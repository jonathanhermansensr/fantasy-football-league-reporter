#!/usr/bin/env python3
"""
One-time Yahoo OAuth helper.

This script does NOT store your Client ID or Client Secret.
It obtains the initial Yahoo refresh token after Yahoo Fantasy API access is approved.
"""

from getpass import getpass
from urllib.parse import urlencode, urlparse, parse_qs
import webbrowser
import requests

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
DEFAULT_REDIRECT_URI = "https://localhost:8080/callback"


def extract_code(value: str) -> str:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        code = parse_qs(parsed.query).get("code", [None])[0]
        if not code:
            raise ValueError("No ?code= parameter was found in the URL.")
        return code
    return value


def main():
    print("Yahoo Fantasy OAuth authorization")
    print("Your credentials are used only for this local run and are not written to disk.\n")

    client_id = getpass("Yahoo Client ID: ").strip()
    client_secret = getpass("Yahoo Client Secret: ").strip()
    redirect_uri = input(
        f"Redirect URI [{DEFAULT_REDIRECT_URI}]: "
    ).strip() or DEFAULT_REDIRECT_URI

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "language": "en-us",
    }
    authorization_url = f"{AUTH_URL}?{urlencode(params)}"

    print("\nOpen this Yahoo authorization URL:\n")
    print(authorization_url)
    print(
        "\nAfter approving access, Yahoo will redirect to your localhost callback. "
        "The page itself may fail to load. That is okay."
    )
    print("Copy the FULL URL from your browser address bar, including ?code=...")

    try:
        webbrowser.open(authorization_url)
    except Exception:
        pass

    redirected = input("\nPaste the redirected URL, or just the authorization code: ")
    code = extract_code(redirected)

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    if not response.ok:
        raise SystemExit(
            f"\nYahoo token exchange failed ({response.status_code}):\n{response.text}"
        )

    payload = response.json()
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise SystemExit(
            "\nYahoo returned no refresh_token. Response keys: "
            + ", ".join(sorted(payload.keys()))
        )

    print("\nSUCCESS")
    print("Copy the value below into the GitHub Actions secret YAHOO_REFRESH_TOKEN.")
    print("Do not commit it to the repository and do not paste it into chat.\n")
    print(refresh_token)


if __name__ == "__main__":
    main()
