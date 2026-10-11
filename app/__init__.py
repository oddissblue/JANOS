# global imports
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin
from datetime import datetime
import secrets
from pathlib import Path
from itsdangerous import BadSignature, SignatureExpired
import os
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from itsdangerous.url_safe import URLSafeTimedSerializer as Serializer

# Configuration comes from the environment; runtime data stays outside static assets.
app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///database.db'),
    UPLOAD_FOLDER=str(Path(app.instance_path) / 'uploads'),
    MODEL_PATH=os.environ.get('MODEL_PATH', str(Path(app.root_path) / 'janos-vgg16-model.h5')),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# password hashing configs
bcrybt = Bcrypt(app)

# Login configs
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# reset password emailing configs
app.config.update(
    MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.environ.get('MAIL_PORT', '465')),
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME'),
    MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'false').lower() == 'true',
    MAIL_USE_SSL=os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true',
    CONTACT_EMAIL=os.environ.get('CONTACT_EMAIL'),
)
mail = Mail(app)

# login manager configs
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

#database tables
# users table
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    scans = db.relationship('Scans', backref='user', lazy=True)
    # reset token requests
    def get_reset_token(self):
        s = Serializer(app.config['SECRET_KEY'], salt='password-reset')
        return s.dumps({'user_id': self.id})
    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        s = Serializer(app.config['SECRET_KEY'], salt='password-reset')
        try:
            user_id = s.loads(token, max_age=expires_sec)['user_id']
        except (BadSignature, SignatureExpired, KeyError, TypeError):
            return None
        return db.session.get(User, user_id)
    # what to display from the database (user table)
    def __repr__(self):
        return f"User('{self.username}', '{self.email}')"
# scans table
class Scans(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_scanned = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    prediction = db.Column(db.String(20), nullable=False)
    probability = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # what to display from the database (scans table)
    def __repr__(self):
        return f"Scans('{self.date_scanned}','{self.prediction}','{self.probability}')"

# initializing the database tables
with app.app_context():
    db.create_all()

# initializing the application
print("Loading Application ...")

# local imports
from app import views
from app import admin_views

def create_app():
    """Return the configured Flask application for Flask CLI discovery."""
    return app
