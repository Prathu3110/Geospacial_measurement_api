import os

# Set before app.db creates its engine, so tests use their own database, never dev data.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://geo:geo@localhost:5432/geomeasure_test"
)

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


@pytest.fixture(scope="session")
def database():
    """Create the test database if needed and migrate it, so the migration itself is tested."""
    from alembic import command
    from alembic.config import Config

    url = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        query = text("SELECT 1 FROM pg_database WHERE datname = :name")
        exists = conn.scalar(query, {"name": url.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def client(database):
    from fastapi.testclient import TestClient

    from app.db import engine
    from app.main import app

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE uploaded_files CASCADE"))
    return TestClient(app)
