# local imports
from app import app, db, bcrybt, User, Scans, mail
from app.forms import RegisterationForm, LoginForm, ContactForm, UpdateAccountForm, RequestResetForm, ResetPasswordForm

# global imports
from flask import flash, redirect, url_for, render_template, request, session, send_from_directory, abort
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message
from werkzeug.utils import secure_filename
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
from PIL import Image, UnidentifiedImageError
import os

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
model = None


def model_pred(path):
    """Load the legacy Keras model only when inference is requested."""
    global model
    import numpy as np
    from tensorflow.keras.models import load_model
    from tensorflow.keras.preprocessing.image import load_img, img_to_array

    if model is None:
        model = load_model(app.config['MODEL_PATH'], compile=False)
    img = img_to_array(load_img(path, target_size=(224, 224))) / 255.0
    probability = float(np.asarray(model.predict(np.expand_dims(img, axis=0), verbose=0)).item())
    if probability > 0.5:
        return 'Pneumonia', probability * 100
    return 'Normal', (1 - probability) * 100


@app.route('/uploads/<filename>')
@login_required
def uploaded_image(filename):
    if filename not in session.get('uploads', []):
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# checking the file type:
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# scanner/upload page:
@app.route("/")
@app.route('/scanner', methods=['GET', 'POST'])
@login_required
def scanner():
    # checks if post request was submitted
    if request.method == 'POST':
        # check if the post request has the file part
        if 'imageFile' not in request.files:
            flash(f'No file part', "danger")
            return redirect(request.url)
        # check if filename is an empty string
        file = request.files['imageFile']
        if file.filename == '':
            flash(f'No selected file', "danger")
            return redirect(request.url)
        # if file is uploaded
        if file and allowed_file(file.filename):
            filename = f'{uuid4().hex}_{secure_filename(file.filename)}'
            imgPath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(imgPath)
            try:
                with Image.open(imgPath) as image:
                    image.verify()
                predection, probability = model_pred(imgPath)
            except (UnidentifiedImageError, OSError, ValueError, ImportError):
                Path(imgPath).unlink(missing_ok=True)
                flash('Unable to scan this image. Check the image and inference setup.', 'danger')
                return redirect(url_for('scanner'))
            session['uploads'] = (session.get('uploads', []) + [filename])[-10:]
            # perfroming prediction and saving the results in the database
            saved_scan = Scans(prediction=predection,probability=round(probability, 2),user_id=current_user.id)
            db.session.add(saved_scan)
            db.session.commit()
            flash(f"Scan successful!", "success")
            return render_template('upload.html', name=filename, predection=predection, probability=round(probability, 2), title="- Results")
        else:
            flash(f"Please select an image file!", "danger")
            return redirect(url_for('scanner'))
    return render_template("scanner.html", title="- Scanner")

# about page:
@app.route("/about")
def about():
    return render_template("about.html", title='- About')

# help page:
@app.route("/help")
def help():
    return render_template("help.html", title='- Help')

# contact page:
@app.route("/contact", methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        if not app.config.get('CONTACT_EMAIL') or not app.config.get('MAIL_DEFAULT_SENDER'):
            flash('Contact delivery is not configured. Please try again later.', 'warning')
            return redirect(url_for('contact'))
        msg = Message(form.report_title.data, recipients=[app.config['CONTACT_EMAIL']],
                      reply_to=form.email.data, body=form.report_message.data)
        mail.send(msg)
        flash('Report sent successfully!', 'success')
        return redirect(url_for('about'))
    return render_template("contact.html", title='- Contact Us', form = form)

# register page:
@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('scanner'))
    form = RegisterationForm()
    if form.validate_on_submit():
        hashed_password = bcrybt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email = form.email.data, password = hashed_password)
        db.session.add(user)
        db.session.commit()
        flash(f'Your account has been created! You are now able to login', 'success')
        return redirect(url_for('login'))
    return render_template("register.html", title='- Register', form = form)

# login page:
@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('scanner'))
    form = LoginForm()
    if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user and bcrybt.check_password_hash(user.password, form.password.data):
                login_user(user, remember=form.remember.data)
                next_page = request.args.get('next')
                flash(f"You have been logged in!", "success")
                if next_page and next_page.startswith('/') and not next_page.startswith('//') and not urlsplit(next_page).netloc and not urlsplit(next_page).scheme and '\\' not in next_page:
                    return redirect(next_page)
                return redirect(url_for('scanner'))
            else:
                flash(f"Login Unseccessful. Please check email and password", "danger")
    return render_template("login.html", title='- Login', form = form)

# logout page:
@app.route("/logout")
def logout():
    logout_user()
    session.pop('uploads', None)
    flash(f"You have been logged out!", "danger")
    return redirect(url_for("scanner"))

# account page:
@app.route("/account")
@login_required
def account():
    history_scans = Scans.query.filter_by(user_id=current_user.id).all()
    return render_template("account.html", history_scans=history_scans, title='- Account')

# update account page:
@app.route("/account/update", methods=['GET', 'POST'])
@login_required
def update_account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash(f'Your account has been updated!', 'success')
        return redirect(url_for('account'))
    return render_template("update_account.html", title='- Update Account', form = form)

# requesting reset token page (email):
def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Restet Request', recipients=[user.email])
    msg.body = f''' To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}
    
If you did not make this request then simply ignore this email and no changes will be made
'''
    mail.send(msg)
# reset password page
@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('scanner'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if not app.config.get('MAIL_DEFAULT_SENDER'):
            flash('Password reset email is not configured.', 'warning')
            return redirect(url_for('reset_request'))
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password', 'info')
        return redirect(url_for('login'))
    return render_template("reset_request.html", title='- Reset Password', form=form)
@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('scanner'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('Expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrybt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash(f'Your password has been updated! You are now able to login', 'success')
        return redirect(url_for('login'))
    return render_template("reset_token.html", title='- Reset Password', form=form)