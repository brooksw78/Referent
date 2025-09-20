from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from . import db
from .wikipedia_utils import get_wikipedia_info 
from .open_library_utils import get_book_data_from_isbn, search_books_by_title_and_author

bp = Blueprint("main", __name__)


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
        title = request.form["title"]
        year = request.form.get("publication_year")
        isbn = request.form.get("isbn")
        authors = request.form.getlist("authors")  # comma-separated string
        translators = request.form.getlist("translators")

        book_id = db.add_book(title, year, isbn)

        for author_name in [a.strip() for a in ",".join(authors).split(",") if a.strip()]:
            author_id = db.add_author(author_name)
            db.link_author_to_book(book_id, author_id)

        for translator_name in [t.strip() for t in ",".join(translators).split(",") if t.strip()]:
            translator_id = db.add_translator(translator_name)
            db.link_translator_to_book(book_id, translator_id)

        return redirect(url_for("main.books"))

    return render_template("add_book.html")

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
    return render_template("view_book.html", book=book, citations=citations)

# -------- PEOPLE --------
@bp.route("/people")
def people():
    all_people = db.get_people()
    return render_template("people.html", people=all_people)


@bp.route("/people/add", methods=["GET", "POST"])
def add_person():
    person_types = db.get_person_types()

    if request.method == "POST":
        name = request.form["name"]
        type_id = request.form.get("type_id")
        birth_year = request.form.get("birth_year") or None
        death_year = request.form.get("death_year") or None

        # convert to int if present
        birth_year = int(birth_year) if birth_year else None
        death_year = int(death_year) if death_year else None
        
        redirect_to = request.form.get("redirect_to") or url_for("main.people")

        wiki_url, bio, birth_year, death_year = get_wikipedia_info(name)
        person_id = db.add_person(name, wiki_url, bio, type_id, birth_year, death_year)

        if "add_citation" in redirect_to:
            return redirect(f"{redirect_to}?person_id={person_id}")

        return redirect(redirect_to)

    redirect_to = request.args.get("redirect_to")
    name_prefill = request.args.get("name", "")
    return render_template("add_person.html", person_types=person_types, redirect_to=redirect_to, name=name_prefill)

@bp.route("/people/inline-add", methods=["POST"])
def inline_add_person():
    data = request.json
    name = data.get("name")
    type_id = data.get("type_id")
    new_type_name = data.get("new_type_name")
    birth_year = data.get("birth_year")
    death_year = data.get("death_year")

    # Prevent duplicate entries
    if db.person_exists(name):
        return jsonify({
            "error": "That person already exists. Please choose them from the list or edit their details."
        }), 400

    if not type_id and new_type_name:
        type_id = db.add_person_type(new_type_name)

    wiki_url, bio, _, _ = get_wikipedia_info(name)
    person_id = db.add_person(name, wiki_url, bio, type_id, birth_year, death_year)

    return {"id": person_id, "name": name}

@bp.route("/people/search")
def search_people():
    query = request.args.get("q", "").lower()
    matches = []
    for p in db.get_people():
        if query in p[1].lower():
            matches.append({"id": p[0], "text": p[1]})
    return jsonify(matches)

# -------- EDIT PERSON --------
@bp.route("/people/edit/<int:person_id>", methods=["GET", "POST"])
def edit_person(person_id):
    person_types = db.get_person_types()
    person = db.get_person_by_id(person_id)

    if request.method == "POST":
        name = request.form["name"]
        type_id = request.form.get("type_id")
        db.update_person(person_id, name, type_id)
        return redirect(url_for("main.people"))

    return render_template("edit_person.html", person=person, person_types=person_types)


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
    books = db.get_books()
    people = db.get_people()
    person_types = db.get_person_types()
    preselected_book_id = request.args.get("book_id", type=int)
    preselected_person_id = request.args.get("person_id", type=int)

    if request.method == "POST":
        person_id = request.form["person_id"]
        book_id = request.form["book_id"]
        page_number = request.form["page_number"]
        notes = request.form.get("notes")
        indirect_citation = request.form.get("indirect_citation") == "on"
        db.add_citation(person_id, book_id, page_number, indirect_citation, notes)
        return redirect(url_for("main.citations"))

    return render_template(
        "add_citation.html",
        books=books,
        people=people,
        person_types=person_types,
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
    books = db.get_books()
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

@bp.route("/person-types", methods=["GET", "POST"])
def manage_person_types():
    if request.method == "POST":
        name = request.form["name"]
        db.add_person_type(name)
        return redirect(url_for("main.manage_person_types"))

    types = db.get_person_types()
    return render_template("person_types.html", types=types)

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