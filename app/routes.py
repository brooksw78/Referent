import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, unquote
from uuid import uuid4

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort, flash, current_app
from werkzeug.utils import secure_filename
from . import db
from .wikipedia_utils import get_wikipedia_info 
from .open_library_utils import fetch_cover_url, get_book_data_from_isbn, search_books_by_title_and_author

bp = Blueprint("main", __name__)


def _get_allowed_cover_extensions():
    allowed = current_app.config.get("ALLOWED_COVER_EXTENSIONS", {"png", "jpg", "jpeg", "gif", "webp"})
    return {str(ext).lower() for ext in allowed}


def _allowed_cover_extension(filename):
    extension = Path(filename or "").suffix.lower().lstrip(".")
    if not extension:
        return False
    return extension in _get_allowed_cover_extensions()


def _cover_upload_directory():
    subdir = current_app.config.get("COVER_UPLOAD_SUBDIR", "uploads/covers")
    return Path(current_app.static_folder) / subdir


def _delete_cover_file(relative_path):
    if not relative_path:
        return
    base = Path(current_app.static_folder).resolve()
    target = (base / relative_path).resolve()
    if base == target or base not in target.parents:
        return
    if target.exists() and target.is_file():
        target.unlink()


def _save_uploaded_cover(file_storage, existing_path=None):
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        return existing_path
    if not _allowed_cover_extension(filename):
        raise ValueError("unsupported file type")

    upload_dir = _cover_upload_directory()
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower()
    unique_name = f"{uuid4().hex}{ext}"
    destination = upload_dir / unique_name
    file_storage.save(destination)

    if existing_path:
        _delete_cover_file(existing_path)

    relative_path = destination.relative_to(Path(current_app.static_folder))
    return str(relative_path).replace("\\", "/")


def _build_cover_image_url(cover_url, cover_image_path):
    if cover_image_path:
        return url_for("static", filename=cover_image_path)
    if cover_url:
        return cover_url
    return url_for("static", filename="images/cover_image_not_found.png")


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


SEX_CHOICES = [
    ("female", "Female"),
    ("male", "Male"),
    ("nonbinary", "Non-binary"),
    ("unknown", "Unknown / Not recorded"),
]
SEX_LABELS = {value: label for value, label in SEX_CHOICES}


def _normalize_sex(value):
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in SEX_LABELS else None


def _format_sex_label(value):
    if not value:
        return None
    return SEX_LABELS.get(value)


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


def _format_common_era_year(value):
    if value is None:
        return "?"
    if value <= 0:
        year = abs(value) + 1
        return f"{year} BC"
    return str(value)


def _format_bin_label(start, end):
    start_label = _format_common_era_year(start)
    end_label = _format_common_era_year(end)
    if start_label == end_label:
        return start_label
    return f"{start_label} – {end_label}"


def _build_temporal_heatmap(people_rows, bin_size=25):
    processed = []
    skipped = 0

    for person in people_rows or []:
        start = _to_common_era_year(person.get("birth_year"), person.get("birth_year_era"))
        end = _to_common_era_year(person.get("death_year"), person.get("death_year_era"))

        if start is None and end is None:
            skipped += 1
            continue

        if start is None:
            start = end
        if end is None:
            end = start
        if end < start:
            start, end = end, start

        processed.append(
            {
                "id": person["person_id"],
                "name": person["name"],
                "type": person.get("type_name"),
                "start": start,
                "end": end,
            }
        )

    if not processed:
        return {
            "bins": [],
            "max_count": 0,
            "bin_size": bin_size,
            "person_count": 0,
            "skipped_count": skipped,
            "earliest_year": None,
            "latest_year": None,
        }

    min_start = min(entry["start"] for entry in processed)
    max_end = max(entry["end"] for entry in processed)

    start_year = math.floor(min_start / bin_size) * bin_size
    end_year = math.floor(max_end / bin_size) * bin_size

    bins = []
    max_count = 0
    current = start_year

    while current <= end_year:
        current_end = current + bin_size - 1
        people_in_bin = [
            entry
            for entry in processed
            if entry["end"] >= current and entry["start"] <= current_end
        ]
        count = len(people_in_bin)
        max_count = max(max_count, count)

        bins.append(
            {
                "start": current,
                "end": current_end,
                "count": count,
                "label": _format_bin_label(current, current_end),
                "people": [
                    {
                        "id": entry["id"],
                        "name": entry["name"],
                        "type": entry["type"],
                    }
                    for entry in sorted(people_in_bin, key=lambda item: item["name"].lower())
                ],
            }
        )

        current += bin_size

    return {
        "bins": bins,
        "max_count": max_count,
        "bin_size": bin_size,
        "person_count": len(processed),
        "skipped_count": skipped,
        "earliest_year": start_year,
        "latest_year": end_year + bin_size - 1,
    }


