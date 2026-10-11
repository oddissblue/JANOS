"""Validated forms for account and mail workflows."""

from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import BooleanField, PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.extensions import db
from app.models import User


def normalize_email(value):
    return value.strip().lower() if value else value


def strip_text(value):
    return value.strip() if value else value


class AccountFields(FlaskForm):
    username = StringField(
        "Username", filters=[strip_text], validators=[DataRequired(), Length(min=3, max=20)]
    )
    email = StringField(
        "Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=120)]
    )

    def _validate_unique(self, column, value, message):
        query = db.select(User).where(column == value)
        if current_user.is_authenticated:
            query = query.where(User.id != current_user.id)
        if db.session.scalar(query):
            raise ValidationError(message)

    def validate_username(self, field):
        self._validate_unique(User.username, field.data, "This username is already registered.")

    def validate_email(self, field):
        self._validate_unique(
            func.lower(User.email), field.data, "This email is already registered."
        )


class RegistrationForm(AccountFields):
    password = PasswordField("Password", validators=[DataRequired(), Length(min=12, max=128)])
    confirm_password = PasswordField(
        "Confirm password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField(
        "Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=120)]
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class ContactForm(FlaskForm):
    email = StringField(
        "Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=120)]
    )
    report_title = StringField(
        "Subject", filters=[strip_text], validators=[DataRequired(), Length(max=150)]
    )
    report_message = TextAreaField(
        "Message", filters=[strip_text], validators=[DataRequired(), Length(max=5000)]
    )
    submit = SubmitField("Send message")

    def validate_report_title(self, field):
        if "\r" in field.data or "\n" in field.data:
            raise ValidationError("Use a single line for the subject.")


class UpdateAccountForm(AccountFields):
    submit = SubmitField("Save changes")


class RequestResetForm(FlaskForm):
    email = StringField(
        "Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=120)]
    )
    submit = SubmitField("Send reset instructions")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=12, max=128)])
    confirm_password = PasswordField(
        "Confirm password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Reset password")
