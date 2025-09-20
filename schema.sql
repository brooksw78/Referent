-- Books table
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    publication_year TEXT,
    isbn TEXT,
    cover_url TEXT
);

-- Authors table
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

-- Join table: Books ↔ Authors (many-to-many)
CREATE TABLE IF NOT EXISTS book_authors (
    book_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    PRIMARY KEY (book_id, author_id),
    FOREIGN KEY (book_id) REFERENCES books (id),
    FOREIGN KEY (author_id) REFERENCES authors (id)
);

-- Translators table
CREATE TABLE IF NOT EXISTS translators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

-- Join table: Books ↔ Translators (many-to-many)
CREATE TABLE IF NOT EXISTS book_translators (
    book_id INTEGER NOT NULL,
    translator_id INTEGER NOT NULL,
    PRIMARY KEY (book_id, translator_id),
    FOREIGN KEY (book_id) REFERENCES books (id),
    FOREIGN KEY (translator_id) REFERENCES translators (id)
);

-- Person Types table (e.g., "Philosopher", "Politician")
CREATE TABLE IF NOT EXISTS person_types (
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
    birth_year INTEGER,
    death_year INTEGER,
    FOREIGN KEY (type_id) REFERENCES person_types(id)
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