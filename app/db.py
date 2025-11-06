import os
import re
from contextlib import contextmanager

import psycopg
from psycopg import Cursor
from psycopg.rows import dict_row


def _build_conninfo():
    dsn = os.getenv("PG_DSN")
    if dsn:
        return dsn

    parts = []
    mapping = {
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "dbname": "PGDATABASE",
        "host": "PGHOST",
        "port": "PGPORT",
    }
    for key, env in mapping.items():
        value = os.getenv(env)
        if value:
            parts.append(f"{key}={value}")
    return " ".join(parts)


class CompatCursor(Cursor):
    def execute(self, query, params=None, /, *args, **kwargs):
        return super().execute(_prepare_sql(query), params, *args, **kwargs)

    def executemany(self, query, params_list, /, *args, **kwargs):
        return super().executemany(_prepare_sql(query), params_list, *args, **kwargs)


def get_connection():
    conn = psycopg.connect(
        _build_conninfo(),
        row_factory=dict_row,
    )
    conn.autocommit = True
    return conn


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def _prepare_sql(sql: str) -> str:
    prepared = sql
    if "?" in prepared:
        parts = prepared.split("?")
        prepared = "%s".join(parts)

    if re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", prepared, flags=re.IGNORECASE):
        prepared = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", prepared, flags=re.IGNORECASE)
        if "ON CONFLICT" not in prepared.upper():
            prepared = prepared.rstrip()
            suffix = ""
            if prepared.endswith(";"):
                prepared = prepared[:-1]
                suffix = ";"
            prepared = f"{prepared} ON CONFLICT DO NOTHING{suffix}"
    return prepared


def _execute(cursor, sql, params=None):
    statement = _prepare_sql(sql)
    if params is None:
        cursor.execute(statement)
    else:
        cursor.execute(statement, params)


@contextmanager
def _cursor(conn):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def init_db():
    """
    Schema migrations are managed separately (see scripts/apply_migrations.py).
    This function remains for compatibility with the Flask app factory.
    """
    return


# ---------- BOOKS ----------
def add_book(title, publication_year=None, isbn=None, is_complete=False, cover_url=None, cover_image_path=None):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                INSERT INTO books (title, publication_year, isbn, is_complete, cover_url, cover_image_path, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (title, publication_year, isbn, bool(is_complete), cover_url, cover_image_path),
            )
            row = cursor.fetchone()
        return row["id"]


def update_book(book_id, title, publication_year=None, isbn=None, is_complete=False, cover_url=None, cover_image_path=None):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                UPDATE books
                SET title = %s,
                    publication_year = %s,
                    isbn = %s,
                    is_complete = %s,
                    cover_url = %s,
                    cover_image_path = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (title, publication_year, isbn, bool(is_complete), cover_url, cover_image_path, book_id),
            )


def get_books(include_completed=True, ensure_ids=None):
    ensure_ids = [int(i) for i in ensure_ids or []]
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            query = """
                SELECT
                    b.id AS id,
                    b.title AS title,
                    b.publication_year AS publication_year,
                    b.isbn AS isbn,
                    authors.names AS authors,
                    authors.ids AS author_ids,
                    translators.names AS translators,
                    translators.ids AS translator_ids,
                    COALESCE(c_counts.citation_count, 0) AS citation_count,
                    COALESCE(e_counts.epigraph_count, 0) AS epigraph_count,
                    b.is_complete AS is_complete,
                    b.cover_url AS cover_url,
                    b.cover_image_path AS cover_image_path
                FROM books b
                LEFT JOIN (
                    SELECT
                        bc.book_id,
                        string_agg(DISTINCT p.name, ', ') AS names,
                        string_agg(DISTINCT (p.id::text || '::' || p.name), '|') AS ids
                    FROM book_contributors bc
                    JOIN people p ON p.id = bc.person_id
                    WHERE bc.role = 'author'
                    GROUP BY bc.book_id
                ) AS authors ON authors.book_id = b.id
                LEFT JOIN (
                    SELECT
                        bc.book_id,
                        string_agg(DISTINCT p.name, ', ') AS names,
                        string_agg(DISTINCT (p.id::text || '::' || p.name), '|') AS ids
                    FROM book_contributors bc
                    JOIN people p ON p.id = bc.person_id
                    WHERE bc.role = 'translator'
                    GROUP BY bc.book_id
                ) AS translators ON translators.book_id = b.id
                LEFT JOIN (
                    SELECT book_id, COUNT(*) AS citation_count
                    FROM citations
                    GROUP BY book_id
                ) AS c_counts ON c_counts.book_id = b.id
                LEFT JOIN (
                    SELECT book_id, COUNT(*) AS epigraph_count
                    FROM epigraphs
                    GROUP BY book_id
                ) AS e_counts ON e_counts.book_id = b.id
            """

            params = []
            conditions = []
            if not include_completed:
                if ensure_ids:
                    placeholders = ", ".join(["%s"] * len(ensure_ids))
                    conditions.append(f"(b.is_complete = FALSE OR b.id IN ({placeholders}))")
                    params.extend(ensure_ids)
                else:
                    conditions.append("b.is_complete = FALSE")

            if conditions:
                query += "\nWHERE " + " AND ".join(conditions)

            query += "\nORDER BY b.title"

            cursor.execute(query, params)
            return _rows_to_dicts(cursor.fetchall())


