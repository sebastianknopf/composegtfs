from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure backend/src is on sys.path so `app.*` imports work both when
# invoked via startup.py and when running alembic manually.
_HERE = os.path.dirname(__file__)  # backend/alembic/
_SRC = os.path.normpath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Import models so Alembic can detect them
from composegtfs.models import Base  # noqa: F401, E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from environment variable if set
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    # asyncpg driver not supported by synchronous Alembic runner — use plain psycopg2 URL
    _db_url = _db_url.replace("postgresql+asyncpg://", "postgresql://")
    config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
