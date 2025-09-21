import sqlite3
from collections import defaultdict
from urllib.parse import urlparse, unquote

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort, flash
from . import db
from .wikipedia_utils import get_wikipedia_info 
from .open_library_utils import get_book_data_from_isbn, search_books_by_title_and_author

bp = Blueprint("main", __name__)


def _parse_names_field(raw_value):
    if not raw_value:
        return []

    values = raw_value if isinstance(raw_value, list) else [raw_value]
    names = []
    seen = set()

    for value in values:
        if not value:
            continue
        for part in value.split(","):
            name = part.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(name)

    return names


def _extract_wikipedia_title(value):
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if "wikipedia.org" not in (parsed.netloc or ""):
            return None
        path = parsed.path or ""
        if path.startswith("/wiki/"):
            title = path[len("/wiki/"):]
            if title:
                return unquote(title).replace("_", " ")
        return None

    return value


def _normalize_era(value):
    value = (value or "AD").upper()
    return "BC" if value == "BC" else "AD"


def _to_common_era_year(year, era):
    if year is None:
        return None
    try:
        year_int = int(year)
    except (TypeError, ValueError):
        return None
    era = _normalize_era(era)
    if era == "BC":
        return -(year_int - 1)
    return year_int


def _update_contributors(book_id, names, role, default_type):
    desired_ids = set()
    for name in names:
        person_id = db.get_or_create_person(name, default_type=default_type)
        if not person_id:
            continue
        desired_ids.add(person_id)
        db.add_book_contributor(book_id, person_id, role)

    existing = db.get_book_contributors(book_id, role=role)
    for _, person_id, _ in existing:
        if person_id not in desired_ids:
            db.remove_book_contributor(book_id, person_id, role)


@bp.route("/")
def index():
    return render_template("index.html")


# -------- BOOKS --------
@bp.route("/books")
def books():
    all_books = db.get_books()
    return render_template("books.html", books=all_books)


@bp.route("/books/add", methods=["GET", "POST"])
def add_book():
    if request.method == "POST":
        title = request.form["title"].strip()
        year = (request.form.get("publication_year") or "").strip() or None
        isbn = (request.form.get("isbn") or "").strip() or None
        authors_raw = request.form.get("authors")
        translators_raw = request.form.get("translators")

        book_id = db.add_book(title, year, isbn)

        author_names = _parse_names_field(authors_raw)
        translator_names = _parse_names_field(translators_raw)

        _update_contributors(book_id, author_names, "author", "Author")
        _update_contributors(book_id, translator_names, "translator", "Translator")

        return redirect(url_for("main.books"))

    return render_template("add_book.html")