def get_book_by_id(book_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    b.id AS id,
                    b.title AS title,
                    b.publication_year AS publication_year,
                    b.isbn AS isbn,
                    authors.names AS authors,
                    translators.names AS translators,
                    b.is_complete AS is_complete,
                    b.cover_url AS cover_url,
                    b.cover_image_path AS cover_image_path
                FROM books b
                LEFT JOIN (
                    SELECT bc.book_id, string_agg(DISTINCT p.name, ', ') AS names
                    FROM book_contributors bc
                    JOIN people p ON p.id = bc.person_id
                    WHERE bc.role = 'author'
                    GROUP BY bc.book_id
                ) AS authors ON authors.book_id = b.id
                LEFT JOIN (
                    SELECT bc.book_id, string_agg(DISTINCT p.name, ', ') AS names
                    FROM book_contributors bc
                    JOIN people p ON p.id = bc.person_id
                    WHERE bc.role = 'translator'
                    GROUP BY bc.book_id
                ) AS translators ON translators.book_id = b.id
                WHERE b.id = %s
                """,
                (book_id,),
            )
            return _row_to_dict(cursor.fetchone())


# ---------- PERSON TYPES ----------
_SCHEMA_CACHE = {}


def _table_has_column(cursor, table_name, column_name):
    key = (table_name, column_name)
    cached = _SCHEMA_CACHE.get(key)
    if cached is not None:
        return cached
    _execute(
        cursor,
        """
        SELECT 1 AS present
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    )
    exists = cursor.fetchone() is not None
    _SCHEMA_CACHE[key] = exists
    return exists


def add_person_type(name):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            has_timestamps = _table_has_column(cursor, "person_types", "updated_at")
            if has_timestamps:
                query = """
                INSERT INTO person_types (name, created_at, updated_at)
                VALUES (%s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (name) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """
            else:
                query = """
                INSERT INTO person_types (name)
                VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            _execute(
                cursor,
                query,
                (name,),
            )
            row = cursor.fetchone()
            return row["id"] if row else None


def update_person_type(type_id, name):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            has_timestamps = _table_has_column(cursor, "person_types", "updated_at")
            if has_timestamps:
                query = """
                UPDATE person_types
                SET name = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """
            else:
                query = """
                UPDATE person_types
                SET name = %s
                WHERE id = %s
                """
            _execute(cursor, query, (name, type_id))


def delete_person_type(type_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "DELETE FROM person_types WHERE id = %s", (type_id,))


def get_person_types():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT pt.id AS id, pt.name AS name, COUNT(p.id) AS usage_count
                FROM person_types pt
                LEFT JOIN people p ON p.type_id = pt.id
                GROUP BY pt.id, pt.name
                ORDER BY pt.name
                """,
            )
            return _rows_to_dicts(cursor.fetchall())


# ---------- NATIONALITIES ----------
def add_nationality(name):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                INSERT INTO nationalities (name)
                VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (name,),
            )
            row = cursor.fetchone()
            return row["id"] if row else None


def get_nationalities():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT n.id AS id, n.name AS name, COUNT(p.id) AS usage_count
                FROM nationalities n
                LEFT JOIN people p ON p.nationality_id = n.id
                GROUP BY n.id, n.name
                ORDER BY n.name
                """,
            )
            return _rows_to_dicts(cursor.fetchall())


def update_nationality(nationality_id, name):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                "UPDATE nationalities SET name = %s WHERE id = %s",
                (name, nationality_id),
            )


def delete_nationality(nationality_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "DELETE FROM nationalities WHERE id = %s", (nationality_id,))


def _get_person_type_id(type_name):
    if not type_name:
        return None
    type_name = type_name.strip()
    if not type_name:
        return None

    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "SELECT id FROM person_types WHERE name = %s", (type_name,))
            row = cursor.fetchone()

    if row:
        return row["id"]

    return add_person_type(type_name)


def get_or_create_person(name, default_type=None):
    normalized = (name or "").strip()
    if not normalized:
        return None

    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                "SELECT id, type_id FROM people WHERE LOWER(name) = LOWER(%s)",
                (normalized,),
            )
            row = cursor.fetchone()
            if row:
                person_id = row["id"]
                current_type_id = row["type_id"]
                if default_type and current_type_id is None:
                    type_id = _get_person_type_id(default_type)
                    if type_id is not None:
                        _execute(
                            cursor,
                            "UPDATE people SET type_id = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                            (type_id, person_id),
                        )
                return person_id

        type_id = _get_person_type_id(default_type) if default_type else None
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                INSERT INTO people (name, wiki_url, bio_summary, type_id, nationality_id, birth_year, death_year, notes, created_at, updated_at)
                VALUES (%s, NULL, NULL, %s, NULL, NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (normalized, type_id),
            )
            row = cursor.fetchone()
            return row["id"]


def add_book_contributor(book_id, person_id, role):
    if not person_id or not role:
        return
    role = role.lower()
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                INSERT INTO book_contributors (book_id, person_id, role, created_at, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (book_id, person_id, role) DO UPDATE
                SET updated_at = EXCLUDED.updated_at
                """,
                (book_id, person_id, role),
            )


