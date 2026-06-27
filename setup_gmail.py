"""
One-time setup script to authorize Gmail API access and generate token.json.

Usage:
  1. Download your OAuth2 credentials from Google Cloud Console
     (APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app)
     Save the file as credentials.json in this directory.

  2. Run:  python setup_gmail.py

  3. A browser window will open for you to authorize Gmail send access.
     After authorizing, token.json will be created.

  4. Add both files as GitHub Actions secrets:
       GMAIL_CREDENTIALS  ← contents of credentials.json
       GMAIL_TOKEN        ← contents of token.json
       NOTIFY_EMAIL       ← your email address (e.g. chelsea.zhao2@gmail.com)
"""

import json
import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    sys.exit("Run: pip install google-auth-oauthlib")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def main():
    if not os.path.exists(CREDS_FILE):
        sys.exit(
            f"ERROR: {CREDS_FILE} not found.\n"
            "Download it from Google Cloud Console:\n"
            "  APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app"
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
        f.write("\n")

    print(f"\n✅ Authorization complete. Token saved to {TOKEN_FILE}.\n")
    print("Next steps — add these as GitHub Actions secrets:\n")
    print(f"  GMAIL_CREDENTIALS  ← copy the contents of {CREDS_FILE}")
    print(f"  GMAIL_TOKEN        ← copy the contents of {TOKEN_FILE}")
    print(f"  NOTIFY_EMAIL       ← your recipient email address\n")
    print("To add secrets: GitHub repo → Settings → Secrets and variables → Actions → New repository secret")


if __name__ == "__main__":
    main()
