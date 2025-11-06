from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder

from ..db_postgres import fetch_all

app = FastAPI(title="Referent API")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/people")
async def list_people():
    sql = """
        SELECT
            id,
            name,
            type_id,
            nationality_id,
            sex,
            birth_year,
            birth_year_era,
            death_year,
            death_year_era,
            created_at,
            updated_at
        FROM people
        ORDER BY name
    """
    try:
        rows = fetch_all(sql)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to load people from Postgres") from exc
    return {"results": jsonable_encoder(rows)}
