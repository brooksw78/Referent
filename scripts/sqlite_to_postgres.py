from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from app.db_postgres import get_conn


def parse_timestamp(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_bool(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip() in {"1", "true", "TRUE", "t", "yes"}


def fetch_sqlite_rows(cursor: sqlite3.Cursor, query: str) -> list[sqlite3.Row]:
    cursor.execute(query)
    return cursor.fetchall()


def upsert_many(cursor, sql: str, rows: Iterable[Sequence]):
    rows = list(rows)
    if not rows:
        return
    cursor.executemany(sql, rows)


def reset_sequences(cursor) -> None:
    tables = ["books", "person_types", "nationalities", "people", "citations", "epigraphs"]
    for table in tables:
        cursor.execute(
            """
            SELECT setval(
                pg_get_serial_sequence(%s, 'id'),
                COALESCE((SELECT MAX(id) FROM {}), 0) + 1,
                false
            )
            """.format(table),
            (table,),
        )


def migrate(sqlite_path: Path) -> None:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    def int_or_none(value):
        if value is None:
            return None
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return None
        return int(text)

    def int_required(value):
        result = int_or_none(value)
        if result is None:
            raise ValueError("Expected integer value, got empty/null")
        return result

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    with sqlite_conn, get_conn() as pg_conn, pg_conn.cursor() as pg_cur:
        pg_cur.execute("SET ROLE referent_user")
        sl_cur = sqlite_conn.cursor()

        # person_types
        person_types = fetch_sqlite_rows(sl_cur, "SELECT id, name FROM person_types ORDER BY id")
        person_type_payload = [(int_required(row["id"]), row["name"]) for row in person_types]
        if person_type_payload:
            upsert_many(
                pg_cur,
                """
                INSERT INTO person_types (id, name)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                """,
                person_type_payload,
            )

        # nationalities
        nationalities = fetch_sqlite_rows(sl_cur, "SELECT id, name FROM nationalities ORDER BY id")
        nationality_payload = [(int_required(row["id"]), row["name"]) for row in nationalities]
        if nationality_payload:
            upsert_many(
                pg_cur,
                """
                INSERT INTO nationalities (id, name)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                """,
                nationality_payload,
            )

        # people
        people_rows = fetch_sqlite_rows(
            sl_cur,
            """
            SELECT
                id, name, wiki_url, bio_summary, type_id, nationality_id, sex,
                birth_year, death_year, birth_year_era, death_year_era,
                notes, created_at, updated_at
            FROM people
            ORDER BY id
            """,
        )
        people_payload = []
        people_ids = set()
        for row in people_rows:
            pid = int_required(row["id"])
            people_ids.add(pid)
            people_payload.append(
                (
                    pid,
                    row["name"],
                    row["wiki_url"],
                    row["bio_summary"],
                    int_or_none(row["type_id"]),
                    int_or_none(row["nationality_id"]),
                    row["sex"],
                    int_or_none(row["birth_year"]),
                    int_or_none(row["death_year"]),
                    row["birth_year_era"],
                    row["death_year_era"],
                    row["notes"],
                    parse_timestamp(row["created_at"]),
                    parse_timestamp(row["updated_at"]),
                )
            )
        if people_payload:
            upsert_many(
                pg_cur,
                """
                INSERT INTO people (
                    id, name, wiki_url, bio_summary, type_id, nationality_id, sex,
                    birth_year, death_year, birth_year_era, death_year_era,
                    notes, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    wiki_url = EXCLUDED.wiki_url,
                    bio_summary = EXCLUDED.bio_summary,
                    type_id = EXCLUDED.type_id,
                    nationality_id = EXCLUDED.nationality_id,
                    sex = EXCLUDED.sex,
                    birth_year = EXCLUDED.birth_year,
                    death_year = EXCLUDED.death_year,
                    birth_year_era = EXCLUDED.birth_year_era,
                    death_year_era = EXCLUDED.death_year_era,
                    notes = EXCLUDED.notes,
                    updated_at = EXCLUDED.updated_at
                """,
                people_payload,
            )

        # books
        book_rows = fetch_sqlite_rows(
            sl_cur,
            """
            SELECT
                id, title, publication_year, isbn, is_complete,
                cover_url, cover_image_path, created_at, updated_at
            FROM books
            ORDER BY id
            """,
        )
        book_payload = []
        book_ids = set()
        for row in book_rows:
            bid = int_required(row["id"])
            book_ids.add(bid)
            book_payload.append(
                (
                    bid,
                    row["title"],
                    row["publication_year"],
                    row["isbn"],
                    to_bool(row["is_complete"]),
                    row["cover_url"],
                    row["cover_image_path"],
                    parse_timestamp(row["created_at"]),
                    parse_timestamp(row["updated_at"]),
                )
            )
        if book_payload:
            upsert_many(
                pg_cur,
                """
                INSERT INTO books (
                    id, title, publication_year, isbn, is_complete,
                    cover_url, cover_image_path, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    publication_year = EXCLUDED.publication_year,
                    isbn = EXCLUDED.isbn,
                    is_complete = EXCLUDED.is_complete,
                    cover_url = EXCLUDED.cover_url,
                    cover_image_path = EXCLUDED.cover_image_path,
                    updated_at = EXCLUDED.updated_at
                """,
                book_payload,
            )

        # book contributors
        contributors = fetch_sqlite_rows(
            sl_cur,
            """
            SELECT
                book_id, person_id, role, created_at, updated_at
            FROM book_contributors
            ORDER BY book_id, person_id, role
            """,
        )
        contributor_payload = []
        skipped_contributors = 0
        for row in contributors:
            book_id = int_or_none(row["book_id"])
            person_id = int_or_none(row["person_id"])
            if book_id is None or person_id is None:
                skipped_contributors += 1
                continue
            if book_id not in book_ids or person_id not in people_ids:
                skipped_contributors += 1
                continue
            contributor_payload.append(
                (
                    book_id,
                    person_id,
                    row["role"],
                    parse_timestamp(row["created_at"]),
                    parse_timestamp(row["updated_at"]),
                )
            )
        if contributor_payload:
            upsert_many(
                pg_cur,
                """
                INSERT INTO book_contributors (
                    book_id, person_id, role, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (book_id, person_id, role) DO UPDATE SET
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                """,
                contributor_payload,
            )
        if skipped_contributors:
            print(f"Skipped {skipped_contributors} book_contributors missing references.")

        # citations
        citation_rows = fetch_sqlite_rows(
            sl_cur,
            """
            SELECT
                id, person_id, book_id, page_number,
                indirect_citation, notes, created_at, updated_at
            FROM citations
            ORDER BY id
            """,
        )
        citation_payload = []
        skipped_citations = 0
        for row in citation_rows:
            person_id = int_or_none(row["person_id"])
            book_id = int_or_none(row["book_id"])
            if person_id is not None and person_id not in people_ids:
                skipped_citations += 1
                continue
            if person_id is None or book_id is None:
                skipped_citations += 1
                continue
            citation_payload.append(
                (
                    int_required(row["id"]),
                    person_id,
                    book_id,
                    row["page_number"],
                    to_bool(row["indirect_citation"]),
                    row["notes"],
                    parse_timestamp(row["created_at"]),
                    parse_timestamp(row["updated_at"]),
                )
            )
        if citation_payload:
            upsert_many(
                pg_cur,
                """
                INSERT INTO citations (
                    id, person_id, book_id, page_number,
                    indirect_citation, notes, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    person_id = EXCLUDED.person_id,
                    book_id = EXCLUDED.book_id,
                    page_number = EXCLUDED.page_number,
                    indirect_citation = EXCLUDED.indirect_citation,
                    notes = EXCLUDED.notes,
                    updated_at = EXCLUDED.updated_at
                """,
                citation_payload,
            )
        if skipped_citations:
            print(f"Skipped {skipped_citations} citations missing person/book references or referencing unknown people.")

        # epigraphs
        epigraph_rows = fetch_sqlite_rows(
            sl_cur,
            """
            SELECT
                id, book_id, author_id, quote, notes, created_at, updated_at
            FROM epigraphs
            ORDER BY id
            """,
        )
        epigraph_payload = []
        skipped_epigraphs = 0
        for row in epigraph_rows:
            book_id = int_or_none(row["book_id"])
            author_id = int_or_none(row["author_id"])
            if book_id is None or author_id is None:
                skipped_epigraphs += 1
                continue
            if book_id not in book_ids or author_id not in people_ids:
                skipped_epigraphs += 1
                continue
            epigraph_payload.append(
                (
                    int_required(row["id"]),
                    book_id,
                    author_id,
                    row["quote"],
                    row["notes"],
                    parse_timestamp(row["created_at"]),
                    parse_timestamp(row["updated_at"]),
                )
            )
        if epigraph_payload:
            upsert_many(
                pg_cur,
                """
                INSERT INTO epigraphs (
                    id, book_id, author_id, quote, notes, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    book_id = EXCLUDED.book_id,
                    author_id = EXCLUDED.author_id,
                    quote = EXCLUDED.quote,
                    notes = EXCLUDED.notes,
                    updated_at = EXCLUDED.updated_at
                """,
                epigraph_payload,
            )
        if skipped_epigraphs:
            print(f"Skipped {skipped_epigraphs} epigraphs missing references.")

        reset_sequences(pg_cur)


def main():
    parser = argparse.ArgumentParser(description="Copy data from SQLite to PostgreSQL.")
    parser.add_argument(
        "--sqlite",
        dest="sqlite_path",
        default=Path("instance/referent.sqlite3"),
        type=Path,
        help="Path to the SQLite database file.",
    )
    args = parser.parse_args()
    migrate(args.sqlite_path)
    print("SQLite data migrated to PostgreSQL successfully.")


if __name__ == "__main__":
    main()
