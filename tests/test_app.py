"""Regression checks for authentication, private uploads, and failure handling."""

import io
from pathlib import Path
from smtplib import SMTPException

import bcrypt
from flask import url_for

from app.extensions import db, mail
from app.inference import InferenceError
from app.models import Scans, User
from tests.conftest import PASSWORD


def test_pages_and_security_headers(client):
    for page in ["/", "/about", "/help", "/contact", "/login", "/register"]:
        response = client.get(page)
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/scanner").status_code == 302
    assert client.get("/account").status_code == 302
    assert client.get("/admin/dashboard").status_code == 404


def test_factory_instances_are_independent(app):
    from app import create_app

    another = create_app({"TESTING": True, "SECRET_KEY": "other", "RATELIMIT_ENABLED": False})
    assert another is not app
    assert app.config["SECRET_KEY"] == "test-only-secret"


def test_account_updates_are_prefilled(auth, app):
    assert b"test@example.com" in auth.get("/account/update").data
    assert (
        auth.post(
            "/account/update", data={"username": "updated", "email": "NEW@example.com"}
        ).status_code
        == 302
    )
    with app.app_context():
        assert db.session.scalar(db.select(User)).email == "new@example.com"


def test_registration_validation(client, app):
    response = client.post(
        "/register",
        data={
            "username": "okname",
            "email": "test@example.com",
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(User)) is None


def test_duplicate_account(client, auth):
    auth.post("/logout")
    response = client.post(
        "/register",
        data={
            "username": "tester",
            "email": "test@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert response.status_code == 200
    assert b"already registered" in response.data


def test_legacy_bcrypt_login_upgrades_hash(client, app):
    with app.app_context():
        user = User(
            username="legacy",
            email="LEGACY@example.com",
            password=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        )
        db.session.add(user)
        db.session.commit()
    response = client.post("/login", data={"email": "legacy@example.com", "password": PASSWORD})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(User)).password.startswith("scrypt:")
    assert client.get("/account").status_code == 200


def test_reset_token_expiry_and_single_use(auth, app):
    with app.app_context():
        user = db.session.scalar(db.select(User))
        token = user.get_reset_token()
        assert User.verify_reset_token(token).id == user.id
        assert User.verify_reset_token("invalid") is None
        assert User.verify_reset_token(token, expires_sec=-1) is None
    auth.post("/logout")
    response = auth.post(
        "/reset_password/" + token,
        data={"password": "new-secure-password-456", "confirm_password": "new-secure-password-456"},
    )
    assert response.status_code == 302
    with app.app_context():
        assert User.verify_reset_token(token) is None
        assert db.session.scalar(db.select(User)).check_password("new-secure-password-456")


def test_reset_email_uses_configured_origin(auth, app):
    auth.post("/logout")
    app.config["PUBLIC_BASE_URL"] = "https://janos.example"
    with mail.record_messages() as messages:
        response = auth.post(
            "/reset_password",
            data={"email": "test@example.com"},
            headers={"Host": "untrusted.example"},
        )
        assert response.status_code == 302
        assert len(messages) == 1
        assert "https://janos.example/reset_password/" in messages[0].body
        assert "untrusted.example" not in messages[0].body


def test_reset_does_not_enumerate_accounts(client):
    with mail.record_messages() as messages:
        response = client.post(
            "/reset_password", data={"email": "missing@example.com"}, follow_redirects=True
        )
        assert b"If an account matches" in response.data
        assert not messages


def test_contact_and_smtp_failure(client, monkeypatch):
    data = {"email": "test@example.com", "report_title": "Question", "report_message": "Hello"}
    with mail.record_messages() as messages:
        assert client.post("/contact", data=data).status_code == 302
        assert messages[0].reply_to == "test@example.com"

    def fail(message):
        raise SMTPException("Unavailable")

    monkeypatch.setattr(mail, "send", fail)
    response = client.post("/contact", data=data)
    assert response.status_code == 200
    assert b"could not be sent" in response.data


def test_login_redirect_is_local(auth):
    for target in ["https://example.com", "//example.com", "/\\example.com"]:
        auth.post("/logout")
        response = auth.post(
            "/login",
            query_string={"next": target},
            data={"email": "test@example.com", "password": PASSWORD},
        )
        assert response.location == "/scanner"


def test_scan_persists_ownership_across_sessions(auth, app, image_bytes, monkeypatch):
    monkeypatch.setattr("app.views.predict", lambda path: ("Normal", 95.0))
    response = auth.post("/scanner", data={"imageFile": (image_bytes, "private-patient-name.png")})
    assert response.status_code == 302
    assert response.location.startswith("/scans/")
    with app.app_context():
        scan = db.session.scalar(db.select(Scans))
        filename = scan.filename
        assert "patient" not in filename
        assert scan.probability == 95.0
    assert auth.get(response.location).status_code == 200
    assert auth.get("/uploads/" + filename).status_code == 200
    assert auth.get("/static/uploads/" + filename).status_code == 404
    auth.post("/logout")
    auth.post("/login", data={"email": "test@example.com", "password": PASSWORD})
    assert auth.get("/uploads/" + filename).status_code == 200
    other = app.test_client()
    other.post(
        "/register",
        data={
            "username": "other",
            "email": "other@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    other.post("/login", data={"email": "other@example.com", "password": PASSWORD})
    assert other.get("/uploads/" + filename).status_code == 404
    assert other.get(response.location).status_code == 404


def test_invalid_and_missing_uploads(auth, app):
    assert auth.post("/scanner").status_code == 302
    assert (
        auth.post("/scanner", data={"imageFile": (io.BytesIO(b"x"), "bad.txt")}).status_code == 302
    )
    assert (
        auth.post(
            "/scanner", data={"imageFile": (io.BytesIO(b"not an image"), "bad.png")}
        ).status_code
        == 302
    )
    assert not list(Path(app.config["UPLOAD_FOLDER"]).iterdir())


def test_inference_failure_does_not_save_scan(auth, app, image_bytes, monkeypatch):
    def fail(path):
        raise InferenceError("Missing model")

    monkeypatch.setattr("app.views.predict", fail)
    response = auth.post("/scanner", data={"imageFile": (image_bytes, "valid.png")})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(Scans)) is None
    assert not list(Path(app.config["UPLOAD_FOLDER"]).iterdir())


def test_scanner_enforces_size_and_csrf(auth, app):
    app.config["MAX_CONTENT_LENGTH"] = 100
    assert (
        auth.post("/scanner", data={"imageFile": (io.BytesIO(b"x" * 200), "large.png")}).status_code
        == 413
    )
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.config["WTF_CSRF_ENABLED"] = True
    assert auth.post("/scanner").status_code == 400
    assert auth.post("/logout").status_code == 400
    assert auth.get("/logout").status_code == 405


def test_history_pagination(auth, app):
    with app.app_context():
        user = db.session.scalar(db.select(User))
        db.session.add_all(
            [Scans(prediction="Normal", probability=95, user_id=user.id) for _ in range(21)]
        )
        db.session.commit()
    assert b"Page 1 of 2" in auth.get("/account").data
    assert b"Page 2 of 2" in auth.get("/account?page=2").data


def test_template_endpoints_exist(app):
    with app.test_request_context():
        for endpoint in [
            "main.about",
            "main.scanner",
            "main.help_page",
            "main.contact",
            "main.register",
            "main.login",
            "main.logout",
            "main.account",
            "main.update_account",
            "main.reset_request",
        ]:
            assert url_for(endpoint).startswith("/")


def test_readiness(client, app, tmp_path):
    assert client.get("/health/live").status_code == 200
    app.config["MODEL_PATH"] = str(tmp_path / "missing.h5")
    assert client.get("/health/ready").status_code == 503
    model = tmp_path / "present.h5"
    model.write_bytes(b"\x89HDF\r\n\x1a\n" + b"x" * 2048)
    app.config["MODEL_PATH"] = str(model)
    assert client.get("/health/ready").status_code == 200


def test_password_change_revokes_existing_session(auth, app):
    with app.app_context():
        user = db.session.scalar(db.select(User))
        user.set_password("changed-secure-password-789")
        db.session.commit()
    assert auth.get("/account").status_code == 302


def test_rate_limit_is_enforced(tmp_path, monkeypatch):
    from app import create_app

    monkeypatch.setenv("JANOS_DATA_DIR", str(tmp_path / "rate-data"))
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": True,
            "RATELIMIT_STORAGE_URI": "memory://",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        }
    )
    with application.app_context():
        db.create_all()
    client = application.test_client()
    for _ in range(10):
        assert (
            client.post(
                "/login", data={"email": "nobody@example.com", "password": "wrong"}
            ).status_code
            == 200
        )
    assert (
        client.post("/login", data={"email": "nobody@example.com", "password": "wrong"}).status_code
        == 429
    )
    with application.app_context():
        db.session.remove()
        db.engine.dispose()
