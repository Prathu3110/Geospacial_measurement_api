import os

from sqlalchemy import create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://geo:geo@localhost:5432/geomeasure"
)

# pool_pre_ping drops connections the DB closed while idle (e.g. after a container restart).
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
