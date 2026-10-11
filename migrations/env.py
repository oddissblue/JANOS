"""Alembic integration for current Flask-SQLAlchemy."""

from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config
fileConfig(config.config_file_name)
database = current_app.extensions["migrate"].db
config.set_main_option(
    "sqlalchemy.url", database.engine.url.render_as_string(hide_password=False).replace("%", "%%")
)


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=database.metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    options = dict(current_app.extensions["migrate"].configure_args)
    with database.engine.connect() as connection:
        context.configure(connection=connection, target_metadata=database.metadata, **options)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
