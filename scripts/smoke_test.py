from __future__ import annotations

import sys

from app.db_postgres import fetch_all, fetch_one


def main() -> None:
    try:
        info = fetch_one("SELECT current_database() AS database, current_user AS user_name, NOW() AS now")
    except Exception as exc:
        print(f"[FAIL] Unable to connect to PostgreSQL: {exc}", file=sys.stderr)
        sys.exit(1)

    migrations = fetch_all(
        "SELECT filename, applied_at FROM schema_migrations ORDER BY filename"
    )

    print("[OK] Connected to PostgreSQL")
    print(f"    database: {info['database']}")
    print(f"    user: {info['user_name']}")
    print(f"    server_time: {info['now']}")
    if migrations:
        print("Applied migrations:")
        for row in migrations:
            print(f"  - {row['filename']} @ {row['applied_at']}")
    else:
        print("No migrations recorded in schema_migrations.")

    print("Smoke test completed successfully.")


if __name__ == "__main__":
    main()
