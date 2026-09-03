#!/usr/bin/env python3
"""
Fetch Yahoo Fantasy Football league data into /data.

Required GitHub Actions secrets:
  YAHOO_CLIENT_ID
  YAHOO_CLIENT_SECRET
  YAHOO_REFRESH_TOKEN

League:
  Yahoo league ID 726144
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import requests

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

CLIENT_ID = os.environ.get("YAHOO_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("YAHOO_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("YAHOO_REFRESH_TOKEN", "")
REDIRECT_URI = os.environ.get(
    "YAHOO_REDIRECT_URI", "https://localhost:8080/callback"
)
LEAGUE_ID = os.environ.get("YAHOO_LEAGUE_ID", "726144")

DATA_DIR = Path("data")


def require_env() -> None:
    missing = [
        name
        for name, value in [
            ("YAHOO_CLIENT_ID", CLIENT_ID),
            ("YAHOO_CLIENT_SECRET", CLIENT_SECRET),
            ("YAHOO_REFRESH_TOKEN", REFRESH_TOKEN),
        ]
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required environment variable(s): " + ", ".join(missing)
        )


def refresh_access_token() -> str:
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "refresh_token": REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if not response.ok:
        raise SystemExit(
            f"Yahoo OAuth refresh failed ({response.status_code}): {response.text}"
        )

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise SystemExit("Yahoo OAuth response did not include an access_token.")

    rotated = payload.get("refresh_token")
    if rotated and rotated != REFRESH_TOKEN:
        # Never print the new token into Actions logs.
        print(
            "::warning::Yahoo issued a new refresh token. "
            "The existing YAHOO_REFRESH_TOKEN secret may need to be replaced "
            "before the next scheduled run."
        )

    return access_token


def api_get(access_token: str, path: str) -> dict[str, Any]:
    url = API_BASE + path
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "json"},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"Yahoo API GET failed ({response.status_code}) for {path}: "
            f"{response.text[:1000]}"
        )
    return response.json()


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def find_league_key(payload: Any, league_id: str) -> str | None:
    expected_suffix = f".l.{league_id}"
    for item in walk(payload):
        if isinstance(item, dict):
            key = item.get("league_key")
            item_id = item.get("league_id")
            if key and str(item_id) == str(league_id):
                return str(key)
            if key and str(key).endswith(expected_suffix):
                return str(key)

    for item in walk(payload):
        if isinstance(item, str) and item.endswith(expected_suffix):
            return item
    return None


def find_current_week(payload: Any) -> int | None:
    for item in walk(payload):
        if isinstance(item, dict) and "current_week" in item:
            try:
                return int(item["current_week"])
            except (TypeError, ValueError):
                pass
    return None


def find_team_keys(payload: Any, league_key: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(league_key)}\.t\.\d+$")
    keys: set[str] = set()
    for item in walk(payload):
        if isinstance(item, dict):
            key = item.get("team_key")
            if isinstance(key, str) and pattern.match(key):
                keys.add(key)
        elif isinstance(item, str) and pattern.match(item):
            keys.add(item)

    return sorted(
        keys,
        key=lambda value: int(value.rsplit(".", 1)[-1]),
    )


def find_player_keys(payload: Any) -> list[str]:
    keys: set[str] = set()
    pattern = re.compile(r"^\d+\.p\.\d+$")
    for item in walk(payload):
        if isinstance(item, dict):
            key = item.get("player_key")
            if isinstance(key, str) and pattern.match(key):
                keys.add(key)
        elif isinstance(item, str) and pattern.match(item):
            keys.add(item)
    return sorted(keys)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def fetch_week(
    access_token: str,
    league_key: str,
    team_keys: list[str],
    week: int,
) -> None:
    week_dir = DATA_DIR / "weeks" / f"week_{week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)

    scoreboard = api_get(
        access_token,
        f"/league/{league_key}/scoreboard;week={week}",
    )
    write_json(week_dir / "scoreboard.json", scoreboard)

    for team_key in team_keys:
        roster = api_get(
            access_token,
            f"/team/{team_key}/roster;week={week}",
        )
        team_stats = api_get(
            access_token,
            f"/team/{team_key}/stats;type=week;week={week}",
        )

        team_file = safe_name(team_key)
        write_json(week_dir / "rosters" / f"{team_file}.json", roster)
        write_json(week_dir / "team_stats" / f"{team_file}.json", team_stats)

        player_keys = find_player_keys(roster)
        if player_keys:
            # An NFL fantasy roster is normally small enough for one player_keys request.
            joined = ",".join(player_keys)
            try:
                player_stats = api_get(
                    access_token,
                    f"/league/{league_key}/players;player_keys={joined}"
                    f"/stats;type=week;week={week}",
                )
                write_json(
                    week_dir / "player_stats" / f"{team_file}.json",
                    player_stats,
                )
            except RuntimeError as exc:
                # Keep the main data pull alive if Yahoo rejects this optional endpoint.
                print(f"::warning::{exc}")


def main() -> None:
    require_env()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    access_token = refresh_access_token()

    # Yahoo accepts "nfl" as the current Football game code.
    user_leagues = api_get(
        access_token,
        "/users;use_login=1/games;game_keys=nfl/leagues",
    )
    write_json(DATA_DIR / "user_leagues.json", user_leagues)

    league_key = find_league_key(user_leagues, LEAGUE_ID)
    if not league_key:
        raise SystemExit(
            f"Could not find Yahoo league ID {LEAGUE_ID} in the authenticated "
            "account's current NFL leagues."
        )

    print(f"Found league: {league_key}")

    league = api_get(access_token, f"/league/{league_key}")
    settings = api_get(access_token, f"/league/{league_key}/settings")
    standings = api_get(access_token, f"/league/{league_key}/standings")
    teams = api_get(access_token, f"/league/{league_key}/teams")
    transactions = api_get(access_token, f"/league/{league_key}/transactions")
    draftresults = api_get(access_token, f"/league/{league_key}/draftresults")

    write_json(DATA_DIR / "league.json", league)
    write_json(DATA_DIR / "settings.json", settings)
    write_json(DATA_DIR / "standings.json", standings)
    write_json(DATA_DIR / "teams.json", teams)
    write_json(DATA_DIR / "transactions.json", transactions)
    write_json(DATA_DIR / "draftresults.json", draftresults)

    current_week = find_current_week(league)
    if not current_week:
        print(
            "::warning::Could not determine current_week. "
            "League-level data was saved, but weekly data was skipped."
        )
        return

    team_keys = find_team_keys(teams, league_key)
    if not team_keys:
        raise SystemExit("Yahoo returned no team keys for the league.")

    # On the first successful run, backfill all weeks through the current week.
    # On later runs, refresh only the current and prior week, while preserving
    # already-collected history in Git.
    weeks_dir = DATA_DIR / "weeks"
    existing_weeks = {
        int(match.group(1))
        for path in weeks_dir.glob("week_*")
        if (match := re.match(r"week_(\d+)$", path.name))
    } if weeks_dir.exists() else set()

    if not existing_weeks:
        weeks_to_fetch = set(range(1, current_week + 1))
    else:
        weeks_to_fetch = {
            week
            for week in (current_week - 1, current_week)
            if week >= 1
        }
        weeks_to_fetch.update(
            week
            for week in range(1, current_week + 1)
            if week not in existing_weeks
        )

    for week in sorted(weeks_to_fetch):
        print(f"Fetching Week {week}")
        fetch_week(access_token, league_key, team_keys, week)

    print("Yahoo Fantasy data collection complete.")


if __name__ == "__main__":
    main()
