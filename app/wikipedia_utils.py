import re
import wikipediaapi

wiki = wikipediaapi.Wikipedia(
    language="en",
    user_agent="ReferentApp/1.0 (referent@app.local)"
)

def extract_years_from_parenthesis(text):
    # Only examine the first parenthetical group
    match = re.search(r'\(([^)]+)\)', text)
    if not match:
        return None, None

    contents = match.group(1)

    # Now extract two 4-digit years from that group
    year_match = re.search(r'.*?(\d{4}).*?[–-].*?(\d{4}|present)', contents)
    if year_match:
        birth_year = int(year_match.group(1))
        death_part = year_match.group(2)
        death_year = None if death_part == "present" else int(death_part)
        return birth_year, death_year

    return None, None

def get_wikipedia_info(name):
    page = wiki.page(name)
    if not page.exists():
        return (None, "No Wikipedia page found.", None, None)

    summary = page.summary
    birth_year, death_year = extract_years_from_parenthesis(summary)

    return (page.fullurl, summary, birth_year, death_year)