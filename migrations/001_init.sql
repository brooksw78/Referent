BEGIN;

SET ROLE referent_user;

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

CREATE TABLE IF NOT EXISTS person_types (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS nationalities (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

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

CREATE TABLE IF NOT EXISTS epigraphs (
    id BIGSERIAL PRIMARY KEY,
    book_id BIGINT NOT NULL REFERENCES books(id),
    author_id BIGINT NOT NULL REFERENCES people(id),
    quote TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS book_contributors (
    book_id BIGINT NOT NULL REFERENCES books(id),
    person_id BIGINT NOT NULL REFERENCES people(id),
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (book_id, person_id, role)
);

COMMIT;
