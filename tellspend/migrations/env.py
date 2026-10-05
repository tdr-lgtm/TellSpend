from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from tellspend.database.config import settings
from tellspend.database.models import Base


# Alembic Config object (the values from alembic.ini).
config = context.config


# Configure Python logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Use the same DATABASE_URL as the application. "%" is doubled because
# the ini parser treats a single "%" as the start of a variable.
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("%", "%%"),
)


# The table definitions that autogenerate compares the database against.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Explanation:
        Run migrations without a database connection: the SQL is printed
        instead of executed (alembic upgrade head --sql).

    Parameters:
        None.

    Returns:
        None.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Explanation:
        Run migrations against the live database.

    Parameters:
        None.

    Returns:
        None.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()