def remove_book_contributor(book_id, person_id, role=None):
    if not person_id:
        return
    query = "DELETE FROM book_contributors WHERE book_id = %s AND person_id = %s"
    params = [book_id, person_id]
    if role:
        query += " AND role = %s"
        params.append(role.lower())
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, query, params)


def get_book_contributors(book_id, role=None):
    query = [
        "SELECT",
        "    bc.role AS role,",
        "    p.id AS person_id,",
        "    p.name AS person_name",
        "FROM book_contributors bc",
        "JOIN people p ON p.id = bc.person_id",
        "WHERE bc.book_id = %s"
    ]
    params = [book_id]

    if role:
        query.append("AND bc.role = %s")
        params.append(role.lower())

    query.append(
        "ORDER BY CASE bc.role WHEN 'author' THEN 0 WHEN 'translator' THEN 1 ELSE 2 END, LOWER(p.name)"
    )

    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "\n".join(query), params)
            return _rows_to_dicts(cursor.fetchall())


# ---------- PEOPLE ----------
def add_person(
    name,
    wiki_url,
    bio_summary,
    type_id=None,
    nationality_id=None,
    sex=None,
    birth_year=None,
    death_year=None,
    notes=None,
    birth_year_era="AD",
    death_year_era="AD",
):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                INSERT INTO people (
                    name, wiki_url, bio_summary, type_id, nationality_id, sex,
                    birth_year, death_year, birth_year_era, death_year_era,
                    notes, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING id
                """,
                (
                    name,
                    wiki_url,
                    bio_summary,
                    type_id,
                    nationality_id,
                    sex,
                    birth_year,
                    death_year,
                    birth_year_era or "AD",
                    death_year_era or "AD",
                    notes,
                ),
            )
            row = cursor.fetchone()
            return row["id"]


def get_people(
    search_term=None,
    type_id=None,
    nationality_id=None,
    missing_nationality=False,
    missing_sex=False,
):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            query = """
                SELECT
                    people.id AS id,
                    people.name AS name,
                    person_types.name AS type_name,
                    people.sex AS sex,
                    people.wiki_url AS wiki_url,
                    COUNT(DISTINCT citations.id) AS citation_count,
                    COUNT(DISTINCT epigraphs.id) AS epigraph_count,
                    people.birth_year AS birth_year,
                    people.death_year AS death_year,
                    people.birth_year_era AS birth_year_era,
                    people.death_year_era AS death_year_era,
                    nationalities.name AS nationality_name
                FROM people
                LEFT JOIN person_types ON people.type_id = person_types.id
                LEFT JOIN citations ON people.id = citations.person_id
                LEFT JOIN epigraphs ON people.id = epigraphs.author_id
                LEFT JOIN nationalities ON people.nationality_id = nationalities.id
            """
            params = []
            conditions = []
            if search_term:
                conditions.append("LOWER(people.name) LIKE %s")
                params.append(f"%{search_term.lower()}%")
            if type_id is not None:
                conditions.append("people.type_id = %s")
                params.append(int(type_id))
            if nationality_id is not None:
                conditions.append("people.nationality_id = %s")
                params.append(int(nationality_id))
            if missing_nationality:
                conditions.append("people.nationality_id IS NULL")
            if missing_sex:
                conditions.append("(people.sex IS NULL OR TRIM(people.sex) = '')")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " GROUP BY people.id, person_types.name, nationalities.name ORDER BY people.name"
            cursor.execute(query, params)
            return _rows_to_dicts(cursor.fetchall())

def get_person_by_id(person_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    people.id,
                    people.name,
                    people.type_id,
                    people.sex,
                    people.wiki_url,
                    people.bio_summary,
                    people.birth_year,
                    people.death_year,
                    people.notes,
                    person_types.name AS type_name,
                    people.nationality_id,
                    nationalities.name AS nationality_name,
                    people.birth_year_era,
                    people.death_year_era
                FROM people
                LEFT JOIN person_types ON people.type_id = person_types.id
                LEFT JOIN nationalities ON people.nationality_id = nationalities.id
                WHERE people.id = %s
                """,
                (person_id,),
            )
            return _row_to_dict(cursor.fetchone())

