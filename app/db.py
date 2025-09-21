import sqlite3
from pathlib import Path

DB_PATH = Path("instance/referent.sqlite3")


def get_connection():
    return sqlite3.connect(DB_PATH)


def _ensure_book_schema():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(books)")
        columns = {row[1] for row in cursor.fetchall()}
        if "is_complete" not in columns:
            cursor.execute("ALTER TABLE books ADD COLUMN is_complete INTEGER NOT NULL DEFAULT 0")
            conn.commit()


def init_db():
    with get_connection() as conn:
        with open("schema.sql") as f:
            conn.executescript(f.read())
        conn.commit()


# ---------- BOOKS ----------
def add_book(title, publication_year=None, isbn=None, is_complete=False):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO books (title, publication_year, isbn, is_complete, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (title, publication_year, isbn, int(bool(is_complete))))
        return cursor.lastrowid


def update_book(book_id, title, publication_year=None, isbn=None, is_complete=False):
    with get_connection() as conn:
        conn.execute("""
            UPDATE books
            SET title = ?,
                publication_year = ?,
                isbn = ?,
                is_complete = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, publication_year, isbn, int(bool(is_complete)), book_id))


def get_books(include_completed=True, ensure_ids=None):
    ensure_ids = [int(i) for i in ensure_ids or []]
    with get_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT
                b.id,
                b.title,
                b.publication_year,
                b.isbn,
                authors.names AS authors,
                translators.names AS translators,
                COALESCE(c_counts.citation_count, 0) AS citation_count,
                COALESCE(e_counts.epigraph_count, 0) AS epigraph_count,
                b.is_complete
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
        return cursor.fetchall()


def get_book_by_id(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                b.id,
                b.title,
                b.publication_year,
                b.isbn,
                authors.names AS authors,
                translators.names AS translators,
                b.is_complete
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
        return cursor.fetchone()


# ---------- PERSON TYPES ----------
def add_person_type(name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO person_types (name, created_at, updated_at) VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name,))
        conn.commit()
        cursor.execute("SELECT id FROM person_types WHERE name = ?", (name,))
        return cursor.fetchone()[0]


def get_person_types():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM person_types ORDER BY name")
        return cursor.fetchall()


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
        return row[0] if row else None


def get_nationalities():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM nationalities ORDER BY name")
        return cursor.fetchall()


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
        return row[0]

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
        "SELECT bc.role, p.id, p.name",
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
        return cursor.fetchall()


# ---------- PEOPLE ----------
def add_person(name, wiki_url, bio_summary, type_id=None, nationality_id=None, birth_year=None, death_year=None, notes=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO people (name, wiki_url, bio_summary, type_id, nationality_id, birth_year, death_year, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name, wiki_url, bio_summary, type_id, nationality_id, birth_year, death_year, notes))
        return cursor.lastrowid


def get_people(search_term=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT
                people.id,
                people.name,
                person_types.name AS type,
                people.wiki_url,
                COUNT(DISTINCT citations.id) AS citation_count,
                COUNT(DISTINCT epigraphs.id) AS epigraph_count,
                nationalities.name AS nationality
            FROM people
            LEFT JOIN person_types ON people.type_id = person_types.id
            LEFT JOIN citations ON people.id = citations.person_id
            LEFT JOIN epigraphs ON people.id = epigraphs.author_id
            LEFT JOIN nationalities ON people.nationality_id = nationalities.id
        """
        params = []
        if search_term:
            query += " WHERE LOWER(people.name) LIKE ?"
            params.append(f"%{search_term.lower()}%")
        query += " GROUP BY people.id ORDER BY people.name"
        cursor.execute(query, params)
        return cursor.fetchall()

def get_person_by_id(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                people.id,
                people.name,
                people.type_id,
                people.wiki_url,
                people.bio_summary,
                people.birth_year,
                people.death_year,
                people.notes,
                person_types.name AS type_name,
                people.nationality_id,
                nationalities.name AS nationality_name
            FROM people
            LEFT JOIN person_types ON people.type_id = person_types.id
            LEFT JOIN nationalities ON people.nationality_id = nationalities.id
            WHERE people.id = ?
            """,
            (person_id,)
        )
        return cursor.fetchone()

def update_person(person_id, name, type_id, nationality_id, birth_year, death_year, notes, wiki_url=None, bio_summary=None):
    with get_connection() as conn:
        conn.execute("""
            UPDATE people
            SET name = ?,
                type_id = ?,
                nationality_id = ?,
                birth_year = ?,
                death_year = ?,
                notes = ?,
                wiki_url = ?,
                bio_summary = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (name, type_id, nationality_id, birth_year, death_year, notes, wiki_url, bio_summary, person_id))

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
            SELECT c.id, p.name, b.title, c.page_number, b.id, c.notes, c.indirect_citation
            FROM citations c
            JOIN people p ON c.person_id = p.id
            JOIN books b ON c.book_id = b.id
            ORDER BY c.updated_at DESC
        """)
        return cursor.fetchall()


def get_citation_by_id(citation_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, person_id, book_id, page_number, notes, indirect_citation
            FROM citations
            WHERE id = ?
        """, (citation_id,))
        return cursor.fetchone()

def get_citations_by_book(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                c.id,
                p.name,
                c.page_number,
                p.id,
                c.notes,
                c.indirect_citation
            FROM citations c
            JOIN people p ON c.person_id = p.id
            WHERE c.book_id = ?
            ORDER BY c.page_number
        """, (book_id,))
        return cursor.fetchall()

def get_citations_by_person(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, p.name, b.title, c.page_number, b.id, c.notes, c.indirect_citation
            FROM citations c
            JOIN people p ON c.person_id = p.id
            JOIN books b ON c.book_id = b.id
            WHERE c.person_id = ?
            ORDER BY b.title, c.page_number
        """, (person_id,))
        return cursor.fetchall()

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
                e.id,
                b.id,
                b.title,
                p.id,
                p.name,
                e.quote,
                e.notes,
                e.created_at
            FROM epigraphs e
            JOIN books b ON e.book_id = b.id
            JOIN people p ON e.author_id = p.id
            ORDER BY b.title, e.created_at DESC
        """)
        return cursor.fetchall()


def get_epigraph_by_id(epigraph_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, book_id, author_id, quote, notes
            FROM epigraphs
            WHERE id = ?
        """, (epigraph_id,))
        return cursor.fetchone()


def get_epigraphs_by_book(book_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                e.id,
                e.quote,
                e.notes,
                p.name,
                p.id,
                e.created_at
            FROM epigraphs e
            JOIN people p ON e.author_id = p.id
            WHERE e.book_id = ?
            ORDER BY e.created_at
        """, (book_id,))
        return cursor.fetchall()


def get_epigraphs_by_person(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                e.id,
                e.quote,
                e.notes,
                b.title,
                b.id,
                e.created_at
            FROM epigraphs e
            JOIN books b ON e.book_id = b.id
            WHERE e.author_id = ?
            ORDER BY e.created_at
        """, (person_id,))
        return cursor.fetchall()


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
            SELECT bc.role, b.id, b.title
            FROM book_contributors bc
            JOIN books b ON b.id = bc.book_id
            WHERE bc.person_id = ?
            ORDER BY CASE bc.role WHEN 'author' THEN 0 WHEN 'translator' THEN 1 ELSE 2 END, b.title COLLATE NOCASE
        """, (person_id,))
        return cursor.fetchall()


_ensure_book_schema()
