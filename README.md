# Referent

Referent is a small Flask application for tracking notable people referenced in books. It lets you catalogue books, manage information about the people cited within them, and record the specific pages where each person is mentioned. The app also offers helpers for looking up book metadata from Open Library and pulling short bios from Wikipedia so that you can build a reference database quickly. Recent updates add book-completion tracking, better person-era handling (AD/BC), and workflow shortcuts for adding multiple citations in a row.

## Features

- 📚 **Book management** – add books with publication details and completion status, and automatically link them to multiple authors and translators.
- 🧑‍🤝‍🧑 **People directory** – maintain a list of referenced people, organized by type (e.g., philosopher, historian). Wikipedia summaries are fetched automatically when available, and birth/death eras (AD/BC) are supported for accurate timelines.
- 🔖 **Citation tracking** – record the page number and notes for each time a person is cited in a book, mark indirect citations, and quickly add another citation for the same book without leaving the form.
- 📝 **Epigraph management** – capture epigraph quotes tied to the book and author, retain optional notes, and keep them separate from inline citations.
- 🔍 **Metadata lookup** – search Open Library by ISBN, title, or author to prefill book details, and preview Wikipedia data before adding a person.

## Prerequisites

- Python 3.10+
- SQLite
- Flask

## Usage overview

- **Books** – use the *Books* tab to see all stored books, add new entries, and view existing ones along with their citations. The *Lookup* action lets you pull metadata from Open Library by ISBN, title, or author.
- **People** – manage referenced people and their types. When adding a person, the app calls Wikipedia to populate the bio, birth year, and death year (including era designations) when available.
- **Citations** – log where a person is cited within a book, add optional notes, and flag indirect citations. Inline dialogs allow you to add missing people or person types on the fly.
- **Epigraphs** – record epigraph passages, associate them with both the book and the quoted author, and manage explanatory notes alongside the quote text.

## External services

- [Open Library](https://openlibrary.org/developers/api) for book metadata and cover images.
- [Wikipedia](https://pypi.org/project/Wikipedia-API/) via the `wikipedia-api` package for person summaries and life dates.

Both services are accessed anonymously; no API keys are required.

## License

This project is provided as-is for instructional purposes. 