@bp.route("/books/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    book_row = db.get_book_by_id(book_id)
    if not book_row:
        abort(404)

    book = {
        "id": book_row[0],
        "title": book_row[1],
        "publication_year": book_row[2] or "",
        "isbn": book_row[3] or "",
        "authors": book_row[4] or "",
        "translators": book_row[5] or "",
        "is_complete": bool(book_row[6]),
    }

    if request.method == "POST":
        title = request.form["title"].strip()
        year = (request.form.get("publication_year") or "").strip() or None
        isbn = (request.form.get("isbn") or "").strip() or None
        authors_raw = request.form.get("authors")
        translators_raw = request.form.get("translators")
        is_complete = request.form.get("is_complete") == "on"

        db.update_book(book_id, title, year, isbn, is_complete)

        author_names = _parse_names_field(authors_raw)
        translator_names = _parse_names_field(translators_raw)

        _update_contributors(book_id, author_names, "author", "Author")
        _update_contributors(book_id, translator_names, "translator", "Translator")

        return redirect(url_for("main.view_book", book_id=book_id))

    return render_template("edit_book.html", book=book)

@bp.route("/books/lookup", methods=["GET", "POST"])
def book_lookup():
    results = []

    if request.method == "POST":
        title = request.form.get("title", "")
        author = request.form.get("author", "")
        isbn = request.form.get("isbn", "").replace("-", "").strip()

        if isbn:
            book = get_book_data_from_isbn(isbn)
            if book:
                results = [book]
        elif title and author:
            results = search_books_by_title_and_author(title, author)

    return render_template("book_lookup.html", results=results)

@bp.route("/books/<int:book_id>")
def view_book(book_id):
    book = db.get_book_by_id(book_id)
    citations = db.get_citations_by_book(book_id)
    epigraphs = db.get_epigraphs_by_book(book_id)
    contributor_rows = db.get_book_contributors(book_id)
    contributors = defaultdict(list)
    for role, person_id, name in contributor_rows:
        contributors[role].append((person_id, name))

    return render_template(
        "view_book.html",
        book=book,
        citations=citations,
        epigraphs=epigraphs,
        contributors=contributors
    )

# -------- PEOPLE --------
@bp.route("/people")
def people():
    raw_query = request.args.get("q", "")
    search_term = raw_query.strip()
    all_people = db.get_people(search_term or None)
    return render_template("people.html", people=all_people, search_query=raw_query)


@bp.route("/people/add", methods=["GET", "POST"])
def add_person():
    person_types = db.get_person_types()
    nationalities = db.get_nationalities()

    if request.method == "POST":
        name = request.form["name"]
        type_id = request.form.get("type_id")
        type_id = int(type_id) if type_id else None
        nationality_id = request.form.get("nationality_id")
        new_nationality = (request.form.get("new_nationality") or "").strip()
        birth_year = request.form.get("birth_year") or None
        death_year = request.form.get("death_year") or None
        notes = (request.form.get("notes") or "").strip() or None
        birth_year_era = _normalize_era(request.form.get("birth_year_era"))
        death_year_era = _normalize_era(request.form.get("death_year_era"))

        if nationality_id == "_new" and new_nationality:
            nationality_id = db.add_nationality(new_nationality)
        elif nationality_id:
            nationality_id = int(nationality_id)
        else:
            nationality_id = None

        # convert to int if present
        birth_year = int(birth_year) if birth_year else None
        death_year = int(death_year) if death_year else None
        
        redirect_to = request.form.get("redirect_to")
        if not redirect_to or redirect_to.lower() == "none":
            redirect_to = url_for("main.people")

        wiki_url, bio, wiki_birth, wiki_death = get_wikipedia_info(name)
        birth_year = birth_year if birth_year is not None else wiki_birth
        death_year = death_year if death_year is not None else wiki_death
        person_id = db.add_person(
            name,
            wiki_url,
            bio,
            type_id,
            nationality_id,
            birth_year,
            death_year,
            notes,
            birth_year_era=birth_year_era,
            death_year_era=death_year_era,
        )

        if "add_citation" in redirect_to:
            return redirect(f"{redirect_to}?person_id={person_id}")

        return redirect(redirect_to)

    redirect_to = request.args.get("redirect_to")
    name_prefill = request.args.get("name", "")
    return render_template(
        "add_person.html",
        person_types=person_types,
        nationalities=nationalities,
        redirect_to=redirect_to,
        name=name_prefill
    )

@bp.route("/people/inline-add", methods=["POST"])
def inline_add_person():
    data = request.json
    name = data.get("name")
    type_id = data.get("type_id")
    new_type_name = data.get("new_type_name")
    birth_year = data.get("birth_year")
    death_year = data.get("death_year")
    notes = (data.get("notes") or "").strip() or None
    nationality_id = data.get("nationality_id")
    new_nationality_name = (data.get("new_nationality_name") or "").strip()
    birth_year_era = _normalize_era(data.get("birth_year_era"))
    death_year_era = _normalize_era(data.get("death_year_era"))

    birth_year = int(birth_year) if birth_year else None
    death_year = int(death_year) if death_year else None

    # Prevent duplicate entries
    if db.person_exists(name):
        return jsonify({
            "error": "That person already exists. Please choose them from the list or edit their details."
        }), 400

    if type_id:
        try:
            type_id = int(type_id)
        except (TypeError, ValueError):
            type_id = None

    if not type_id and new_type_name:
        type_id = db.add_person_type(new_type_name)

    if nationality_id == "_new":
        nationality_id = None
    elif nationality_id:
        try:
            nationality_id = int(nationality_id)
        except (TypeError, ValueError):
            nationality_id = None

    if not nationality_id and new_nationality_name:
        nationality_id = db.add_nationality(new_nationality_name)

    wiki_url, bio, wiki_birth, wiki_death = get_wikipedia_info(name)
    birth_year = birth_year if birth_year is not None else wiki_birth
    death_year = death_year if death_year is not None else wiki_death
    person_id = db.add_person(
        name,
        wiki_url,
        bio,
        type_id,
        nationality_id,
        birth_year,
        death_year,
        notes,
        birth_year_era=birth_year_era,
        death_year_era=death_year_era,
    )

    return {"id": person_id, "name": name}

@bp.route("/people/search")
def search_people():
    query = request.args.get("q", "").lower()
    matches = []
    for p in db.get_people():
        if query in p[1].lower():
            matches.append({"id": p[0], "text": p[1]})
    return jsonify(matches)


@bp.route("/people/<int:person_id>")
def view_person(person_id):
    person = db.get_person_by_id(person_id)
    if not person:
        abort(404)

    citations = db.get_citations_by_person(person_id)
    epigraphs = db.get_epigraphs_by_person(person_id)
    contribution_rows = db.get_book_contributions_by_person(person_id)
    contributions = defaultdict(list)
    for role, book_id, title in contribution_rows:
        contributions[role].append((book_id, title))

    birth_year = person[5]
    death_year = person[6]
    birth_year_era = person[11]
    death_year_era = person[12]
    age = None
    age_label = None
    current_year = datetime.now().year
    if isinstance(death_year, str) and death_year and death_year.lower() == "present":
        death_year = None
    birth_value = _to_common_era_year(birth_year, birth_year_era)
    death_value = _to_common_era_year(death_year, death_year_era) if death_year is not None else None

    if birth_value is not None:
        if death_value is not None:
            if death_value >= birth_value:
                age = death_value - birth_value
                age_label = f"Age at death: {age}"
        else:
            age = current_year - birth_value
            age_label = f"Age: {age}"

    return render_template(
        "view_person.html",
        person=person,
        citations=citations,
        epigraphs=epigraphs,
        contributions=contributions,
        age=age,
        age_label=age_label,
        birth_year_era=birth_year_era,
        death_year_era=death_year_era
    )

# -------- EDIT PERSON --------
@bp.route("/people/edit/<int:person_id>", methods=["GET", "POST"])
def edit_person(person_id):
    person_types = db.get_person_types()
    nationalities = db.get_nationalities()
    person = db.get_person_by_id(person_id)
    if not person:
        abort(404)

    if request.method == "POST":
        name = request.form["name"]
        type_id = request.form.get("type_id")
        type_id = int(type_id) if type_id else None
        nationality_id = request.form.get("nationality_id")
        nationality_id = int(nationality_id) if nationality_id else None
        birth_year = request.form.get("birth_year") or None
        death_year = request.form.get("death_year") or None
        notes = (request.form.get("notes") or "").strip() or None
        wiki_url_input = (request.form.get("wiki_url") or "").strip() or None
        birth_year_era = _normalize_era(request.form.get("birth_year_era"))
        death_year_era = _normalize_era(request.form.get("death_year_era"))

        existing_url = person[3] or None
        wiki_url = wiki_url_input
        bio_summary = person[4]

        if wiki_url != existing_url:
            search_term = _extract_wikipedia_title(wiki_url)
            if search_term:
                fetched_url, fetched_summary, _, _ = get_wikipedia_info(search_term)
                wiki_url = fetched_url or wiki_url
                bio_summary = fetched_summary
            else:
                bio_summary = None
        elif wiki_url is None:
            bio_summary = None

        birth_year = int(birth_year) if birth_year else None
        death_year = int(death_year) if death_year else None

        db.update_person(
            person_id,
            name,
            type_id,
            nationality_id,
            birth_year,
            death_year,
            notes,
            wiki_url=wiki_url,
            bio_summary=bio_summary,
            birth_year_era=birth_year_era,
            death_year_era=death_year_era
        )
        return redirect(url_for("main.people"))

    return render_template("edit_person.html", person=person, person_types=person_types, nationalities=nationalities)


# -------- DELETE PERSON --------
@bp.route("/people/delete/<int:person_id>", methods=["POST"])
def delete_person(person_id):
    db.delete_person(person_id)
    return redirect(url_for("main.people"))


# -------- CITATIONS --------
@bp.route("/citations")
def citations():
    all_citations = db.get_citations()
    return render_template("citations.html", citations=all_citations)


@bp.route("/citations/add", methods=["GET", "POST"])
def add_citation():
    books = db.get_books(include_completed=False)
    people = db.get_people()
    person_types = db.get_person_types()
    nationalities = db.get_nationalities()
    preselected_book_id = request.args.get("book_id", type=int)
    preselected_person_id = request.args.get("person_id", type=int)

    if request.method == "POST":
        person_id = request.form["person_id"]
        book_id = request.form["book_id"]
        page_number = request.form["page_number"]
        notes = request.form.get("notes")
        indirect_citation = request.form.get("indirect_citation") == "on"
        db.add_citation(person_id, book_id, page_number, indirect_citation, notes)
        if request.form.get("save_and_add") == "another":
            flash("Citation saved. Add another.", "success")
            return redirect(url_for("main.add_citation", book_id=book_id))
        return redirect(url_for("main.citations"))

    if preselected_book_id and preselected_book_id not in {book[0] for book in books}:
        preselected_book_id = None

    return render_template(
        "add_citation.html",
        books=books,
        people=people,
        person_types=person_types,
        nationalities=nationalities,
        preselected_book_id=preselected_book_id,
        preselected_person_id=preselected_person_id
    )

@bp.route("/citations/person/<int:person_id>")
def citations_for_person(person_id):
    person = db.get_person_by_id(person_id)
    citations = db.get_citations_by_person(person_id)
    return render_template("citations.html", citations=citations, person=person)

# -------- EDIT CITATION --------
@bp.route("/citations/edit/<int:citation_id>", methods=["GET", "POST"])
def edit_citation(citation_id):
    citation = db.get_citation_by_id(citation_id)
    books = db.get_books(include_completed=False, ensure_ids=[citation[2]])
    people = db.get_people()

    if request.method == "POST":
        person_id = request.form["person_id"]
        book_id = request.form["book_id"]
        page_number = request.form["page_number"]
        notes = request.form["notes"]
        indirect =request.form.get("indirect_citation") == "on"

        db.update_citation(citation_id, person_id, book_id, page_number, indirect, notes)
        return redirect(url_for("main.citations"))

    return render_template("edit_citation.html", citation=citation, books=books, people=people)


# -------- EPIGRAPHS --------
@bp.route("/epigraphs")
def epigraphs():
    all_epigraphs = db.get_epigraphs()
    return render_template("epigraphs.html", epigraphs=all_epigraphs)


@bp.route("/epigraphs/add", methods=["GET", "POST"])
def add_epigraph():
    books = db.get_books(include_completed=False)
    person_types = db.get_person_types()
    nationalities = db.get_nationalities()
    preselected_book_id = request.args.get("book_id", type=int)

    if request.method == "POST":
        book_id = request.form.get("book_id")
        author_id = request.form.get("person_id")
        quote = (request.form.get("quote") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if not author_id:
            flash("Please select an author from the list or add a new person.", "danger")
        elif not quote:
            flash("Please provide the epigraph text.", "danger")
        else:
            db.add_epigraph(book_id, author_id, quote, notes)
            flash("Epigraph added.", "success")
            return redirect(url_for("main.epigraphs"))

    selected_book_id = request.form.get("book_id", type=int)
    if selected_book_id is None:
        selected_book_id = preselected_book_id

    if selected_book_id and selected_book_id not in {book[0] for book in books}:
        selected_book_id = None

    quote_value = request.form.get("quote") if request.method == "POST" else ""
    notes_value = request.form.get("notes") if request.method == "POST" else ""

    return render_template(
        "add_epigraph.html",
        books=books,
        person_types=person_types,
        nationalities=nationalities,
        selected_book_id=selected_book_id,
        quote_value=quote_value,
        notes_value=notes_value
    )


@bp.route("/epigraphs/edit/<int:epigraph_id>", methods=["GET", "POST"])
def edit_epigraph(epigraph_id):
    epigraph = db.get_epigraph_by_id(epigraph_id)
    if not epigraph:
        abort(404)

    books = db.get_books(include_completed=False, ensure_ids=[epigraph[1]])
    person_types = db.get_person_types()
    nationalities = db.get_nationalities()
    author = db.get_person_by_id(epigraph[2])
    author_name = author[1] if author else ""

    if request.method == "POST":
        book_id = request.form.get("book_id")
        author_id = request.form.get("person_id")
        quote = (request.form.get("quote") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if not author_id:
            flash("Please select an author from the list or add a new person.", "danger")
        elif not quote:
            flash("Please provide the epigraph text.", "danger")
        else:
            db.update_epigraph(epigraph_id, book_id, author_id, quote, notes)
            flash("Epigraph updated.", "success")
            return redirect(url_for("main.epigraphs"))

    selected_book_id = request.form.get("book_id", type=int)
    if selected_book_id is None:
        selected_book_id = epigraph[1]

    quote_value = request.form.get("quote") if request.method == "POST" else epigraph[3]
    notes_value = request.form.get("notes") if request.method == "POST" else (epigraph[4] or "")

    return render_template(
        "edit_epigraph.html",
        epigraph=epigraph,
        books=books,
        person_types=person_types,
        nationalities=nationalities,
        author_name=author_name,
        selected_book_id=selected_book_id,
        quote_value=quote_value,
        notes_value=notes_value
    )


@bp.route("/epigraphs/delete/<int:epigraph_id>", methods=["POST"])
def delete_epigraph(epigraph_id):
    db.delete_epigraph(epigraph_id)
    flash("Epigraph removed.", "info")
    return redirect(url_for("main.epigraphs"))


@bp.route("/person-types", methods=["GET", "POST"])
def manage_person_types():
    if request.method == "POST":
        name = request.form["name"]
        db.add_person_type(name)
        return redirect(url_for("main.manage_person_types"))

    types = db.get_person_types()
    return render_template("person_types.html", types=types)


@bp.route("/nationalities", methods=["GET", "POST"])
def manage_nationalities():
    if request.method == "POST":
        action = request.form.get("action") or ""
        name = (request.form.get("name") or "").strip()
        nationality_id = request.form.get("nationality_id")
        try:
            nationality_id = int(nationality_id) if nationality_id else None
        except (TypeError, ValueError):
            nationality_id = None

        try:
            if action == "add":
                if not name:
                    flash("Please provide a nationality name.", "warning")
                else:
                    db.add_nationality(name)
                    flash("Nationality added.", "success")
            elif action == "update" and nationality_id:
                if not name:
                    flash("Please provide a nationality name.", "warning")
                else:
                    db.update_nationality(nationality_id, name)
                    flash("Nationality updated.", "success")
            elif action == "delete" and nationality_id:
                db.delete_nationality(nationality_id)
                flash("Nationality removed.", "info")
            else:
                flash("Unable to process the request.", "danger")
        except sqlite3.IntegrityError:
            flash("That nationality is in use and cannot be removed or renamed to an existing entry.", "danger")

        return redirect(url_for("main.manage_nationalities"))

    nationalities = db.get_nationalities()
    return render_template("nationalities.html", nationalities=nationalities)

@bp.route("/wikipedia/preview")
def wikipedia_preview():
    name = request.args.get("name")
    if not name:
        return {"summary": None, "url": None, "birth_year": None, "death_year": None}

    url, summary, birth_year, death_year = get_wikipedia_info(name)
    return {
        "summary": summary,
        "url": url,
        "birth_year": birth_year,
        "death_year": death_year
    }

@bp.route('/api/people-list')
def people_list():
    results = db.get_people()
    return jsonify([{"id": p[0], "name": p[1]} for p in results])
