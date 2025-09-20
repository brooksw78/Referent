import requests

def get_book_data_from_isbn(isbn):
    url = f"https://openlibrary.org/api/books"
    params = {
        "bibkeys": f"ISBN:{isbn}",
        "format": "json",
        "jscmd": "data"
    }

    response = requests.get(url, params=params)
    data = response.json()
    key = f"ISBN:{isbn}"

    if key not in data:
        return None

    book = data[key]
    title = book.get("title")
    authors = [a["name"] for a in book.get("authors", [])]
    publish_date = book.get("publish_date")
    cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

    return {
        "title": title,
        "authors": authors,
        "publication_year": publish_date,
        "isbn": isbn,
        "cover_url": cover_url
    }
    
def search_books_by_title_and_author(title, author):
    params = {
        "title": title,
        "author": author,
        "limit": 5,
    }
    resp = requests.get("https://openlibrary.org/search.json", params=params)
    data = resp.json()

    results = []
    for doc in data.get("docs", []):
        isbn_list = doc.get("isbn", [])
        isbn = isbn_list[0] if isbn_list else None
        cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg" if isbn else None

        results.append({
            "title": doc.get("title"),
            "authors": doc.get("author_name", []),
            "publication_year": doc.get("first_publish_year"),
            "isbn": isbn,
            "cover_url": cover_url
        })

    return results
