"""Public pages, authentication, mail delivery, and private scan results."""

import warnings
from pathlib import Path
from smtplib import SMTPException
from urllib.parse import urlsplit
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db, limiter, mail
from app.forms import (
    ContactForm,
    LoginForm,
    RegistrationForm,
    RequestResetForm,
    ResetPasswordForm,
    UpdateAccountForm,
)
from app.inference import InferenceError, predict
from app.models import Scans, User

main = Blueprint("main", __name__)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}


def _deliver(message: Message) -> bool:
    try:
        mail.send(message)
        return True
    except (SMTPException, OSError, ValueError):
        current_app.logger.exception("Email delivery failed")
        return False


def _save_account() -> bool:
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        flash("That username or email is already registered.", "danger")
        return False


@main.get("/")
@main.get("/about")
def about():
    return render_template("about.html", title="About")


@main.get("/help")
def help_page():
    return render_template("help.html", title="Help")


@main.route("/scanner", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per minute", methods=["POST"])
def scanner():
    if request.method == "GET":
        return render_template("scanner.html", title="Scanner")
    upload = request.files.get("imageFile")
    if not upload or not upload.filename:
        flash("Choose an image to scan.", "danger")
        return redirect(url_for("main.scanner"))
    extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        flash("Choose a PNG or JPEG image.", "danger")
        return redirect(url_for("main.scanner"))
    filename = f"{uuid4().hex}.{extension}"
    path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    try:
        upload.save(path)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ValueError("Image format does not match an accepted type.")
                if (image.format == "PNG" and extension != "png") or (
                    image.format == "JPEG" and extension not in {"jpg", "jpeg"}
                ):
                    raise ValueError("Image extension does not match its content.")
                image.verify()
        prediction, probability = predict(path)
        scan = Scans(
            prediction=prediction,
            probability=round(probability, 2),
            user_id=current_user.id,
            filename=filename,
        )
        db.session.add(scan)
        db.session.commit()
    except (
        UnidentifiedImageError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        path.unlink(missing_ok=True)
        flash("This file is not a supported, valid image.", "danger")
        return redirect(url_for("main.scanner"))
    except (InferenceError, SQLAlchemyError, OSError):
        db.session.rollback()
        path.unlink(missing_ok=True)
        current_app.logger.exception("Scan failed")
        flash("Scanning is temporarily unavailable. Please try again later.", "danger")
        return redirect(url_for("main.scanner"))
    flash("Scan saved to your account.", "success")
    return redirect(url_for("main.scan_result", scan_id=scan.id))


@main.get("/scans/<int:scan_id>")
@login_required
def scan_result(scan_id):
    scan = db.session.scalar(
        db.select(Scans).where(Scans.id == scan_id, Scans.user_id == current_user.id)
    )
    if scan is None:
        abort(404)
    return render_template("upload.html", scan=scan, title="Scan result")


@main.get("/uploads/<filename>")
@login_required
def uploaded_image(filename):
    scan = db.session.scalar(
        db.select(Scans).where(Scans.filename == filename, Scans.user_id == current_user.id)
    )
    if scan is None:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@main.route("/contact", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        if not current_app.config.get("CONTACT_EMAIL") or not current_app.config.get(
            "MAIL_DEFAULT_SENDER"
        ):
            flash("Contact delivery is not configured. Please try again later.", "warning")
        else:
            message = Message(
                form.report_title.data,
                recipients=[current_app.config["CONTACT_EMAIL"]],
                reply_to=form.email.data,
                body=form.report_message.data,
            )
            if _deliver(message):
                flash("Your message has been sent.", "success")
                return redirect(url_for("main.contact"))
            flash("Your message could not be sent. Please try again later.", "danger")
    return render_template("contact.html", title="Contact", form=form)


@main.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.scanner"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        if _save_account():
            flash("Your account is ready. You can now sign in.", "success")
            return redirect(url_for("main.login"))
    return render_template("register.html", title="Register", form=form)


@main.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.scanner"))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).where(func.lower(User.email) == form.email.data))
        if user and user.check_password(form.password.data):
            if user.password.startswith(("$2a$", "$2b$", "$2y$")):
                user.set_password(form.password.data)
                db.session.commit()
            login_user(user, remember=form.remember.data)
            flash("You are signed in.", "success")
            next_page = request.args.get("next", "")
            parsed = urlsplit(next_page)
            if (
                next_page.startswith("/")
                and not next_page.startswith("//")
                and not parsed.netloc
                and not parsed.scheme
                and chr(92) not in next_page
            ):
                return redirect(next_page)
            return redirect(url_for("main.scanner"))
        flash("Sign-in failed. Check your email and password.", "danger")
    return render_template("login.html", title="Sign in", form=form)


@main.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You are signed out.", "info")
    return redirect(url_for("main.login"))


@main.get("/account")
@login_required
def account():
    page = request.args.get("page", 1, type=int)
    history = db.paginate(
        db.select(Scans)
        .where(Scans.user_id == current_user.id)
        .order_by(Scans.date_scanned.desc(), Scans.id.desc()),
        page=page,
        per_page=20,
        error_out=False,
    )
    return render_template("account.html", history=history, title="Account")


@main.route("/account/update", methods=["GET", "POST"])
@login_required
def update_account():
    form = UpdateAccountForm(obj=current_user)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        if _save_account():
            flash("Your account has been updated.", "success")
            return redirect(url_for("main.account"))
    return render_template("update_account.html", title="Update account", form=form)


@main.route("/reset_password", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("main.scanner"))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).where(func.lower(User.email) == form.email.data))
        if user and current_app.config.get("MAIL_DEFAULT_SENDER"):
            reset_url = current_app.config["PUBLIC_BASE_URL"] + url_for(
                "main.reset_token", token=user.get_reset_token()
            )
            _deliver(
                Message(
                    "JANOS password reset",
                    recipients=[user.email],
                    body=f"Reset your password within 30 minutes: {reset_url}\n\nIf you did not request this, ignore this email.",
                )
            )
        flash("If an account matches that email, reset instructions will be sent.", "info")
        return redirect(url_for("main.login"))
    return render_template("reset_request.html", title="Reset password", form=form)


@main.route("/reset_password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def reset_token(token):
    user = User.verify_reset_token(token)
    if user is None:
        flash("This reset link is invalid or has expired.", "warning")
        return redirect(url_for("main.reset_request"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Your password has been updated. Please sign in.", "success")
        return redirect(url_for("main.login"))
    return render_template("reset_token.html", title="Reset password", form=form)
