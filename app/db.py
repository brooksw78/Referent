import sqlite3
from pathlib import Path

DB_PATH = Path("instance/referent.sqlite3")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def _ensure_book_schema():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(books)")
        columns = {row[1] for row in cursor.fetchall()}
        updates = []
        if "is_complete" not in columns:
            updates.append("ALTER TABLE books ADD COLUMN is_complete INTEGER NOT NULL DEFAULT 0")
        if "cover_image_path" not in columns:
            updates.append("ALTER TABLE books ADD COLUMN cover_image_path TEXT")
        for statement in updates:
            cursor.execute(statement)
        if updates:
            conn.commit()


def _ensure_person_schema():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(people)")
        columns = {row[1] for row in cursor.fetchall()}
        updates = []
        if "sex" not in columns:
            updates.append("ALTER TABLE people ADD COLUMN sex TEXT")
        if "birth_year_era" not in columns:
            updates.append("ALTER TABLE people ADD COLUMN birth_year_era TEXT NOT NULL DEFAULT 'AD'")
        if "death_year_era" not in columns:
            updates.append("ALTER TABLE people ADD COLUMN death_year_era TEXT NOT NULL DEFAULT 'AD'")
        for statement in updates:
            cursor.execute(statement)
        if updates:
            conn.commit()


def init_db():
    with get_connection() as conn:
        with open("schema.sql") as f:
            conn.executescript(f.read())
        conn.commit()


# ---------- BOOKS ----------
def add_book(title, publication_year=None, isbn=None, is_complete=False, cover_url=None, cover_image_path=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO books (title, publication_year, isbn, is_complete, cover_url, cover_image_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (title, publication_year, isbn, int(bool(is_complete)), cover_url, cover_image_path))
        return cursor.lastrowid


def update_book(book_id, title, publication_year=None, isbn=None, is_complete=False, cover_url=None, cover_image_path=None):
    with get_connection() as conn:
        conn.execute("""
            UPDATE books
            SET title = ?,
                publication_year = ?,
                isbn = ?,
                is_complete = ?,
                cover_url = ?,
                cover_image_path = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, publication_year, isbn, int(bool(is_complete)), cover_url, cover_image_path, book_id))


def get_books(include_completed=True, ensure_ids=None):
    ensure_ids = [int(i) for i in ensure_ids or []]
    with get_connection() as conn:
        cursor = conn.cursor()

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
                    REPLACE(GROUP_CONCAT(DISTINCT p.name), ',', ', ') AS names,
                    REPLACE(GROUP_CONCAT(DISTINCT p.id || '::' || p.name), ',', '|') AS ids
                FROM book_contributors bc
                JOIN people p ON p.id = bc.person_id
                WHERE bc.role = 'author'
                GROUP BY bc.book_id
            ) AS authors ON authors.book_id = b.id
            LEFT JOIN (
                SELECT
                    bc.book_id,
                    REPLACE(GROUP_CONCAT(DISTINCT p.name), ',', ', ') AS names,
                    REPLACE(GROUP_CONCAT(DISTINCT p.id || '::' || p.name), ',', '|') AS ids
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
                placeholders = ", ".join("?" for _ in ensure_ids)
                conditions.append(f"(b.is_complete = 0 OR b.id IN ({placeholders}))")
                params.extend(ensure_ids)
            else:
                conditions.append("b.is_complete = 0")

        if conditions:
            query += "\nWHERE " + " AND ".join(conditions)

        query += "\nORDER BY b.title"

        cursor.execute(query, params)
        return _rows_to_dicts(cursor.fetchall())


def get_book_by_id(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
                SELECT bc.book_id, REPLACE(GROUP_CONCAT(DISTINCT p.name), ',', ', ') AS names
                FROM book_contributors bc
                JOIN people p ON p.id = bc.person_id
                WHERE bc.role = 'author'
                GROUP BY bc.book_id
            ) AS authors ON authors.book_id = b.id
            LEFT JOIN (
                SELECT bc.book_id, REPLACE(GROUP_CONCAT(DISTINCT p.name), ',', ', ') AS names
                FROM book_contributors bc
                JOIN people p ON p.id = bc.person_id
                WHERE bc.role = 'translator'
                GROUP BY bc.book_id
            ) AS translators ON translators.book_id = b.id
            WHERE b.id = ?
        """, (book_id,))
        return _row_to_dict(cursor.fetchone())


# ---------- PERSON TYPES ----------
def add_person_type(name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO person_types (name, created_at, updated_at) VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name,))
        conn.commit()
        cursor.execute("SELECT id FROM person_types WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row["id"] if row else None


def update_person_type(type_id, name):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE person_types
            SET name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, type_id),
        )


