"""Verify the configured database (Somee or SQLite): connect, create schema, count rows.

Usage:  python -m scripts.check_db
"""

import sys

from app import create_app, db


def main() -> int:
    try:
        create_app()
    except Exception as exc:
        print(f"FAILED to connect / create schema: {type(exc).__name__}: {exc}")
        print("Checks: DATABASE_URL format, URL-encoded password, Somee remote access enabled, port 1433 not blocked.")
        return 1
    print(f"backend : {db.backend_name()}")
    print(f"target  : {db.describe_target()}")
    for table, n in db.ping().items():
        print(f"{table:<13}: {n}")
    if db.backend_name() == "sqlite":
        print("NOTE: running on local SQLite. Set DATABASE_URL to the Somee connection string for the cloud database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
