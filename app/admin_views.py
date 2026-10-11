# Local imports:
from app import app
# from app.forms import RegisterationForm, LoginForm, ContactForm, UploadForm

# Global imports:
from flask import flash, redirect, url_for, render_template, send_from_directory, request

# Admin dashboard page:
@app.route("/admin/dashboard")
def admin_dashboard():
    return "admin dashboard"

# Admin profile page:
@app.route("/admin/profile")
def admin_profile():
    return "admin profile"