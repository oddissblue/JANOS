"""Persistent users and scan results."""

import hashlib
import secrets
from datetime import UTC, datetime

import bcrypt
from flask import current_app
from flask_login import UserMixin
from itsdangerous import BadData, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model, UserMixin):
    """An account using scrypt; legacy bcrypt hashes remain valid."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    scans = db.relationship("Scans", backref="user", lazy=True)

    def set_password(self, password: str) -> None:
        self.password = generate_password_hash(password)

    def get_id(self) -> str:
        """Changing a password also revokes existing sessions and remember cookies."""
        return f"{self.id}:{hashlib.sha256(self.password.encode()).hexdigest()}"

    def check_password(self, password: str) -> bool:
        if self.password.startswith(("$2a$", "$2b$", "$2y$")):
            try:
                # Old bcrypt versions truncated inputs at 72 bytes.
                return bcrypt.checkpw(password.encode()[:72], self.password.encode())
            except ValueError:
                return False
        return check_password_hash(self.password, password)

    def get_reset_token(self) -> str:
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")
        return serializer.dumps(
            {"user_id": self.id, "password": hashlib.sha256(self.password.encode()).hexdigest()}
        )

    @staticmethod
    def verify_reset_token(token: str, expires_sec: int = 1800):
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")
        try:
            payload = serializer.loads(token, max_age=expires_sec)
            user = db.session.get(User, int(payload["user_id"]))
            if user and secrets.compare_digest(
                payload["password"], hashlib.sha256(user.password.encode()).hexdigest()
            ):
                return user
        except (BadData, KeyError, TypeError, ValueError):
            return None
        return None


class Scans(db.Model):
    """A model result owned by one user; filenames omit original image names."""

    id = db.Column(db.Integer, primary_key=True)
    date_scanned = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    prediction = db.Column(db.String(20), nullable=False)
    probability = db.Column(db.Float, nullable=False)
    filename = db.Column(db.String(100), unique=True, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
