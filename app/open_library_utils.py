import logging

import requests


logger = logging.getLogger(__name__)


def fetch_cover_url(isbn, size="L"):
    if not isbn:
        return None
    base = f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"
    test_url = f"{base}?default=false"
    try:
        response = requests.get(test_url, timeout=5)
        if response.status_code == 200 and response.content:
            return test_url
        logger.debug("Open Library cover not found for ISBN %s (status %s)", isbn, response.status_code)
    except requests.RequestException as exc:
        logger.warning("Open Library cover request failed for ISBN %s: %s", isbn, exc)
        return None
    return None


def get_book_data_from_isbn(isbn):
    if not isbn:
        logger.debug("No ISBN supplied for lookup")
        return None, "Enter an ISBN to search Open Library."

    url = "https://openlibrary.org/api/books"
    params = {
        "bibkeys": f"ISBN:{isbn}",
        "format": "json",
        "jscmd": "data",
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning("Open Library book lookup failed for ISBN %s: %s", isbn, exc)
        return None, "We couldn't reach Open Library. Please try again in a moment."

    key = f"ISBN:{isbn}"

    if key not in data:
        logger.info("Open Library returned no data for ISBN %s", isbn)
        return None, f"No Open Library record found for ISBN {isbn}."

    book = data[key]
    title = book.get("title")
    authors = [a["name"] for a in book.get("authors", [])]
    publish_date = book.get("publish_date")
    cover_url = fetch_cover_url(isbn)

    return {
        "title": title,
        "authors": authors,
        "publication_year": publish_date,
        "isbn": isbn,
        "cover_url": cover_url,
    }, None


def search_books_by_title_and_author(title, author):
    params = {"limit": 5}
    if title:
        params["title"] = title
    if author:
        params["author"] = author

    if len(params) == 1:
        logger.debug("Search requested without title or author")
        return [], "Enter a title, author, or both to search Open Library."

    try:
        resp = requests.get("https://openlibrary.org/search.json", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning(
            "Open Library search failed for title=%s author=%s: %s",
            title,
            author,
            exc,
        )
        return [], "We couldn't reach Open Library. Please try again later."

    results = []
    for doc in data.get("docs", []):
        isbn_list = doc.get("isbn", [])
        isbn = isbn_list[0] if isbn_list else None
        cover_url = fetch_cover_url(isbn) if isbn else None

        results.append(
            {
                "title": doc.get("title"),
                "authors": doc.get("author_name", []),
                "publication_year": doc.get("first_publish_year"),
                "isbn": isbn,
                "cover_url": cover_url,
            }
        )

    if not results:
        logger.info(
            "Open Library search returned no results for title=%s author=%s",
            title,
            author,
        )
        return [], "No Open Library results matched that search."

    return results, None
