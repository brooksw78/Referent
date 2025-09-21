-- Books table
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    publication_year TEXT,
    isbn TEXT,
    is_complete INTEGER NOT NULL DEFAULT 0,
    cover_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Person Types table (e.g., "Philosopher", "Politician")
CREATE TABLE IF NOT EXISTS person_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- Nationalities table
CREATE TABLE IF NOT EXISTS nationalities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- People table (referenced figures)
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    wiki_url TEXT,
    bio_summary TEXT,
    type_id INTEGER,
    nationality_id INTEGER,
    birth_year INTEGER,
    death_year INTEGER,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (type_id) REFERENCES person_types(id),
    FOREIGN KEY (nationality_id) REFERENCES nationalities(id)
);
-- Citations table (person mentioned in a book, on a page)
CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    page_number TEXT,
    FOREIGN KEY (person_id) REFERENCES people (id),
    FOREIGN KEY (book_id) REFERENCES books (id)
);

-- Epigraphs table
CREATE TABLE IF NOT EXISTS epigraphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    quote TEXT NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books (id),
    FOREIGN KEY (author_id) REFERENCES people (id)
);

-- Book contributors (authors, translators, etc.)
CREATE TABLE IF NOT EXISTS book_contributors (
    book_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (book_id, person_id, role),
    FOREIGN KEY (book_id) REFERENCES books (id),
    FOREIGN KEY (person_id) REFERENCES people (id)
);