def delete_person_type(type_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM person_types WHERE id = ?", (type_id,))


def get_person_types():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT pt.id AS id, pt.name AS name, COUNT(p.id) AS usage_count
            FROM person_types pt
            LEFT JOIN people p ON p.type_id = pt.id
            GROUP BY pt.id, pt.name
            ORDER BY pt.name
            """
        )
        return _rows_to_dicts(cursor.fetchall())


# ---------- NATIONALITIES ----------
def add_nationality(name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO nationalities (name)
            VALUES (?)
        """, (name,))
        conn.commit()
        cursor.execute("SELECT id FROM nationalities WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row["id"] if row else None


def get_nationalities():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT n.id AS id, n.name AS name, COUNT(p.id) AS usage_count
            FROM nationalities n
            LEFT JOIN people p ON p.nationality_id = n.id
            GROUP BY n.id, n.name
            ORDER BY n.name
            """
        )
        return _rows_to_dicts(cursor.fetchall())


def update_nationality(nationality_id, name):
    with get_connection() as conn:
        conn.execute(
            "UPDATE nationalities SET name = ? WHERE id = ?",
            (name, nationality_id)
        )


def delete_nationality(nationality_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM nationalities WHERE id = ?", (nationality_id,))


def _get_person_type_id(type_name):
    if not type_name:
        return None
    type_name = type_name.strip()
    if not type_name:
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM person_types WHERE name = ?", (type_name,))
        row = cursor.fetchone()

    if row:
        return row["id"]

    return add_person_type(type_name)


def get_or_create_person(name, default_type=None):
    normalized = (name or "").strip()
    if not normalized:
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, type_id FROM people WHERE LOWER(name) = LOWER(?)",
            (normalized,)
        )
        row = cursor.fetchone()

        if row:
            person_id, current_type_id = row
            if default_type and current_type_id is None:
                type_id = _get_person_type_id(default_type)
                if type_id is not None:
                    conn.execute(
                        "UPDATE people SET type_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (type_id, person_id)
                    )
            return person_id

        type_id = _get_person_type_id(default_type) if default_type else None
        cursor.execute(
            """
            INSERT INTO people (name, wiki_url, bio_summary, type_id, nationality_id, birth_year, death_year, notes, created_at, updated_at)
            VALUES (?, NULL, NULL, ?, NULL, NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (normalized, type_id)
        )
        return cursor.lastrowid


def add_book_contributor(book_id, person_id, role):
    if not person_id or not role:
        return
    role = role.lower()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO book_contributors (book_id, person_id, role)
            VALUES (?, ?, ?)
            """,
            (book_id, person_id, role)
        )


def remove_book_contributor(book_id, person_id, role=None):
    if not person_id:
        return
    query = "DELETE FROM book_contributors WHERE book_id = ? AND person_id = ?"
    params = [book_id, person_id]
    if role:
        query += " AND role = ?"
        params.append(role.lower())
    with get_connection() as conn:
        conn.execute(query, params)


def get_book_contributors(book_id, role=None):
    query = [
        "SELECT",
        "    bc.role AS role,",
        "    p.id AS person_id,",
        "    p.name AS person_name",
        "FROM book_contributors bc",
        "JOIN people p ON p.id = bc.person_id",
        "WHERE bc.book_id = ?"
    ]
    params = [book_id]

    if role:
        query.append("AND bc.role = ?")
        params.append(role.lower())

    query.append(
        "ORDER BY CASE bc.role WHEN 'author' THEN 0 WHEN 'translator' THEN 1 ELSE 2 END, p.name COLLATE NOCASE"
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("\n".join(query), params)
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
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO people (
                name,
                wiki_url,
                bio_summary,
                type_id,
                nationality_id,
                sex,
                birth_year,
                death_year,
                birth_year_era,
                death_year_era,
                notes,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name, wiki_url, bio_summary, type_id, nationality_id, sex, birth_year, death_year, birth_year_era or "AD", death_year_era or "AD", notes))
        return cursor.lastrowid


def get_people(search_term=None, type_id=None, nationality_id=None):
    with get_connection() as conn:
        cursor = conn.cursor()
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
            conditions.append("LOWER(people.name) LIKE ?")
            params.append(f"%{search_term.lower()}%")
        if type_id is not None:
            conditions.append("people.type_id = ?")
            params.append(int(type_id))
        if nationality_id is not None:
            conditions.append("people.nationality_id = ?")
            params.append(int(nationality_id))
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " GROUP BY people.id ORDER BY people.name"
        cursor.execute(query, params)
        return _rows_to_dicts(cursor.fetchall())

def get_person_by_id(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
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
            WHERE people.id = ?
            """,
            (person_id,)
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
        conn.execute("""
            UPDATE people
            SET name = ?,
                type_id = ?,
                nationality_id = ?,
                sex = ?,
                birth_year = ?,
                death_year = ?,
                birth_year_era = ?,
                death_year_era = ?,
                notes = ?,
                wiki_url = ?,
                bio_summary = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (name, type_id, nationality_id, sex, birth_year, death_year, birth_year_era or "AD", death_year_era or "AD", notes, wiki_url, bio_summary, person_id))

def delete_person(person_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        
def person_exists(name):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM people WHERE name = ?", (name.strip(),))
        return cur.fetchone() is not None

# ---------- CITATIONS ----------
def add_citation(person_id, book_id, page_number, indirect_citation, notes=None):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO citations (person_id, book_id, page_number, indirect_citation, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (person_id, book_id, page_number, indirect_citation, notes))


def get_citations():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
        """)
        return _rows_to_dicts(cursor.fetchall())


def get_citation_by_id(citation_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id,
                person_id,
                book_id,
                page_number,
                notes,
                indirect_citation
            FROM citations
            WHERE id = ?
        """, (citation_id,))
        return _row_to_dict(cursor.fetchone())

def get_citations_by_book(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
            WHERE c.book_id = ?
            ORDER BY
                CASE
                    WHEN TRIM(c.page_number) GLOB '[0-9]*' AND TRIM(c.page_number) <> ''
                        THEN CAST(TRIM(c.page_number) AS INTEGER)
                    ELSE NULL
                END,
                TRIM(c.page_number)
        """, (book_id,))
        return _rows_to_dicts(cursor.fetchall())

def get_citations_by_person(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
            WHERE c.person_id = ?
            ORDER BY b.title, c.page_number
        """, (person_id,))
        return _rows_to_dicts(cursor.fetchall())

def update_citation(citation_id, person_id, book_id, page_number, indirect_citation, notes):
    with get_connection() as conn:
        conn.execute("""
            UPDATE citations
            SET person_id = ?, book_id = ?, page_number = ?, notes = ?, indirect_citation = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (person_id, book_id, page_number, notes, indirect_citation, citation_id))


# ---------- EPIGRAPHS ----------
def add_epigraph(book_id, author_id, quote, notes=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO epigraphs (book_id, author_id, quote, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (book_id, author_id, quote, notes))
        return cursor.lastrowid


def get_epigraphs():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
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
        """)
        return _rows_to_dicts(cursor.fetchall())


def get_epigraph_by_id(epigraph_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id,
                book_id,
                author_id,
                quote,
                notes
            FROM epigraphs
            WHERE id = ?
        """, (epigraph_id,))
        return _row_to_dict(cursor.fetchone())


def get_epigraphs_by_book(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                e.id AS id,
                e.quote AS quote,
                e.notes AS notes,
                p.name AS author_name,
                p.id AS author_id,
                e.created_at AS created_at
            FROM epigraphs e
            JOIN people p ON e.author_id = p.id
            WHERE e.book_id = ?
            ORDER BY e.created_at
        """, (book_id,))
        return _rows_to_dicts(cursor.fetchall())


def get_epigraphs_by_person(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                e.id AS id,
                e.quote AS quote,
                e.notes AS notes,
                b.title AS book_title,
                b.id AS book_id,
                e.created_at AS created_at
            FROM epigraphs e
            JOIN books b ON e.book_id = b.id
            WHERE e.author_id = ?
            ORDER BY e.created_at
        """, (person_id,))
        return _rows_to_dicts(cursor.fetchall())


def update_epigraph(epigraph_id, book_id, author_id, quote, notes):
    with get_connection() as conn:
        conn.execute("""
            UPDATE epigraphs
            SET book_id = ?, author_id = ?, quote = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (book_id, author_id, quote, notes, epigraph_id))


def delete_epigraph(epigraph_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM epigraphs WHERE id = ?", (epigraph_id,))


def get_book_contributions_by_person(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                bc.role AS role,
                b.id AS book_id,
                b.title AS book_title,
                b.cover_url AS cover_url,
                b.cover_image_path AS cover_image_path
            FROM book_contributors bc
            JOIN books b ON b.id = bc.book_id
            WHERE bc.person_id = ?
            ORDER BY CASE bc.role WHEN 'author' THEN 0 WHEN 'translator' THEN 1 ELSE 2 END, b.title COLLATE NOCASE
        """, (person_id,))
        return _rows_to_dicts(cursor.fetchall())


def get_book_summary(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT pt.id AS id, pt.name AS name, SUM(cnt) AS total
            FROM (
                SELECT p.type_id AS type_id, COUNT(*) AS cnt
                FROM citations c
                JOIN people p ON p.id = c.person_id
                WHERE c.book_id = ?
                GROUP BY p.type_id
                UNION ALL
                SELECT p.type_id AS type_id, COUNT(*) AS cnt
                FROM epigraphs e
                JOIN people p ON p.id = e.author_id
                WHERE e.book_id = ?
                GROUP BY p.type_id
            ) agg
            JOIN person_types pt ON pt.id = agg.type_id
            GROUP BY pt.id, pt.name
            ORDER BY total DESC, pt.name
            """,
            (book_id, book_id),
        )
        type_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute(
            """
            SELECT n.id AS id, n.name AS name, SUM(cnt) AS total
            FROM (
                SELECT p.nationality_id AS nationality_id, COUNT(*) AS cnt
                FROM citations c
                JOIN people p ON p.id = c.person_id
                WHERE c.book_id = ?
                GROUP BY p.nationality_id
                UNION ALL
                SELECT p.nationality_id AS nationality_id, COUNT(*) AS cnt
                FROM epigraphs e
                JOIN people p ON p.id = e.author_id
                WHERE e.book_id = ?
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
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS total FROM citations WHERE book_id = ?", (book_id,))
        citation_total = (cursor.fetchone() or {"total": 0})["total"]

        cursor.execute(
            "SELECT COUNT(DISTINCT person_id) AS distinct_people FROM citations WHERE book_id = ?",
            (book_id,),
        )
        distinct_people = (cursor.fetchone() or {"distinct_people": 0})["distinct_people"]

        cursor.execute(
            """
            SELECT COUNT(DISTINCT c1.person_id) AS shared_people
            FROM citations c1
            WHERE c1.book_id = ?
              AND EXISTS (
                SELECT 1
                FROM citations c2
                WHERE c2.person_id = c1.person_id
                  AND c2.book_id <> ?
              )
            """,
            (book_id, book_id),
        )
        shared_referents = (cursor.fetchone() or {"shared_people": 0})["shared_people"]

    unique_to_book = max(distinct_people - shared_referents, 0)

    return {
        "total_referents": citation_total,
        "unique_referents": unique_to_book,
        "shared_referents": shared_referents or 0,
    }


def get_book_people_lifetimes(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
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
                SELECT person_id FROM citations WHERE book_id = ?
                UNION
                SELECT author_id FROM epigraphs WHERE book_id = ?
            )
            ORDER BY
                CASE WHEN p.birth_year IS NULL THEN 1 ELSE 0 END,
                p.birth_year,
                p.name COLLATE NOCASE
            """,
            (book_id, book_id),
        )
        return _rows_to_dicts(cursor.fetchall())


def get_books_with_shared_referents(book_id, limit=6):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            WITH target_people AS (
                SELECT person_id
                FROM citations
                WHERE book_id = ?
                  AND person_id IS NOT NULL
                  AND TRIM(CAST(person_id AS TEXT)) <> ''
                UNION
                SELECT author_id AS person_id
                FROM epigraphs
                WHERE book_id = ?
                  AND author_id IS NOT NULL
                  AND TRIM(CAST(author_id AS TEXT)) <> ''
            ),
            other_references AS (
                SELECT c.book_id AS book_id, c.person_id AS person_id
                FROM citations c
                WHERE c.book_id <> ? AND c.person_id IN (SELECT person_id FROM target_people)
                UNION
                SELECT e.book_id AS book_id, e.author_id AS person_id
                FROM epigraphs e
                WHERE e.book_id <> ? AND e.author_id IN (SELECT person_id FROM target_people)
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
                    GROUP_CONCAT(name, '||') AS names
                FROM (
                    SELECT DISTINCT o.book_id AS book_id, p.name AS name
                    FROM other_references o
                    JOIN people p ON p.id = o.person_id
                    ORDER BY name COLLATE NOCASE
                )
                GROUP BY book_id
            )
            SELECT
                b.id AS book_id,
                b.title AS title,
                COUNT(DISTINCT other_references.person_id) AS shared_count,
                COALESCE(aggregate_totals.total_people, 0) AS other_total,
                current_totals.total_people AS current_total,
                COALESCE(shared_people.names, '') AS shared_names
            FROM other_references
            JOIN books b ON b.id = other_references.book_id
            LEFT JOIN aggregate_totals ON aggregate_totals.book_id = other_references.book_id
            LEFT JOIN shared_people ON shared_people.book_id = other_references.book_id
            CROSS JOIN current_totals
            GROUP BY
                b.id,
                b.title,
                aggregate_totals.total_people,
                current_totals.total_people,
                shared_people.names
            ORDER BY shared_count DESC, b.title COLLATE NOCASE
            LIMIT ?
            """,
            (book_id, book_id, book_id, book_id, int(limit)),
        )
        return _rows_to_dicts(cursor.fetchall())


def get_chord_data():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id, title FROM books ORDER BY title")
        book_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute("SELECT id, name FROM person_types ORDER BY name")
        type_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute(
            """
            SELECT c.book_id AS book_id, pt.id AS type_id, COUNT(*) AS citation_count
            FROM citations c
            JOIN people p ON p.id = c.person_id
            LEFT JOIN person_types pt ON pt.id = p.type_id
            WHERE pt.id IS NOT NULL
            GROUP BY c.book_id, pt.id
            """
        )
        citation_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute(
            """
            SELECT e.book_id AS book_id, pt.id AS type_id, COUNT(*) AS epigraph_count
            FROM epigraphs e
            JOIN people p ON p.id = e.author_id
            LEFT JOIN person_types pt ON pt.id = p.type_id
            WHERE pt.id IS NOT NULL
            GROUP BY e.book_id, pt.id
            """
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
        cursor = conn.cursor()

        cursor.execute("SELECT id, title FROM books ORDER BY title")
        book_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute("SELECT id, name FROM nationalities ORDER BY name")
        nationality_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute(
            """
            SELECT c.book_id AS book_id, n.id AS nationality_id, COUNT(*) AS citation_count
            FROM citations c
            JOIN people p ON p.id = c.person_id
            LEFT JOIN nationalities n ON n.id = p.nationality_id
            WHERE n.id IS NOT NULL
            GROUP BY c.book_id, n.id
            """
        )
        citation_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute(
            """
            SELECT e.book_id AS book_id, n.id AS nationality_id, COUNT(*) AS epigraph_count
            FROM epigraphs e
            JOIN people p ON p.id = e.author_id
            LEFT JOIN nationalities n ON n.id = p.nationality_id
            WHERE n.id IS NOT NULL
            GROUP BY e.book_id, n.id
            """
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
        cursor = conn.cursor()

        cursor.execute("SELECT id, title FROM books ORDER BY title")
        book_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute("SELECT id, name FROM people ORDER BY name")
        person_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute(
            "SELECT person_id, book_id, indirect_citation FROM citations"
        )
        citation_rows = _rows_to_dicts(cursor.fetchall())

        cursor.execute(
            "SELECT author_id, book_id FROM epigraphs"
        )
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
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT pt.id AS id, pt.name AS name, COUNT(p.id) AS total
            FROM person_types pt
            LEFT JOIN people p ON p.type_id = pt.id
            GROUP BY pt.id, pt.name
            ORDER BY total DESC, pt.name
            """
        )
        return _rows_to_dicts(cursor.fetchall())


def get_nationality_distribution():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT n.id AS id, n.name AS name, COUNT(p.id) AS total
            FROM nationalities n
            LEFT JOIN people p ON p.nationality_id = n.id
            GROUP BY n.id, n.name
            ORDER BY total DESC, n.name
            """
        )
        return _rows_to_dicts(cursor.fetchall())


def get_global_counts():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM books")
        books = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM citations")
        citations = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM epigraphs")
        epigraphs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM people")
        people = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM person_types")
        person_types = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM nationalities")
        nationalities = cursor.fetchone()[0]

    return {
        "books": books,
        "citations": citations,
        "epigraphs": epigraphs,
        "people": people,
        "person_types": person_types,
        "nationalities": nationalities,
    }


_ensure_book_schema()
_ensure_person_schema()
