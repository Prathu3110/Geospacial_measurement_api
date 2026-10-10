from alembic import context

from app.db import engine
from app.models import Base

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # The postgis image ships tiger/topology tables; never autogenerate drops for them.
    return not (reflected and compare_to is None)


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, include_object=include_object
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