def _update_contributors(book_id, names, role, default_type):
    desired_ids = set()
    for name in names:
        person_id = db.get_or_create_person(name, default_type=default_type)
        if not person_id:
            continue
        desired_ids.add(person_id)
        db.add_book_contributor(book_id, person_id, role)

    existing = db.get_book_contributors(book_id, role=role)
    for entry in existing:
        person_id = entry["person_id"]
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
        cover_url = (request.form.get("cover_url") or "").strip() or None
        cover_file = request.files.get("cover_file")
        cover_image_path = None
        authors_raw = request.form.get("authors")
        translators_raw = request.form.get("translators")

        if cover_file and cover_file.filename:
            try:
                cover_image_path = _save_uploaded_cover(cover_file)
            except ValueError:
                allowed = ", ".join(sorted(_get_allowed_cover_extensions()))
                flash(f"Unsupported file type. Allowed extensions: {allowed}.", "warning")
                current_app.logger.warning("Unsupported cover file type while creating book '%s'", title)
                cover_image_path = None
            except OSError as exc:
                current_app.logger.exception("Failed to save uploaded cover: %s", exc)
                flash("We couldn't save that cover image. Please try again.", "danger")
                cover_image_path = None

        if not cover_image_path and not cover_url and isbn:
            cover_url = fetch_cover_url(isbn)

        book_id = db.add_book(title, year, isbn, cover_url=cover_url, cover_image_path=cover_image_path)

        author_names = _parse_names_field(authors_raw)
        translator_names = _parse_names_field(translators_raw)

        _update_contributors(book_id, author_names, "author", "Author")
        _update_contributors(book_id, translator_names, "translator", "Translator")

        current_app.logger.info(
            "Book created id=%s title='%s' isbn=%s", book_id, title, isbn or "n/a"
        )

        return redirect(url_for("main.books"))

    return render_template("add_book.html")