def update_person(
    person_id,
    name,
    type_id,
    nationality_id,
    sex,
    birth_year,
    death_year,
    notes,
    wiki_url=None,
    bio_summary=None,
    birth_year_era="AD",
    death_year_era="AD",
):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                UPDATE people
                SET name = %s,
                    type_id = %s,
                    nationality_id = %s,
                    sex = %s,
                    birth_year = %s,
                    death_year = %s,
                    birth_year_era = %s,
                    death_year_era = %s,
                    notes = %s,
                    wiki_url = %s,
                    bio_summary = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    name,
                    type_id,
                    nationality_id,
                    sex,
                    birth_year,
                    death_year,
                    birth_year_era or "AD",
                    death_year_era or "AD",
                    notes,
                    wiki_url,
                    bio_summary,
                    person_id,
                ),
            )


def delete_person(person_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "DELETE FROM people WHERE id = %s", (person_id,))
def person_exists(name):
    with get_connection() as conn:
        with _cursor(conn) as cur:
            _execute(cur, "SELECT id FROM people WHERE name = %s", (name.strip(),))
            return cur.fetchone() is not None

# ---------- CITATIONS ----------
def add_citation(person_id, book_id, page_number, indirect_citation, notes=None):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                INSERT INTO citations (person_id, book_id, page_number, indirect_citation, notes, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (person_id, book_id, page_number, indirect_citation, notes),
            )


def get_citations():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
            SELECT
                c.id AS id,
                p.name AS person_name,
                b.title AS book_title,
                c.page_number AS page_number,
                b.id AS book_id,
                c.notes AS notes,
                c.indirect_citation AS indirect_citation
            FROM citations c
            JOIN people p ON c.person_id = p.id
            JOIN books b ON c.book_id = b.id
            ORDER BY c.updated_at DESC
            """,
            )
            return _rows_to_dicts(cursor.fetchall())


def get_citation_by_id(citation_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    id,
                    person_id,
                    book_id,
                    page_number,
                    notes,
                    indirect_citation
                FROM citations
                WHERE id = %s
                """,
                (citation_id,),
            )
            return _row_to_dict(cursor.fetchone())

def get_citations_by_book(book_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    c.id AS id,
                    p.name AS person_name,
                    c.page_number AS page_number,
                    p.id AS person_id,
                    c.notes AS notes,
                    c.indirect_citation AS indirect_citation,
                    pt.name AS type_name,
                    n.name AS nationality_name,
                    p.birth_year AS birth_year,
                    p.birth_year_era AS birth_year_era,
                    p.death_year AS death_year,
                    p.death_year_era AS death_year_era
                FROM citations c
                JOIN people p ON c.person_id = p.id
                LEFT JOIN person_types pt ON pt.id = p.type_id
                LEFT JOIN nationalities n ON n.id = p.nationality_id
                WHERE c.book_id = %s
                ORDER BY
                    CASE
                        WHEN TRIM(c.page_number) ~ '^[0-9]*$' AND TRIM(c.page_number) <> ''
                            THEN CAST(TRIM(c.page_number) AS INTEGER)
                        ELSE NULL
                    END,
                    TRIM(c.page_number)
                """,
                (book_id,),
            )
            return _rows_to_dicts(cursor.fetchall())

def get_citations_by_person(person_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    c.id AS id,
                    p.name AS person_name,
                    b.title AS book_title,
                    c.page_number AS page_number,
                    b.id AS book_id,
                    c.notes AS notes,
                    c.indirect_citation AS indirect_citation
                FROM citations c
                JOIN people p ON c.person_id = p.id
                JOIN books b ON c.book_id = b.id
                WHERE c.person_id = %s
                ORDER BY b.title, c.page_number
                """,
                (person_id,),
            )
            return _rows_to_dicts(cursor.fetchall())

def update_citation(citation_id, person_id, book_id, page_number, indirect_citation, notes):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                UPDATE citations
                SET person_id = %s,
                    book_id = %s,
                    page_number = %s,
                    notes = %s,
                    indirect_citation = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (person_id, book_id, page_number, notes, indirect_citation, citation_id),
            )


