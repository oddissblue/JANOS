# JANOS

JANOS is a Flask research application that classifies chest X-ray images as normal
or pneumonia using a pretrained VGG16-based Keras model. It includes registration,
login, account updates, scan history, contact email, and password reset.

This is a research prototype. Predictions and displayed confidence are model outputs,
not a clinical diagnosis or validated probability.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Git LFS](https://git-lfs.com/), then run:

```powershell
git clone https://github.com/oddissblue/JANOS.git
cd JANOS
git lfs pull
uv sync --extra inference
$env:SECRET_KEY = uv run python -c "import secrets; print(secrets.token_hex(32))"
uv run flask --app app run --debug
```

Open http://127.0.0.1:5000 and register an account. Upload a PNG or JPEG of up to
10 MiB. Python 3.11 is pinned in `.python-version`; uv can provision it automatically.
TensorFlow 2.15.1 preserves Keras 2 compatibility with the existing HDF5 model.
Native Windows inference uses CPU; GPU support requires a separate compatible setup.

For web development without inference, use `uv sync` and the same Flask command.
Scanning requires `uv sync --extra inference` and the LFS model file. GitHub stores
the 381 MB model through LFS; a clone without LFS contains only its pointer.

## Configuration

Set environment variables before starting the server. `.env.example` lists the mail
settings; it is an example, and the application does not automatically load it.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Stable random session/reset signing secret; required for persistent sessions and multiple workers. A temporary random key is generated if absent. |
| `DATABASE_URL` | SQLAlchemy connection URL; defaults to SQLite in `instance/database.db`. |
| `MODEL_PATH` | Override the bundled model path. |
| `MAIL_SERVER`, `MAIL_PORT` | SMTP host and port (defaults: smtp.gmail.com, 465). |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | SMTP credentials; use a provider app password where required. |
| `MAIL_USE_SSL`, `MAIL_USE_TLS` | `true`/`false`; defaults to SSL enabled and TLS disabled. Choose one transport mode. |
| `MAIL_DEFAULT_SENDER` | Sender address, falling back to `MAIL_USERNAME`. |
| `CONTACT_EMAIL` | Recipient for contact form submissions. |

SQLite tables and the private upload directory are created on startup. Runtime data,
credentials, environments, and desktop cache files are ignored by Git. Uploaded
images are served only to the logged-in session that uploaded them. The app retains
uploads on disk; operators must establish retention and access policies before use
with real data. Reset tokens expire after 30 minutes. Placeholder admin routes are
not an administrative system. SMTP delivery errors need operational monitoring.

## Development

```powershell
uv sync
uv run pytest
uv run ruff check .
uv lock --check
```

`pyproject.toml` defines direct dependencies and the optional inference extra;
`uv.lock` records resolved versions. `requirements.txt` is generated for pip users:

```powershell
uv export --extra inference --no-dev --no-hashes --output-file requirements.txt
```

The app lives in `app/`, templates and static assets in its subdirectories, and
`run.py` is an alternative local entry point. Tests exercise authentication, password
reset, contact delivery, upload access, and inference plumbing with a fake predictor.
They do not establish model accuracy. Sample X-rays remain in
`app/static/sample test images/`.

Use a production WSGI server and HTTPS for deployment; the Flask development server
is intended for local development. Rotate any credentials from the original local
source before configuring mail. No dataset/model license or clinical validation
documentation is supplied in this repository.
