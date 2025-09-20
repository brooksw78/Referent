import sqlite3
from pathlib import Path

DB_PATH = Path("instance/referent.sqlite3")


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        with open("schema.sql") as f:
            conn.executescript(f.read())
        conn.commit()


# ---------- BOOKS ----------
def add_book(title, publication_year=None, isbn=None, cover_url=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO books (title, publication_year, isbn, cover_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (title, publication_year, isbn, cover_url))
        return cursor.lastrowid


def get_books():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                b.id,
                b.title,
                b.publication_year,
                b.isbn,
                b.cover_url,
                replace(GROUP_CONCAT(DISTINCT a.name),',',', ') AS authors,
                replace(GROUP_CONCAT(DISTINCT t.name),',',', ') AS translators,
                COUNT(DISTINCT c.id) AS citation_count
            FROM books b
            LEFT JOIN book_authors ba ON b.id = ba.book_id
            LEFT JOIN authors a ON ba.author_id = a.id
            LEFT JOIN book_translators bt ON b.id = bt.book_id
            LEFT JOIN translators t ON bt.translator_id = t.id
            LEFT JOIN citations c ON b.id = c.book_id
            GROUP BY b.id
            ORDER BY b.title
        """)
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
                b.cover_url,
                GROUP_CONCAT(DISTINCT a.name) AS authors,
                GROUP_CONCAT(DISTINCT t.name) AS translators
            FROM books b
            LEFT JOIN book_authors ba ON b.id = ba.book_id
            LEFT JOIN authors a ON ba.author_id = a.id
            LEFT JOIN book_translators bt ON b.id = bt.book_id
            LEFT JOIN translators t ON bt.translator_id = t.id
            WHERE b.id = ?
            GROUP BY b.id
        """, (book_id,))
        return cursor.fetchone()


# ---------- AUTHORS ----------
def add_author(name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO authors (name, created_at, updated_at) VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name,))
        conn.commit()
        cursor.execute("SELECT id FROM authors WHERE name = ?", (name,))
        return cursor.fetchone()[0]


def link_author_to_book(book_id, author_id):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO book_authors (book_id, author_id)
            VALUES (?, ?)
        """, (book_id, author_id))


# ---------- TRANSLATORS ----------
def add_translator(name):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO translators (name) VALUES (?)
        """, (name,))
        conn.commit()
        cursor.execute("SELECT id FROM translators WHERE name = ?", (name,))
        return cursor.fetchone()[0]


def link_translator_to_book(book_id, translator_id):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO book_translators (book_id, translator_id)
            VALUES (?, ?)
        """, (book_id, translator_id))


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


# ---------- PEOPLE ----------
def add_person(name, wiki_url, bio_summary, type_id=None, birth_year=None, death_year=None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO people (name, wiki_url, bio_summary, type_id, birth_year, death_year, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name, wiki_url, bio_summary, type_id, birth_year, death_year))
        return cursor.lastrowid


def get_people():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                people.id,
                people.name,
                person_types.name AS type,
                people.wiki_url,
                COUNT(citations.id) AS citation_count
            FROM people
            LEFT JOIN person_types ON people.type_id = person_types.id
            LEFT JOIN citations ON people.id = citations.person_id
            GROUP BY people.id
            ORDER BY people.name
        """)
        return cursor.fetchall()

def get_person_by_id(person_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, type_id, wiki_url, bio_summary FROM people WHERE id = ?", (person_id,))
        return cursor.fetchone()

def update_person(person_id, name, type_id):
    with get_connection() as conn:
        conn.execute("""
            UPDATE people SET name = ?, type_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
        """, (name, type_id, person_id))

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