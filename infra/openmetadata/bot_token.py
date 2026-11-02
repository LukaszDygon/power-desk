"""Print the JWT of OpenMetadata's `ingestion-bot`, which ingestion workflows authenticate with.

Logs in as the default admin of a local install (basic auth) and reads the bot's token; the UI shows the same
token under Settings > Bots. Usage: `python bot_token.py http://localhost:8585/api`.
"""

from __future__ import annotations

import base64
import sys

import requests

ADMIN = ("admin@open-metadata.org", "admin")


def bot_token(api: str) -> str:
    email, password = ADMIN
    login = requests.post(
        f"{api}/v1/users/login",
        json={"email": email, "password": base64.b64encode(password.encode()).decode()},
        timeout=30,
    )
    login.raise_for_status()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {login.json()['accessToken']}"
    bot = session.get(f"{api}/v1/bots/name/ingestion-bot", timeout=30)
    bot.raise_for_status()
    auth = session.get(f"{api}/v1/users/auth-mechanism/{bot.json()['botUser']['id']}", timeout=30)
    auth.raise_for_status()
    return auth.json()["config"]["JWTToken"]


if __name__ == "__main__":
    print(bot_token(sys.argv[1]))
