"""Verify fresh schema creation and preservation of legacy account data."""

from pathlib import Path

import pytest
from flask_migrate import stamp, upgrade
from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db

MIGRATIONS = str(Path(__file__).resolve().parent.parent / "migrations")


@pytest.mark.parametrize("legacy", [False, True])
def test_database_migrations(tmp_path, monkeypatch, legacy):
    monkeypatch.setenv("JANOS_DATA_DIR", str(tmp_path / "data"))
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "RATELIMIT_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "migration.db").as_posix(),
        }
    )
    with app.app_context():
        if legacy:
            upgrade(directory=MIGRATIONS, revision="0001")
            db.session.execute(
                text(
                    "INSERT INTO user (id,username,email,password) VALUES (1,'legacy','legacy@example.com','original-hash')"
                )
            )
            db.session.execute(
                text(
                    "INSERT INTO scans (id,date_scanned,prediction,probability,user_id) VALUES (1,'2022-01-01','Normal',90,1)"
                )
            )
            db.session.commit()
            # An original installation has these tables but no Alembic version.
            db.session.execute(text("DROP TABLE alembic_version"))
            db.session.commit()
            stamp(directory=MIGRATIONS, revision="0001")
        upgrade(directory=MIGRATIONS)
        upgrade(directory=MIGRATIONS)
        columns = {column["name"]: column for column in inspect(db.engine).get_columns("user")}
        assert columns["password"]["type"].length == 255
        assert "filename" in {column["name"] for column in inspect(db.engine).get_columns("scans")}
        if legacy:
            assert (
                db.session.scalar(text("SELECT password FROM user WHERE id=1")) == "original-hash"
            )
            assert db.session.scalar(text("SELECT prediction FROM scans WHERE id=1")) == "Normal"
        db.session.remove()
        db.engine.dispose()