# ---------- EPIGRAPHS ----------
def add_epigraph(book_id, author_id, quote, notes=None):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                INSERT INTO epigraphs (book_id, author_id, quote, notes, created_at, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (book_id, author_id, quote, notes),
            )
            row = cursor.fetchone()
            return row["id"]


def get_epigraphs():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    e.id AS id,
                    b.id AS book_id,
                    b.title AS book_title,
                    p.id AS author_id,
                    p.name AS author_name,
                    e.quote AS quote,
                    e.notes AS notes,
                    e.created_at AS created_at
                FROM epigraphs e
                JOIN books b ON e.book_id = b.id
                JOIN people p ON e.author_id = p.id
                ORDER BY b.title, e.created_at DESC
                """,
            )
            return _rows_to_dicts(cursor.fetchall())


def get_epigraph_by_id(epigraph_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    id,
                    book_id,
                    author_id,
                    quote,
                    notes
                FROM epigraphs
                WHERE id = %s
                """,
                (epigraph_id,),
            )
            return _row_to_dict(cursor.fetchone())


def get_epigraphs_by_book(book_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    e.id AS id,
                    e.quote AS quote,
                    e.notes AS notes,
                    p.name AS author_name,
                    p.id AS author_id,
                    e.created_at AS created_at
                FROM epigraphs e
                JOIN people p ON e.author_id = p.id
                WHERE e.book_id = %s
                ORDER BY e.created_at
                """,
                (book_id,),
            )
            return _rows_to_dicts(cursor.fetchall())


def get_epigraphs_by_person(person_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    e.id AS id,
                    e.quote AS quote,
                    e.notes AS notes,
                    b.title AS book_title,
                    b.id AS book_id,
                    e.created_at AS created_at
                FROM epigraphs e
                JOIN books b ON e.book_id = b.id
                WHERE e.author_id = %s
                ORDER BY e.created_at
                """,
                (person_id,),
            )
            return _rows_to_dicts(cursor.fetchall())


def update_epigraph(epigraph_id, book_id, author_id, quote, notes):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                UPDATE epigraphs
                SET book_id = %s,
                    author_id = %s,
                    quote = %s,
                    notes = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (book_id, author_id, quote, notes, epigraph_id),
            )


def delete_epigraph(epigraph_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "DELETE FROM epigraphs WHERE id = %s", (epigraph_id,))


def get_book_contributions_by_person(person_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    bc.role AS role,
                    b.id AS book_id,
                    b.title AS book_title,
                    b.cover_url AS cover_url,
                    b.cover_image_path AS cover_image_path
                FROM book_contributors bc
                JOIN books b ON b.id = bc.book_id
                WHERE bc.person_id = %s
                ORDER BY CASE bc.role WHEN 'author' THEN 0 WHEN 'translator' THEN 1 ELSE 2 END, LOWER(b.title)
                """,
                (person_id,),
            )
            return _rows_to_dicts(cursor.fetchall())


def get_book_summary(book_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT pt.id AS id, pt.name AS name, SUM(cnt) AS total
                FROM (
                    SELECT p.type_id AS type_id, COUNT(*) AS cnt
                    FROM citations c
                    JOIN people p ON p.id = c.person_id
                    WHERE c.book_id = %s
                    GROUP BY p.type_id
                    UNION ALL
                    SELECT p.type_id AS type_id, COUNT(*) AS cnt
                    FROM epigraphs e
                    JOIN people p ON p.id = e.author_id
                    WHERE e.book_id = %s
                    GROUP BY p.type_id
                ) agg
                JOIN person_types pt ON pt.id = agg.type_id
                GROUP BY pt.id, pt.name
                ORDER BY total DESC, pt.name
                """,
                (book_id, book_id),
            )
            type_rows = _rows_to_dicts(cursor.fetchall())

            _execute(
                cursor,
                """
                SELECT n.id AS id, n.name AS name, SUM(cnt) AS total
                FROM (
                    SELECT p.nationality_id AS nationality_id, COUNT(*) AS cnt
                    FROM citations c
                    JOIN people p ON p.id = c.person_id
                    WHERE c.book_id = %s
                    GROUP BY p.nationality_id
                    UNION ALL
                    SELECT p.nationality_id AS nationality_id, COUNT(*) AS cnt
                    FROM epigraphs e
                    JOIN people p ON p.id = e.author_id
                    WHERE e.book_id = %s
                    GROUP BY p.nationality_id
                ) agg
                JOIN nationalities n ON n.id = agg.nationality_id
                GROUP BY n.id, n.name
                ORDER BY total DESC, n.name
                """,
                (book_id, book_id),
            )
            nationality_rows = _rows_to_dicts(cursor.fetchall())

    return {
        "person_types": type_rows,
        "nationalities": nationality_rows,
    }


