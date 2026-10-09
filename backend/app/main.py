from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.db import engine

app = FastAPI(title="Geospatial File Measurement API")


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with engine.connect() as conn:
            postgis = conn.execute(text("SELECT postgis_version()")).scalar_one()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "postgis": postgis}