@bp.route("/books/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    book_row = db.get_book_by_id(book_id)
    if not book_row:
        abort(404)

    book = {
        "id": book_row["id"],
        "title": book_row["title"],
        "publication_year": book_row.get("publication_year") or "",
        "isbn": book_row.get("isbn") or "",
        "authors": book_row.get("authors") or "",
        "translators": book_row.get("translators") or "",
        "is_complete": bool(book_row.get("is_complete")),
        "cover_url": book_row.get("cover_url") or "",
        "cover_image_path": book_row.get("cover_image_path") or "",
    }
    book["cover_preview"] = _build_cover_image_url(book["cover_url"], book["cover_image_path"])

    if not (book["cover_url"] or book["cover_image_path"]) and book["isbn"]:
        auto_cover = fetch_cover_url(book["isbn"])
        if auto_cover:
            book["cover_url"] = auto_cover
            book["cover_preview"] = auto_cover

    if request.method == "POST":
        title = request.form["title"].strip()
        year = (request.form.get("publication_year") or "").strip() or None
        isbn = (request.form.get("isbn") or "").strip() or None
        cover_url = (request.form.get("cover_url") or "").strip() or None
        authors_raw = request.form.get("authors")
        translators_raw = request.form.get("translators")
        is_complete = request.form.get("is_complete") == "on"
        action = request.form.get("_action", "save")
        cover_file = request.files.get("cover_file")
        remove_cover = request.form.get("remove_cover") == "on"
        cover_image_path = book["cover_image_path"] or None

        if not cover_image_path and not cover_url and isbn:
            cover_url = fetch_cover_url(isbn)

        if action == "fetch_cover":
            if remove_cover and cover_image_path:
                _delete_cover_file(cover_image_path)
                cover_image_path = None
            if not isbn:
                flash("Provide an ISBN before fetching a cover.", "warning")
                cover_url = None
                current_app.logger.warning("Fetch cover requested without ISBN for book id=%s", book_id)
            else:
                cover_url = fetch_cover_url(isbn)
                if cover_url:
                    flash("Cover fetched from Open Library.", "success")
                    if cover_image_path:
                        _delete_cover_file(cover_image_path)
                        cover_image_path = None
                    current_app.logger.info(
                        "Fetched cover from Open Library for book id=%s isbn=%s",
                        book_id,
                        isbn,
                    )
                else:
                    flash("Open Library does not have a cover for that ISBN.", "info")
                    current_app.logger.info(
                        "No Open Library cover available for book id=%s isbn=%s",
                        book_id,
                        isbn,
                    )

            db.update_book(
                book_id,
                title or book["title"],
                year,
                isbn,
                is_complete,
                cover_url,
                cover_image_path,
            )

            book.update(
                {
                    "title": title,
                    "publication_year": year or "",
                    "isbn": isbn or "",
                    "authors": request.form.get("authors", ""),
                    "translators": request.form.get("translators", ""),
                    "is_complete": is_complete,
                    "cover_url": cover_url,
                    "cover_image_path": cover_image_path or "",
                    "cover_preview": _build_cover_image_url(cover_url, cover_image_path),
                }
            )

            return render_template("edit_book.html", book=book)

        if cover_file and cover_file.filename:
            try:
                cover_image_path = _save_uploaded_cover(cover_file, existing_path=cover_image_path)
            except ValueError:
                allowed = ", ".join(sorted(_get_allowed_cover_extensions()))
                flash(f"Unsupported file type. Allowed extensions: {allowed}.", "warning")
                current_app.logger.warning(
                    "Unsupported cover file type during edit for book id=%s", book_id
                )
            except OSError as exc:
                current_app.logger.exception("Failed to save uploaded cover: %s", exc)
                flash("We couldn't save that cover image. Please try again.", "danger")
        else:
            if remove_cover and cover_image_path:
                _delete_cover_file(cover_image_path)
                cover_image_path = None
                current_app.logger.info("Removed uploaded cover for book id=%s", book_id)
            elif (
                cover_image_path
                and cover_url
                and cover_url != (book["cover_url"] or "")
            ):
                _delete_cover_file(cover_image_path)
                cover_image_path = None
                current_app.logger.info(
                    "Replaced uploaded cover with remote URL for book id=%s", book_id
                )

        db.update_book(book_id, title, year, isbn, is_complete, cover_url, cover_image_path)

        author_names = _parse_names_field(authors_raw)
        translator_names = _parse_names_field(translators_raw)

        _update_contributors(book_id, author_names, "author", "Author")
        _update_contributors(book_id, translator_names, "translator", "Translator")

        current_app.logger.info("Book updated id=%s title='%s'", book_id, title)

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
            book, error = get_book_data_from_isbn(isbn)
            if book:
                results = [book]
            else:
                flash(error or "No Open Library record found for that ISBN.", "warning")
        elif title or author:
            results, error = search_books_by_title_and_author(title, author)
            if not results:
                flash(error or "No Open Library results matched that search.", "info")
        else:
            flash("Enter an ISBN or provide a title and/or author to search.", "warning")

    return render_template("book_lookup.html", results=results)

@bp.route("/books/<int:book_id>")
def view_book(book_id):
    book = db.get_book_by_id(book_id)
    citations = db.get_citations_by_book(book_id)
    epigraphs = db.get_epigraphs_by_book(book_id)
    contributor_rows = db.get_book_contributors(book_id)
    contributors = defaultdict(list)
    for row in contributor_rows:
        contributors[row["role"]].append((row["person_id"], row["person_name"]))

    summary = db.get_book_summary(book_id)
    stats = db.get_book_reference_stats(book_id)
    lifetime_rows = db.get_book_people_lifetimes(book_id)
    heatmap = _build_temporal_heatmap(lifetime_rows)
    shared_books = db.get_books_with_shared_referents(book_id)
    for entry in shared_books:
        raw_names = entry.pop("shared_names", "") or ""
        shared_people = []
        for name in raw_names.split("||"):
            clean = (name or "").strip()
            if clean:
                shared_people.append(clean)
        entry["shared_people"] = shared_people

    return render_template(
        "view_book.html",
        book=book,
        citations=citations,
        epigraphs=epigraphs,
        contributors=contributors,
        summary_data=summary,
        reference_stats=stats,
        heatmap_data=heatmap,
        shared_books=shared_books,
    )


@bp.route("/graph")
def graph_view():
    return render_template("graph.html")


@bp.route("/graph/data")
def graph_data():
    elements = db.get_graph_elements()

    for node in elements["nodes"]:
        if node["type"] == "book":
            node["url"] = url_for("main.view_book", book_id=node["entity_id"])
        elif node["type"] == "person":
            node["url"] = url_for("main.view_person", person_id=node["entity_id"])
        node.pop("entity_id", None)

    return jsonify(elements)


@bp.route("/chords")
def chord_view():
    return render_template("chord.html")


@bp.route("/chords/data")
def chord_data():
    payload = db.get_chord_data()

    for entry in payload["connections"]:
        book_id = entry["book"]["id"]
        type_id = entry["person_type"]["id"]
        entry["book"]["url"] = url_for("main.view_book", book_id=book_id)
        entry["person_type"]["url"] = url_for("main.manage_person_types") + f"#type-{type_id}"

    return jsonify(payload)


@bp.route("/nationalities")
def nationality_map():
    return render_template("nationality_map.html")


@bp.route("/nationalities/data")
def nationality_data():
    payload = db.get_book_nationality_data()

    for entry in payload["connections"]:
        book_id = entry["book"]["id"]
        nationality_id = entry["nationality"]["id"]
        entry["book"]["url"] = url_for("main.view_book", book_id=book_id)
        entry["nationality"]["url"] = url_for("main.manage_nationalities") + f"#nationality-{nationality_id}"

    return jsonify(payload)


@bp.route("/visualizations/demographics")
def demographics():
    type_distribution = db.get_people_type_distribution()
    nationality_distribution = db.get_nationality_distribution()
    return render_template(
        "demographics.html",
        type_distribution=type_distribution,
        nationality_distribution=nationality_distribution,
    )


@bp.route("/stats")
def stats():
    counts = db.get_global_counts()
    return render_template("stats.html", counts=counts)


# -------- PEOPLE --------
@bp.route("/people")
def people():
    raw_query = request.args.get("q", "")
    search_term = raw_query.strip()
    type_arg = request.args.get("type_id")
    nationality_arg = request.args.get("nationality_id")

    def _parse_filter(value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    selected_type_id = _parse_filter(type_arg)
    selected_nationality_id = _parse_filter(nationality_arg)

    all_people = db.get_people(
        search_term or None,
        type_id=selected_type_id,
        nationality_id=selected_nationality_id,
    )
    for person in all_people:
        person["sex_label"] = _format_sex_label(person.get("sex"))
    person_types = db.get_person_types()
    nationalities = db.get_nationalities()
    filters_active = bool(
        (search_term or "").strip()
        or selected_type_id is not None
        or selected_nationality_id is not None
    )
    return render_template(
        "people.html",
        people=all_people,
        search_query=raw_query,
        person_types=person_types,
        nationalities=nationalities,
        selected_type_id=selected_type_id,
        selected_nationality_id=selected_nationality_id,
        filters_active=filters_active,
    )


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
        sex_value = _normalize_sex(request.form.get("sex"))
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
            sex_value,
            birth_year,
            death_year,
            notes,
            birth_year_era=birth_year_era,
            death_year_era=death_year_era,
        )

        current_app.logger.info(
            "Person created id=%s name='%s' type_id=%s nationality_id=%s sex=%s",
            person_id,
            name,
            type_id,
            nationality_id,
            sex_value or "n/a",
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
        sex_choices=SEX_CHOICES,
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
    sex_value = _normalize_sex(data.get("sex"))

    birth_year = int(birth_year) if birth_year else None
    death_year = int(death_year) if death_year else None

    # Prevent duplicate entries
    if db.person_exists(name):
        current_app.logger.warning("Inline person add rejected because '%s' already exists", name)
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
        sex_value,
        birth_year,
        death_year,
        notes,
        birth_year_era=birth_year_era,
        death_year_era=death_year_era,
    )

    current_app.logger.info(
        "Person created via inline add id=%s name='%s' type_id=%s nationality_id=%s sex=%s",
        person_id,
        name,
        type_id,
        nationality_id,
        sex_value or "n/a",
    )

    return {"id": person_id, "name": name}

@bp.route("/people/search")
def search_people():
    query = request.args.get("q", "").lower()
    matches = []
    for p in db.get_people():
        name = p["name"].lower()
        if query in name:
            matches.append({"id": p["id"], "text": p["name"]})
    return jsonify(matches)


@bp.route("/people/<int:person_id>")
def view_person(person_id):
    person = db.get_person_by_id(person_id)
    if not person:
        abort(404)
    sex_label = _format_sex_label(person.get("sex"))

    citations = db.get_citations_by_person(person_id)
    epigraphs = db.get_epigraphs_by_person(person_id)
    contribution_rows = db.get_book_contributions_by_person(person_id)
    contributions = defaultdict(list)
    for row in contribution_rows:
        role = row["role"]
        book_id = row["book_id"]
        title = row["book_title"]
        cover_url = _build_cover_image_url(row.get("cover_url"), row.get("cover_image_path"))
        contributions[role].append((book_id, title, cover_url))

    birth_year = person["birth_year"]
    death_year = person["death_year"]
    birth_year_era = person["birth_year_era"]
    death_year_era = person["death_year_era"]
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
        death_year_era=death_year_era,
        sex_label=sex_label,
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
        new_nationality = (request.form.get("new_nationality") or "").strip()
        if nationality_id == "_new":
            if new_nationality:
                nationality_id = db.add_nationality(new_nationality)
            else:
                nationality_id = None
        else:
            nationality_id = int(nationality_id) if nationality_id else None
        birth_year = request.form.get("birth_year") or None
        death_year = request.form.get("death_year") or None
        notes = (request.form.get("notes") or "").strip() or None
        wiki_url_input = (request.form.get("wiki_url") or "").strip() or None
        birth_year_era = _normalize_era(request.form.get("birth_year_era"))
        death_year_era = _normalize_era(request.form.get("death_year_era"))
        sex_value = _normalize_sex(request.form.get("sex"))

        existing_url = person["wiki_url"] or None
        wiki_url = wiki_url_input
        bio_summary = person["bio_summary"]

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
            sex_value,
            birth_year,
            death_year,
            notes,
            wiki_url=wiki_url,
            bio_summary=bio_summary,
            birth_year_era=birth_year_era,
            death_year_era=death_year_era
        )
        current_app.logger.info(
            "Person updated id=%s name='%s' type_id=%s nationality_id=%s sex=%s",
            person_id,
            name,
            type_id,
            nationality_id,
            sex_value or "n/a",
        )
        return redirect(url_for("main.people"))

    return render_template(
        "edit_person.html",
        person=person,
        person_types=person_types,
        nationalities=nationalities,
        sex_choices=SEX_CHOICES,
    )