def get_book_reference_stats(book_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    (SELECT COUNT(*) FROM citations WHERE book_id = %s) AS citation_total,
                    (SELECT COUNT(*) FROM epigraphs WHERE book_id = %s) AS epigraph_total
                """,
                (book_id, book_id),
            )
            totals_row = cursor.fetchone() or {"citation_total": 0, "epigraph_total": 0}
            citation_total = totals_row["citation_total"] or 0
            epigraph_total = totals_row["epigraph_total"] or 0
            total_references = citation_total + epigraph_total

            _execute(
                cursor,
                """
                SELECT COUNT(*) AS distinct_people
                FROM (
                    SELECT DISTINCT person_id AS person_id
                    FROM citations
                    WHERE book_id = %s
                    UNION
                    SELECT DISTINCT author_id AS person_id
                    FROM epigraphs
                    WHERE book_id = %s
                ) combined
                """,
                (book_id, book_id),
            )
            distinct_people = (cursor.fetchone() or {"distinct_people": 0})["distinct_people"]

            _execute(
                cursor,
                """
                WITH target_people AS (
                    SELECT DISTINCT person_id
                    FROM citations
                    WHERE book_id = %s
                    UNION
                    SELECT DISTINCT author_id AS person_id
                    FROM epigraphs
                    WHERE book_id = %s
                ),
                other_mentions AS (
                    SELECT DISTINCT person_id
                    FROM citations
                    WHERE book_id <> %s
                    UNION
                    SELECT DISTINCT author_id AS person_id
                    FROM epigraphs
                    WHERE book_id <> %s
                )
                SELECT COUNT(*) AS shared_people
                FROM target_people tp
                WHERE tp.person_id IN (SELECT person_id FROM other_mentions)
                """,
                (book_id, book_id, book_id, book_id),
            )
            shared_referents = (cursor.fetchone() or {"shared_people": 0})["shared_people"]

    unique_to_book = max(distinct_people - shared_referents, 0)

    return {
        "total_referents": total_references,
        "unique_referents": unique_to_book,
        "shared_referents": shared_referents or 0,
    }


def get_book_people_lifetimes(book_id):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT
                    p.id AS person_id,
                    p.name AS name,
                    p.birth_year AS birth_year,
                    p.birth_year_era AS birth_year_era,
                    p.death_year AS death_year,
                    p.death_year_era AS death_year_era,
                    pt.name AS type_name
                FROM people p
                LEFT JOIN person_types pt ON pt.id = p.type_id
                WHERE p.id IN (
                    SELECT person_id FROM citations WHERE book_id = %s
                    UNION
                    SELECT author_id FROM epigraphs WHERE book_id = %s
                )
                ORDER BY
                    CASE WHEN p.birth_year IS NULL THEN 1 ELSE 0 END,
                    p.birth_year,
                    LOWER(p.name)
                """,
                (book_id, book_id),
            )
            return _rows_to_dicts(cursor.fetchall())


