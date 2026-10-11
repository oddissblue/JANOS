"""Flask application factory and environment configuration."""

import logging
import os
import secrets
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, render_template, request
from sqlalchemy import text

from app.extensions import csrf, db, limiter, login_manager, mail, migrate


def _boolean(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes"}


def create_app(test_config: dict | None = None) -> Flask:
    """Create an independent app. Schema changes belong to migrations, not imports."""
    load_dotenv()
    data_dir = Path(
        os.environ.get("JANOS_DATA_DIR", Path(__file__).resolve().parent.parent / "instance")
    )
    app = Flask(__name__, instance_path=str(data_dir.resolve()), instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///database.db"),
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        UPLOAD_FOLDER=str(data_dir.resolve() / "uploads"),
        MODEL_PATH=os.environ.get("MODEL_PATH", str(Path(app.root_path) / "janos-vgg16-model.h5")),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=128 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_boolean("COOKIE_SECURE"),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=_boolean("COOKIE_SECURE"),
        MAIL_SERVER=os.environ.get("MAIL_SERVER", "localhost"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", "1025")),
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME") or None,
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD") or None,
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_DEFAULT_SENDER", "janos@localhost"),
        MAIL_USE_TLS=_boolean("MAIL_USE_TLS"),
        MAIL_USE_SSL=_boolean("MAIL_USE_SSL"),
        CONTACT_EMAIL=os.environ.get("CONTACT_EMAIL", "contact@localhost"),
        PUBLIC_BASE_URL=os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        RATELIMIT_STORAGE_URI=os.environ.get("REDIS_URL", "memory://"),
        RATELIMIT_STRATEGY="fixed-window",
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        if _boolean("JANOS_PRODUCTION"):
            raise RuntimeError("SECRET_KEY must be configured in production.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning(
            "Temporary session secret: configure SECRET_KEY for persistent sessions."
        )
    if _boolean("JANOS_PRODUCTION") and len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Production SECRET_KEY must contain at least 32 random characters.")
    if app.config["MAIL_USE_TLS"] and app.config["MAIL_USE_SSL"]:
        raise ValueError("Enable MAIL_USE_TLS or MAIL_USE_SSL, not both.")
    data_dir.mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    for extension in (db, csrf, login_manager, mail, limiter):
        extension.init_app(app)
    migrate.init_app(app, db, render_as_batch=True, compare_type=True)
    login_manager.login_view = "main.login"
    login_manager.login_message_category = "info"

    from app.models import User
    from app.views import main

    @login_manager.user_loader
    def load_user(user_id):
        try:
            identifier, fingerprint = user_id.split(":", 1)
            user = db.session.get(User, int(identifier))
            if user and secrets.compare_digest(user.get_id(), f"{identifier}:{fingerprint}"):
                return user
            return None
        except (TypeError, ValueError):
            return None

    app.register_blueprint(main)

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            db.session.execute(text("SELECT 1"))
            db.session.execute(db.select(User.id).limit(1))
            model_path = Path(app.config["MODEL_PATH"])
            if not model_path.is_file() or model_path.stat().st_size < 1024:
                return {"status": "unavailable"}, 503
            with model_path.open("rb") as model_file:
                signature = model_file.read(8)
            if signature != b"\x89HDF\r\n\x1a\n" and not signature.startswith(b"PK"):
                return {"status": "unavailable"}, 503
            if app.config.get("RATELIMIT_ENABLED", True) and not limiter.storage.check():
                return {"status": "unavailable"}, 503
            return {"status": "ok"}
        except Exception:
            db.session.rollback()
            app.logger.exception("Readiness check failed")
            return {"status": "unavailable"}, 503

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(429)
    @app.errorhandler(500)
    def error_page(error):
        return render_template("error.html", code=error.code, message=error.description), error.code

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'self'; object-src 'none'"
        )
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.cli.command("check-model")
    @click.argument("image", type=click.Path(exists=True, path_type=Path))
    def check_model(image):
        """Run a real prediction to verify model/runtime compatibility."""
        from app.inference import predict

        prediction, confidence = predict(image)
        click.echo(f"{prediction}: {confidence:.4f}%")

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    return app
