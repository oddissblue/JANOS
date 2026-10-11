"""Isolated application and database fixtures."""

import io

import pytest
from PIL import Image

from app import create_app
from app.extensions import db

PASSWORD = "a-secure-password-123"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("JANOS_DATA_DIR", str(tmp_path / "data"))
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "test.db").as_posix(),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
            "MAIL_SUPPRESS_SEND": True,
            "MAIL_DEFAULT_SENDER": "janos@example.com",
            "CONTACT_EMAIL": "contact@example.com",
        }
    )
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(client):
    response = client.post(
        "/register",
        data={
            "username": "tester",
            "email": "test@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert response.status_code == 302
    response = client.post("/login", data={"email": "test@example.com", "password": PASSWORD})
    assert response.status_code == 302
    return client


@pytest.fixture
def image_bytes():
    image = io.BytesIO()
    Image.new("RGB", (8, 8)).save(image, format="PNG")
    image.seek(0)
    return image
