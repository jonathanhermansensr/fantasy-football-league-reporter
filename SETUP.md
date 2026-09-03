# Yahoo Fantasy League Reporter Setup

League ID: 726144

## Already completed

- Yahoo Developer application created.
- Yahoo Fantasy Sports API access request submitted.
- GitHub Actions secrets created:
  - YAHOO_CLIENT_ID
  - YAHOO_CLIENT_SECRET

## Do not do this until Yahoo approves Fantasy Sports API access

### 1. Get the initial Yahoo refresh token

Run:

```bash
pip install -r requirements.txt
python scripts/authorize_yahoo.py
```

The script prompts for your Yahoo Client ID and Client Secret without writing them to disk.

Yahoo will send you to the Redirect URI registered with the app:

https://localhost:8080/callback

The browser may show an error because no local web server is running. That is expected. Copy the full URL from the browser address bar, including the `?code=...` portion, and paste it into the script.

### 2. Add the refresh token to GitHub Actions

Repository > Settings > Secrets and variables > Actions > New repository secret

Name:

YAHOO_REFRESH_TOKEN

Value:

The refresh token printed by `scripts/authorize_yahoo.py`.

Do not commit this value and do not paste it into ChatGPT.

### 3. Test the data collector

Repository > Actions > Update Yahoo Fantasy Data > Run workflow

A successful run should create files under:

data/
data/weeks/week_XX/

### 4. Scheduled collection

The workflow runs every Tuesday at 15:30 UTC, after Monday Night Football, and can also be run manually.

## Public-repository privacy

Anything committed under `data/` is visible to anyone if the repository is public.

The collector currently saves Yahoo API responses needed for league reporting. Before relying on the public repository long-term, review the first successful data pull for any manager/profile fields you do not want public. We can then add a sanitization layer that keeps only the data needed for the weekly stories.
