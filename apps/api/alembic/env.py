from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

# Make sure app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.infrastructure.db.base import Base
import app.infrastructure.db.models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def _database_url() -> str:
    """Render/production: POSTGRES_URL env var. Local fallback: alembic.ini."""
    url = os.getenv("POSTGRES_URL", "").strip()
    if not url:
        url = config.get_main_option("sqlalchemy.url") or ""
    # SQLAlchemy 2.x expects postgresql:// (Render may supply postgres://)
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def run_migrations_offline():
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()