def get_books_with_shared_referents(book_id, limit=6):
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                WITH target_people AS (
                    SELECT person_id
                    FROM citations
                    WHERE book_id = %s
                      AND person_id IS NOT NULL
                      AND TRIM(person_id::text) <> ''
                    UNION
                    SELECT author_id AS person_id
                    FROM epigraphs
                    WHERE book_id = %s
                      AND author_id IS NOT NULL
                      AND TRIM(author_id::text) <> ''
                ),
                other_references AS (
                    SELECT c.book_id AS book_id, c.person_id AS person_id
                    FROM citations c
                    WHERE c.book_id <> %s AND c.person_id IN (SELECT person_id FROM target_people)
                    UNION
                    SELECT e.book_id AS book_id, e.author_id AS person_id
                    FROM epigraphs e
                    WHERE e.book_id <> %s AND e.author_id IN (SELECT person_id FROM target_people)
                ),
                aggregate_totals AS (
                    SELECT book_id, COUNT(DISTINCT person_id) AS total_people
                    FROM (
                        SELECT book_id, person_id FROM citations
                        UNION
                        SELECT book_id, author_id AS person_id FROM epigraphs
                    )
                    GROUP BY book_id
                ),
                current_totals AS (
                    SELECT COUNT(DISTINCT person_id) AS total_people
                    FROM target_people
                ),
                shared_people AS (
                    SELECT
                        book_id,
                        string_agg(name, '||') AS names
                    FROM (
                        SELECT DISTINCT o.book_id AS book_id, p.name AS name
                        FROM other_references o
                        JOIN people p ON p.id = o.person_id
                        ORDER BY p.name
                    ) AS names_cte
                    GROUP BY book_id
                )
                SELECT
                    b.id AS book_id,
                    b.title AS title,
                    COUNT(DISTINCT refs.person_id) AS shared_count,
                    COALESCE(aggregate_totals.total_people, 0) AS other_total,
                    current_totals.total_people AS current_total,
                    COALESCE(shared_people.names, '') AS shared_names
                FROM other_references AS refs
                JOIN books b ON b.id = refs.book_id
                LEFT JOIN aggregate_totals ON aggregate_totals.book_id = refs.book_id
                LEFT JOIN shared_people ON shared_people.book_id = refs.book_id
                CROSS JOIN current_totals
                WHERE b.id <> %s
                GROUP BY
                    b.id,
                    b.title,
                    aggregate_totals.total_people,
                    current_totals.total_people,
                    shared_people.names
                ORDER BY shared_count DESC, LOWER(b.title)
                LIMIT %s
                """,
                (book_id, book_id, book_id, book_id, book_id, int(limit)),
            )
            return _rows_to_dicts(cursor.fetchall())


def get_chord_data():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "SELECT id, title FROM books ORDER BY title")
            book_rows = _rows_to_dicts(cursor.fetchall())

            _execute(cursor, "SELECT id, name FROM person_types ORDER BY name")
            type_rows = _rows_to_dicts(cursor.fetchall())

            _execute(
                cursor,
                """
                SELECT c.book_id AS book_id, pt.id AS type_id, COUNT(*) AS citation_count
                FROM citations c
                JOIN people p ON p.id = c.person_id
                LEFT JOIN person_types pt ON pt.id = p.type_id
                WHERE pt.id IS NOT NULL
                GROUP BY c.book_id, pt.id
                """,
            )
            citation_rows = _rows_to_dicts(cursor.fetchall())

            _execute(
                cursor,
                """
                SELECT e.book_id AS book_id, pt.id AS type_id, COUNT(*) AS epigraph_count
                FROM epigraphs e
                JOIN people p ON p.id = e.author_id
                LEFT JOIN person_types pt ON pt.id = p.type_id
                WHERE pt.id IS NOT NULL
                GROUP BY e.book_id, pt.id
                """,
            )
            epigraph_rows = _rows_to_dicts(cursor.fetchall())

    books = {row["id"]: row["title"] for row in book_rows}
    types = {row["id"]: row["name"] for row in type_rows}
    connections = {}

    for row in citation_rows:
        book_id = row["book_id"]
        type_id = row["type_id"]
        count = row["citation_count"]
        if book_id not in books or type_id not in types:
            continue
        key = (book_id, type_id)
        entry = connections.setdefault(key, {"citations": 0, "epigraphs": 0})
        entry["citations"] = count

    for row in epigraph_rows:
        book_id = row["book_id"]
        type_id = row["type_id"]
        count = row["epigraph_count"]
        if book_id not in books or type_id not in types:
            continue
        key = (book_id, type_id)
        entry = connections.setdefault(key, {"citations": 0, "epigraphs": 0})
        entry["epigraphs"] = count

    chords = []
    for (book_id, type_id), counts in connections.items():
        total = counts["citations"] + counts["epigraphs"]
        if not total:
            continue
        chords.append({
            "book": {"id": book_id, "title": books[book_id]},
            "person_type": {"id": type_id, "name": types[type_id]},
            "citations": counts["citations"],
            "epigraphs": counts["epigraphs"],
            "total": total,
        })

    return {
        "books": book_rows,
        "person_types": type_rows,
        "connections": chords,
    }


def get_book_nationality_data():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "SELECT id, title FROM books ORDER BY title")
            book_rows = _rows_to_dicts(cursor.fetchall())

            _execute(cursor, "SELECT id, name FROM nationalities ORDER BY name")
            nationality_rows = _rows_to_dicts(cursor.fetchall())

            _execute(
                cursor,
                """
                SELECT c.book_id AS book_id, n.id AS nationality_id, COUNT(*) AS citation_count
                FROM citations c
                JOIN people p ON p.id = c.person_id
                LEFT JOIN nationalities n ON n.id = p.nationality_id
                WHERE n.id IS NOT NULL
                GROUP BY c.book_id, n.id
                """,
            )
            citation_rows = _rows_to_dicts(cursor.fetchall())

            _execute(
                cursor,
                """
                SELECT e.book_id AS book_id, n.id AS nationality_id, COUNT(*) AS epigraph_count
                FROM epigraphs e
                JOIN people p ON p.id = e.author_id
                LEFT JOIN nationalities n ON n.id = p.nationality_id
                WHERE n.id IS NOT NULL
                GROUP BY e.book_id, n.id
                """,
            )
            epigraph_rows = _rows_to_dicts(cursor.fetchall())

    books = {row["id"]: row["title"] for row in book_rows}
    nationalities = {row["id"]: row["name"] for row in nationality_rows}
    connections = {}

    for row in citation_rows:
        book_id = row["book_id"]
        nationality_id = row["nationality_id"]
        count = row["citation_count"]
        if book_id not in books or nationality_id not in nationalities:
            continue
        key = (book_id, nationality_id)
        entry = connections.setdefault(key, {"citations": 0, "epigraphs": 0})
        entry["citations"] = count

    for row in epigraph_rows:
        book_id = row["book_id"]
        nationality_id = row["nationality_id"]
        count = row["epigraph_count"]
        if book_id not in books or nationality_id not in nationalities:
            continue
        key = (book_id, nationality_id)
        entry = connections.setdefault(key, {"citations": 0, "epigraphs": 0})
        entry["epigraphs"] = count

    chords = []
    for (book_id, nationality_id), counts in connections.items():
        total = counts["citations"] + counts["epigraphs"]
        if not total:
            continue
        chords.append({
            "book": {"id": book_id, "title": books[book_id]},
            "nationality": {"id": nationality_id, "name": nationalities[nationality_id]},
            "citations": counts["citations"],
            "epigraphs": counts["epigraphs"],
            "total": total,
        })

    return {
        "books": book_rows,
        "nationalities": nationality_rows,
        "connections": chords,
    }


def get_graph_elements():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "SELECT id, title FROM books ORDER BY title")
            book_rows = _rows_to_dicts(cursor.fetchall())

            _execute(cursor, "SELECT id, name FROM people ORDER BY name")
            person_rows = _rows_to_dicts(cursor.fetchall())

            _execute(cursor, "SELECT person_id, book_id, indirect_citation FROM citations")
            citation_rows = _rows_to_dicts(cursor.fetchall())

            _execute(cursor, "SELECT author_id, book_id FROM epigraphs")
            epigraph_rows = _rows_to_dicts(cursor.fetchall())

    nodes = []
    edges = []

    for row in book_rows:
        book_id = row["id"]
        nodes.append({
            "id": f"book-{book_id}",
            "label": row["title"],
            "type": "book",
            "entity_id": book_id,
        })

    for row in person_rows:
        person_id = row["id"]
        nodes.append({
            "id": f"person-{person_id}",
            "label": row["name"],
            "type": "person",
            "entity_id": person_id,
        })

    for row in citation_rows:
        person_id = row["person_id"]
        book_id = row["book_id"]
        indirect = row["indirect_citation"]
        edges.append({
            "source": f"book-{book_id}",
            "target": f"person-{person_id}",
            "kind": "citation",
            "indirect": bool(indirect),
        })

    for row in epigraph_rows:
        person_id = row["author_id"]
        book_id = row["book_id"]
        edges.append({
            "source": f"person-{person_id}",
            "target": f"book-{book_id}",
            "kind": "epigraph",
        })

    return {"nodes": nodes, "edges": edges}


def get_people_type_distribution():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT pt.id AS id, pt.name AS name, COUNT(p.id) AS total
                FROM person_types pt
                LEFT JOIN people p ON p.type_id = pt.id
                GROUP BY pt.id, pt.name
                ORDER BY total DESC, pt.name
                """,
            )
            return _rows_to_dicts(cursor.fetchall())


