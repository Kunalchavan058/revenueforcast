"""Create local-only database settings without printing or replacing real credentials."""

from __future__ import annotations

import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = {"", "replace_me", "replace_with_local_password"}


def main() -> None:
    """Initialize missing local Compose settings; retain existing non-placeholder values."""
    path = ROOT / ".env"
    path.touch(exist_ok=True)
    values = dotenv_values(path)
    password = values.get("POSTGRES_PASSWORD")
    if not password or password in PLACEHOLDERS:
        password = secrets.token_hex(24)
        set_key(path, "POSTGRES_PASSWORD", password)
    port = values.get("POSTGRES_PORT") or "5432"
    if not values.get("POSTGRES_PORT"):
        set_key(path, "POSTGRES_PORT", port)
    database_url = values.get("DATABASE_URL")
    if not database_url or "replace_" in database_url:
        set_key(
            path,
            "DATABASE_URL",
            f"postgresql+psycopg://retailforecast:{password}@127.0.0.1:{port}/retailforecast",
        )
    print("Local database settings are ready in ignored .env; credentials were not printed.")


if __name__ == "__main__":
    main()
