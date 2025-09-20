# Referent

Referent is a small Flask application for tracking notable people referenced in books. It lets you catalogue books, manage information about the people cited within them, and record the specific pages where each person is mentioned. The app also offers helpers for looking up book metadata from Open Library and pulling short bios from Wikipedia so that you can build a reference database quickly.

## Features

- 📚 **Book management** – add books with publication details, ISBNs, and automatically link them to multiple authors and translators.
- 🧑‍🤝‍🧑 **People directory** – maintain a list of referenced people, organized by type (e.g., philosopher, historian). Wikipedia summaries are fetched automatically when available.
- 🔖 **Citation tracking** – record the page number and notes for each time a person is cited in a book and mark indirect citations.
- 🔍 **Metadata lookup** – search Open Library by ISBN, title, or author to prefill book details, and preview Wikipedia data before adding a person.
- ⚙️ **Inline helpers** – create new person entries or person types directly from citation forms without leaving the page.

## Project structure

```
referent/
├── app/
│   ├── __init__.py          # Flask application factory
│   ├── routes.py            # Web routes and view logic
│   ├── db.py                # SQLite helper functions
│   ├── open_library_utils.py
│   ├── wikipedia_utils.py
│   ├── templates/           # Jinja2 templates for the UI
│   └── static/              # CSS and image assets
├── run.py                   # Entry point used for local development
├── schema.sql               # Database schema (loaded on startup)
├── requirements.txt         # Python dependencies
└── README.md
```

An `instance/` directory will be created automatically at runtime to store the SQLite database (`referent.sqlite3`). The file is intentionally excluded from version control.

## Prerequisites

- Python 3.10+
- (Optional) `virtualenv` or another environment manager

## Local setup

1. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the development server**
   ```bash
   flask --app run --debug run
   ```

   Alternatively, run `python run.py` to start the server with Flask's built-in debugger enabled.

4. **Open the app**

   Visit [http://localhost:5000](http://localhost:5000) in your browser.

The first time the application starts it will create `instance/referent.sqlite3` by executing the statements in `schema.sql`.

## Usage overview

- **Books** – use the *Books* tab to see all stored books, add new entries, and view existing ones along with their citations. The *Lookup* action lets you pull metadata from Open Library by ISBN, title, or author.
- **People** – manage referenced people and their types. When adding a person, the app calls Wikipedia to populate the bio, birth year, and death year when available.
- **Citations** – log where a person is cited within a book, add optional notes, and flag indirect citations. Inline dialogs allow you to add missing people or person types on the fly.

## Database schema

The application uses SQLite. Tables are created from `schema.sql` and cover books, authors, translators, people, person types, and citations. Application-level helper functions (see `app/db.py`) handle all CRUD operations and ensure many-to-many relationships between books/authors and books/translators.

## External services

- [Open Library](https://openlibrary.org/developers/api) for book metadata and cover images.
- [Wikipedia](https://pypi.org/project/Wikipedia-API/) via the `wikipedia-api` package for person summaries and life dates.

Both services are accessed anonymously; no API keys are required.

## Development tips

- The Flask application factory lives in `app/__init__.py`. If you add new blueprints or configuration, register them there.
- Jinja2 templates are organized under `app/templates/`. Extend `base.html` for new pages to keep styling consistent.
- Static assets (CSS, images) belong in `app/static/`.
- If you need to reset the database, delete `instance/referent.sqlite3` and restart the server to rebuild it from `schema.sql`.

## License

This project is provided as-is for instructional purposes. Update this section with your preferred licensing information if you plan to distribute the application.
