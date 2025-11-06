BEGIN;

-- Optional: comment out if running without database roles
SET ROLE referent_user;

-- Track applied migrations when using apply_migrations.py
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Books table
CREATE TABLE IF NOT EXISTS books (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    publication_year TEXT,
    isbn TEXT,
    is_complete BOOLEAN NOT NULL DEFAULT FALSE,
    cover_url TEXT,
    cover_image_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Person Types table (e.g., "Philosopher", "Politician")
CREATE TABLE IF NOT EXISTS person_types (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Nationalities table
CREATE TABLE IF NOT EXISTS nationalities (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- People table (referenced figures)
CREATE TABLE IF NOT EXISTS people (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    wiki_url TEXT,
    bio_summary TEXT,
    type_id BIGINT REFERENCES person_types(id),
    nationality_id BIGINT REFERENCES nationalities(id),
    sex TEXT,
    birth_year INTEGER,
    death_year INTEGER,
    birth_year_era TEXT NOT NULL DEFAULT 'AD',
    death_year_era TEXT NOT NULL DEFAULT 'AD',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Citations table (person mentioned in a book, on a page)
CREATE TABLE IF NOT EXISTS citations (
    id BIGSERIAL PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES people(id),
    book_id BIGINT NOT NULL REFERENCES books(id),
    page_number TEXT,
    indirect_citation BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Epigraphs table
CREATE TABLE IF NOT EXISTS epigraphs (
    id BIGSERIAL PRIMARY KEY,
    book_id BIGINT NOT NULL REFERENCES books(id),
    author_id BIGINT NOT NULL REFERENCES people(id),
    quote TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Book contributors (authors, translators, etc.)
CREATE TABLE IF NOT EXISTS book_contributors (
    book_id BIGINT NOT NULL REFERENCES books(id),
    person_id BIGINT NOT NULL REFERENCES people(id),
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (book_id, person_id, role)
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_people_name ON people (name);
CREATE INDEX IF NOT EXISTS idx_people_type_id ON people (type_id);
CREATE INDEX IF NOT EXISTS idx_people_nationality_id ON people (nationality_id);

CREATE INDEX IF NOT EXISTS idx_books_is_complete ON books (is_complete);
CREATE INDEX IF NOT EXISTS idx_books_title ON books (title);

CREATE INDEX IF NOT EXISTS idx_citations_person_id ON citations (person_id);
CREATE INDEX IF NOT EXISTS idx_citations_book_id ON citations (book_id);

CREATE INDEX IF NOT EXISTS idx_epigraphs_author_id ON epigraphs (author_id);
CREATE INDEX IF NOT EXISTS idx_epigraphs_book_id ON epigraphs (book_id);

CREATE INDEX IF NOT EXISTS idx_book_contributors_person_id ON book_contributors (person_id);

COMMIT;