# -------- DELETE PERSON --------
@bp.route("/people/delete/<int:person_id>", methods=["POST"])
def delete_person(person_id):
    db.delete_person(person_id)
    current_app.logger.info("Person deleted id=%s", person_id)
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
    book_ids = {book["id"] for book in books}
    people_by_id = {person["id"]: person for person in people}
    preselected_book_id = request.args.get("book_id", type=int)
    preselected_person_id = request.args.get("person_id", type=int)
    form_values = None
    error_message = None
    error_category = "danger"

    if request.method == "POST":
        person_id_raw = request.form.get("person_id")
        book_id_raw = request.form.get("book_id")
        page_number = (request.form.get("page_number") or "").strip()
        raw_notes = request.form.get("notes", "")
        indirect_citation = request.form.get("indirect_citation") == "on"

        try:
            person_id = int(person_id_raw)
        except (TypeError, ValueError):
            person_id = None

        try:
            book_id = int(book_id_raw)
        except (TypeError, ValueError):
            book_id = None

        person = db.get_person_by_id(person_id) if person_id else None

        form_values = {
            "person_id": person["id"] if person else None,
            "book_id": book_id if book_id in book_ids else None,
            "page_number": page_number,
            "notes": raw_notes,
            "indirect_citation": indirect_citation,
        }

        if not person:
            error_message = "Select an existing person or add them before saving a citation."
            error_category = "danger"
        elif book_id not in book_ids:
            error_message = "Choose a valid book for this citation."
            error_category = "warning"
        else:
            notes_value = raw_notes.strip() or None
            db.add_citation(person_id, book_id, page_number, indirect_citation, notes_value)
            current_app.logger.info(
                "Citation created person_id=%s book_id=%s page=%s indirect=%s",
                person_id,
                book_id,
                page_number,
                indirect_citation,
            )
            if request.form.get("save_and_add") == "another":
                flash("Citation saved. Add another.", "success")
                return redirect(url_for("main.add_citation", book_id=book_id))
            return redirect(url_for("main.citations"))

    if form_values:
        if form_values.get("book_id"):
            preselected_book_id = form_values["book_id"]
        if form_values.get("person_id"):
            preselected_person_id = form_values["person_id"]

    if preselected_book_id and preselected_book_id not in book_ids:
        preselected_book_id = None

    if preselected_person_id and preselected_person_id not in people_by_id:
        preselected_person_id = None

    selected_person = people_by_id.get(preselected_person_id) if preselected_person_id else None
    preselected_person_name = selected_person["name"] if selected_person else ""

    if error_message:
        flash(error_message, error_category)

    return render_template(
        "add_citation.html",
        books=books,
        people=people,
        person_types=person_types,
        nationalities=nationalities,
        sex_choices=SEX_CHOICES,
        preselected_book_id=preselected_book_id,
        preselected_person_id=preselected_person_id,
        preselected_person_name=preselected_person_name,
        form_values=form_values,
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
    books = db.get_books(include_completed=False, ensure_ids=[citation["book_id"]])
    people = db.get_people()
    book_ids = {book["id"] for book in books}
    people_by_id = {person["id"]: person for person in people}

    if request.method == "POST":
        page_number = (request.form.get("page_number") or "").strip()
        raw_notes = request.form.get("notes", "")
        indirect = request.form.get("indirect_citation") == "on"

        updated_citation = dict(citation)
        updated_citation.update(
            {
                "page_number": page_number,
                "notes": raw_notes,
                "indirect_citation": indirect,
            }
        )

        try:
            person_id = int(request.form.get("person_id"))
        except (TypeError, ValueError):
            person_id = None

        if person_id:
            updated_citation["person_id"] = person_id

        try:
            book_id = int(request.form.get("book_id"))
        except (TypeError, ValueError):
            book_id = None

        if book_id:
            updated_citation["book_id"] = book_id

        if not person_id or person_id not in people_by_id:
            flash("Select an existing person before saving this citation.", "danger")
            return render_template("edit_citation.html", citation=updated_citation, books=books, people=people)

        if book_id not in book_ids:
            flash("Choose a valid book for this citation.", "warning")
            return render_template("edit_citation.html", citation=updated_citation, books=books, people=people)

        notes_value = raw_notes.strip() or None
        db.update_citation(citation_id, person_id, book_id, page_number, indirect, notes_value)
        current_app.logger.info(
            "Citation updated id=%s person_id=%s book_id=%s",
            citation_id,
            person_id,
            book_id,
        )
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
            current_app.logger.warning("Epigraph creation blocked: missing author for book_id=%s", book_id)
        elif not quote:
            flash("Please provide the epigraph text.", "danger")
            current_app.logger.warning("Epigraph creation blocked: missing quote for book_id=%s author_id=%s", book_id, author_id)
        else:
            db.add_epigraph(book_id, author_id, quote, notes)
            flash("Epigraph added.", "success")
            current_app.logger.info(
                "Epigraph created book_id=%s author_id=%s", book_id, author_id
            )
            return redirect(url_for("main.epigraphs"))

    selected_book_id = request.form.get("book_id", type=int)
    if selected_book_id is None:
        selected_book_id = preselected_book_id

    if selected_book_id and selected_book_id not in {book["id"] for book in books}:
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

    books = db.get_books(include_completed=False, ensure_ids=[epigraph["book_id"]])
    person_types = db.get_person_types()
    nationalities = db.get_nationalities()
    author = db.get_person_by_id(epigraph["author_id"])
    author_name = author["name"] if author else ""

    if request.method == "POST":
        book_id = request.form.get("book_id")
        author_id = request.form.get("person_id")
        quote = (request.form.get("quote") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if not author_id:
            flash("Please select an author from the list or add a new person.", "danger")
            current_app.logger.warning(
                "Epigraph update blocked: missing author for epigraph_id=%s", epigraph_id
            )
        elif not quote:
            flash("Please provide the epigraph text.", "danger")
            current_app.logger.warning(
                "Epigraph update blocked: missing quote for epigraph_id=%s", epigraph_id
            )
        else:
            db.update_epigraph(epigraph_id, book_id, author_id, quote, notes)
            flash("Epigraph updated.", "success")
            current_app.logger.info(
                "Epigraph updated id=%s book_id=%s author_id=%s",
                epigraph_id,
                book_id,
                author_id,
            )
            return redirect(url_for("main.epigraphs"))

    selected_book_id = request.form.get("book_id", type=int)
    if selected_book_id is None:
        selected_book_id = epigraph["book_id"]

    quote_value = request.form.get("quote") if request.method == "POST" else epigraph["quote"]
    notes_value = request.form.get("notes") if request.method == "POST" else (epigraph.get("notes") or "")

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
    current_app.logger.info("Epigraph deleted id=%s", epigraph_id)
    flash("Epigraph removed.", "info")
    return redirect(url_for("main.epigraphs"))


@bp.route("/person-types", methods=["GET", "POST"])
def manage_person_types():
    if request.method == "POST":
        action = request.form.get("action") or ""
        name = (request.form.get("name") or "").strip()
        type_id = request.form.get("type_id")
        try:
            type_id = int(type_id) if type_id else None
        except (TypeError, ValueError):
            type_id = None

        if action == "add":
            if not name:
                flash("Please provide a person type name.", "warning")
                current_app.logger.warning("Person type add blocked: missing name")
            else:
                type_id = db.add_person_type(name)
                flash("Person type added.", "success")
                current_app.logger.info("Person type added id=%s name='%s'", type_id, name)
        elif action == "update" and type_id:
            if not name:
                flash("Please provide a person type name.", "warning")
                current_app.logger.warning("Person type update blocked: missing name for id=%s", type_id)
            else:
                db.update_person_type(type_id, name)
                flash("Person type updated.", "success")
                current_app.logger.info("Person type updated id=%s name='%s'", type_id, name)
        elif action == "delete" and type_id:
            try:
                db.delete_person_type(type_id)
                flash("Person type removed.", "info")
                current_app.logger.info("Person type deleted id=%s", type_id)
            except sqlite3.IntegrityError:
                flash("That person type is in use and cannot be removed.", "danger")
                current_app.logger.warning(
                    "Person type delete blocked by constraint id=%s", type_id
                )
        else:
            flash("Unable to process the request.", "danger")
            current_app.logger.warning(
                "Person type management received unsupported action '%s' (id=%s)",
                action,
                type_id,
            )

        return redirect(url_for("main.manage_person_types"))

    types = db.get_person_types()
    return render_template("person_types.html", types=types)


@bp.route("/utilities/nationalities", methods=["GET", "POST"])
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
                    current_app.logger.warning("Nationality add blocked: missing name")
                else:
                    db.add_nationality(name)
                    flash("Nationality added.", "success")
                    current_app.logger.info("Nationality added name='%s'", name)
            elif action == "update" and nationality_id:
                if not name:
                    flash("Please provide a nationality name.", "warning")
                    current_app.logger.warning("Nationality update blocked: missing name for id=%s", nationality_id)
                else:
                    db.update_nationality(nationality_id, name)
                    flash("Nationality updated.", "success")
                    current_app.logger.info("Nationality updated id=%s name='%s'", nationality_id, name)
            elif action == "delete" and nationality_id:
                db.delete_nationality(nationality_id)
                flash("Nationality removed.", "info")
                current_app.logger.info("Nationality deleted id=%s", nationality_id)
            else:
                flash("Unable to process the request.", "danger")
                current_app.logger.warning(
                    "Nationality management received unsupported action '%s' (id=%s)",
                    action,
                    nationality_id,
                )
        except sqlite3.IntegrityError:
            flash("That nationality is in use and cannot be removed or renamed to an existing entry.", "danger")
            current_app.logger.warning(
                "Nationality change failed due to constraint (action=%s id=%s)", action, nationality_id
            )

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
    return jsonify([{"id": p["id"], "name": p["name"]} for p in results])
