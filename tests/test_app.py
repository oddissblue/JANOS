import io
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

_runtime = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(_runtime.name) / 'test.db').as_posix()
os.environ['SECRET_KEY'] = 'test-secret'

from app import User, app, bcrybt, db, mail


@pytest.fixture
def client(tmp_path):
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, UPLOAD_FOLDER=str(tmp_path),
                      MAIL_SUPPRESS_SEND=True, MAIL_DEFAULT_SENDER='test@example.com',
                      CONTACT_EMAIL='contact@example.com')
    mail.init_app(app)
    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def register_and_login(client):
    assert client.post('/register', data=dict(username='tester', email='test@example.com',
                       password='password', confirm_password='password')).status_code == 302
    assert client.post('/login', data=dict(email='test@example.com', password='password')).status_code == 302


def test_pages_and_authentication(client):
    for page in ['/about', '/help', '/contact', '/login', '/register']:
        assert client.get(page).status_code == 200
    assert client.get('/scanner').status_code == 302
    register_and_login(client)
    assert client.get('/scanner').status_code == 200
    assert client.get('/account').status_code == 200
    assert client.post('/account/update', data=dict(username='updated', email='new@example.com')).status_code == 302


def test_reset_tokens_and_password(client):
    register_and_login(client)
    with app.app_context():
        user = User.query.first()
        token = user.get_reset_token()
        assert User.verify_reset_token(token).id == user.id
        assert User.verify_reset_token('invalid') is None
        assert User.verify_reset_token(token, expires_sec=-1) is None
    client.get('/logout')
    with mail.record_messages() as messages:
        assert client.post('/reset_password', data={'email': 'test@example.com'}).status_code == 302
        assert len(messages) == 1
    assert client.get('/reset_password/' + token).status_code == 200
    assert client.post('/reset_password/' + token, data=dict(password='newpass', confirm_password='newpass')).status_code == 302
    with app.app_context():
        assert bcrybt.check_password_hash(User.query.first().password, 'newpass')


def test_contact_delivery(client):
    with mail.record_messages() as messages:
        response = client.post('/contact', data=dict(email='test@example.com',
                               report_title='Question', report_message='Hello'))
        assert response.status_code == 302
        assert len(messages) == 1
        assert messages[0].reply_to == 'test@example.com'


def test_login_redirect_is_local(client):
    register_and_login(client)
    client.get('/logout')
    response = client.post('/login?next=https://example.com', data=dict(email='test@example.com', password='password'))
    assert response.location == '/scanner'


def test_scan_upload_is_private(client, monkeypatch):
    from app import views
    monkeypatch.setattr(views, 'model_pred', lambda path: ('Normal', 95.0))
    register_and_login(client)
    image = io.BytesIO()
    Image.new('RGB', (8, 8)).save(image, format='PNG')
    image.seek(0)
    response = client.post('/scanner', data={'imageFile': (image, 'test.png')})
    assert response.status_code == 200
    with client.session_transaction() as session:
        name = session['uploads'][0]
    assert client.get('/uploads/' + name).status_code == 200
    assert client.get('/static/uploads/' + name).status_code == 404
    with app.app_context():
        assert User.query.first().scans[0].prediction == 'Normal'
    client.get('/logout')
    register_response = client.post('/register', data=dict(username='other', email='other@example.com', password='password', confirm_password='password'))
    assert register_response.status_code == 302
    client.post('/login', data=dict(email='other@example.com', password='password'))
    assert client.get('/uploads/' + name).status_code == 404


def test_invalid_upload(client):
    register_and_login(client)
    response = client.post('/scanner', data={'imageFile': (io.BytesIO(b'not an image'), 'bad.png')})
    assert response.status_code == 302
    assert not list(Path(app.config['UPLOAD_FOLDER']).iterdir())


def test_scanner_requires_csrf(client):
    register_and_login(client)
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/scanner').status_code == 400
