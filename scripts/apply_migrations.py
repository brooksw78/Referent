from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.db_postgres import get_conn

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buffer).rstrip(";"))
            buffer = []
    if buffer:
        statements.append("\n".join(buffer))
    return [stmt.strip() for stmt in statements if stmt.strip()]


def ensure_migrations_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def already_applied(cursor, filename: str) -> bool:
    cursor.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (filename,))
    return cursor.fetchone() is not None


def apply_migration(cursor, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    for statement in _split_statements(sql):
        cursor.execute(statement)
    cursor.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))


def main(selected: str | None = None) -> None:
    if not MIGRATIONS_DIR.exists():
        print(f"Migrations directory not found: {MIGRATIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    migration_files = sorted(p for p in MIGRATIONS_DIR.iterdir() if p.name.endswith(".sql"))
    if selected:
        migration_files = [p for p in migration_files if p.name >= selected]
        if not migration_files:
            print(f"No migrations match selection '{selected}'", file=sys.stderr)
            sys.exit(1)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SET ROLE referent_user")
        ensure_migrations_table(cur)
        for path in migration_files:
            if already_applied(cur, path.name):
                continue
            print(f"Applying migration {path.name}")
            apply_migration(cur, path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply SQL migrations to PostgreSQL.")
    parser.add_argument(
        "--from",
        dest="start_from",
        help="Apply migrations starting from the given filename (inclusive).",
    )
    args = parser.parse_args()
    main(args.start_from)