def get_nationality_distribution():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(
                cursor,
                """
                SELECT n.id AS id, n.name AS name, COUNT(p.id) AS total
                FROM nationalities n
                LEFT JOIN people p ON p.nationality_id = n.id
                GROUP BY n.id, n.name
                ORDER BY total DESC, n.name
                """,
            )
            return _rows_to_dicts(cursor.fetchall())


def get_global_counts():
    with get_connection() as conn:
        with _cursor(conn) as cursor:
            _execute(cursor, "SELECT COUNT(*) AS total FROM books")
            books = (cursor.fetchone() or {"total": 0})["total"]

            _execute(cursor, "SELECT COUNT(*) AS total FROM citations")
            citations = (cursor.fetchone() or {"total": 0})["total"]

            _execute(cursor, "SELECT COUNT(*) AS total FROM epigraphs")
            epigraphs = (cursor.fetchone() or {"total": 0})["total"]

            _execute(cursor, "SELECT COUNT(*) AS total FROM people")
            people = (cursor.fetchone() or {"total": 0})["total"]

            _execute(cursor, "SELECT COUNT(*) AS total FROM person_types")
            person_types = (cursor.fetchone() or {"total": 0})["total"]

            _execute(cursor, "SELECT COUNT(*) AS total FROM nationalities")
            nationalities = (cursor.fetchone() or {"total": 0})["total"]

    return {
        "books": books,
        "citations": citations,
        "epigraphs": epigraphs,
        "people": people,
        "person_types": person_types,
        "nationalities": nationalities,
    }
