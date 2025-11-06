BEGIN;

SET ROLE referent_user;

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
