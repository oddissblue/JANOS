# JANOS

[![CI](https://github.com/oddissblue/JANOS/actions/workflows/ci.yml/badge.svg)](https://github.com/oddissblue/JANOS/actions/workflows/ci.yml)

A chest X-ray classification research application built with Flask, Keras, and
PostgreSQL. Users can create an account, upload an image, and review private scan
results. The frontend is rendered by Flask using accessible HTML and responsive
CSS; it does not require a separate JavaScript server or build tool.

**Research use only.** The pretrained model classifies images as normal or
pneumonia. Its score is not a clinical diagnosis or calibrated disease probability.
No clinical validation or model/dataset license is supplied with this repository.

## Run the complete stack

Install [Docker Desktop](https://docs.docker.com/desktop/) with Linux containers,
[uv](https://docs.astral.sh/uv/getting-started/installation/), and
[Git LFS](https://git-lfs.com/). Allow at least 4 GB of memory and several GB of
free disk space for the TensorFlow image and model.

```sh
git clone https://github.com/oddissblue/JANOS.git
cd JANOS
git lfs pull
uv run --no-project --python 3.13 scripts/manage.py start
```

The start command generates random local secrets in `.env` if the file does not
exist, builds the image, applies database migrations, and waits for healthy services.
It preserves existing configuration and data. Subsequent starts use the same command.

| Service | Purpose | Local access |
| --- | --- | --- |
| Web | Flask frontend/backend and Keras CPU inference | http://localhost:8000 |
| PostgreSQL 18.6 | Users, scan metadata, migration history | Internal network only |
| Redis 8.6.6 | Shared request rate limits | Internal network only |
| Mailpit 1.31.4 | Local SMTP inbox for reset/contact messages | http://localhost:8025 |

Create an account and upload a PNG or JPEG chest X-ray up to 10 MiB. Mailpit captures
messages locally; it does **not** deliver them to real inboxes. Named Docker volumes
retain database records, images, Redis data, and captured mail across restarts.

If Python 3.13 is already installed, `python scripts/manage.py start` works without
uv. After configuring `.env`, the equivalent Compose command is:

```sh
python scripts/manage.py configure
docker compose up --build -d --wait --wait-timeout 300
```

The first image build downloads substantial TensorFlow dependencies. A missing LFS
model causes an explicit build error. Run `git lfs pull` before retrying.

## Local development

```sh
uv sync --locked --extra inference
uv run --extra inference flask --app app db upgrade
uv run --extra inference flask --app app run --debug
```

Open http://127.0.0.1:5000. Run `scripts/manage.py configure` to generate `.env`
before editing it, or set environment variables.
For development on port 5000, set `PUBLIC_BASE_URL=http://localhost:5000` and
`MAIL_SERVER=localhost` when connecting to a local SMTP service. The factory loads
`.env` without replacing already-set environment variables. SQLite is the default
outside Docker. Migrations must run before account workflows.

Use `uv sync --locked` for web-only development; real scanning requires the inference
extra and the model. Keep `--extra inference` on `uv run` when testing inference,
because uv otherwise syncs away optional dependencies.

Native Windows uses CPU inference. Python 3.13 is the newest minor supported by
this TensorFlow release. Use Linux/WSL2 and a separately configured CUDA environment
for GPU experiments; the supplied Docker stack runs on CPU.

**Existing installations:** back up your database and follow
[the upgrade guide](docs/UPGRADING.md) before migrating the original SQLite schema.
Do not run a fresh initial migration over an unversioned existing database.

## Configuration

`scripts/manage.py configure` creates `.env` once using cryptographically random,
URL-safe secrets. It never overwrites an existing `.env`. Configure secrets before
setting `JANOS_PRODUCTION=true`; production startup rejects a missing signing key.

| Variable | Default / purpose |
| --- | --- |
| `SECRET_KEY` | Session/reset signing secret. Required in production; temporary in development if absent. |
| `POSTGRES_PASSWORD` | Required by Compose; generated during configuration. |
| `DATABASE_URL` | SQLAlchemy URL. Local default: `sqlite:///database.db`; Compose uses `postgresql+psycopg://…`. |
| `REDIS_URL` | Rate-limit storage. Local default: `memory://`; Compose uses its Redis service. |
| `JANOS_DATA_DIR` | Runtime directory. Local: `instance/`; Docker: `/var/lib/janos`. |
| `MODEL_PATH` | Bundled `app/janos-vgg16-model.h5`, or an operator-provided compatible model. |
| `PUBLIC_BASE_URL` | Canonical URL used in reset emails; default `http://localhost:8000`. Change when overriding the port or deploying. |
| `COOKIE_SECURE` | `false` locally; set `true` when using HTTPS. |
| `MAIL_SERVER`, `MAIL_PORT` | Compose defaults: `mailpit`, `1025`. Configure your SMTP provider for real delivery. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | Optional SMTP credentials. |
| `MAIL_USE_TLS`, `MAIL_USE_SSL` | Both `false` for Mailpit. Enable exactly one if your provider requires it. |
| `MAIL_DEFAULT_SENDER` | Sender address; default `janos@localhost`. |
| `CONTACT_EMAIL` | Contact-message recipient; default `contact@localhost`. |
| `WEB_PORT`, `MAIL_UI_PORT` | Compose host ports: `8000`, `8025`. Both bind only to loopback. |

For real SMTP, set an authorized sender, recipient, provider credentials and transport.
Do not publish `.env`. Avoid identifiable patient data. Uploads persist until the
operator removes them; establish a retention policy before accepting real data.

## Checks and dependency updates

```sh
uv sync --locked --extra inference
uv run --extra inference pytest --cov=app --cov-report=term-missing
uv run --extra inference ruff check .
uv run --extra inference ruff format --check .
uv lock --check
uv run --extra inference flask --app app check-model "app/static/sample test images/NORMAL/IM-0001-0001.jpeg"
```

CI runs checks on Windows and Linux, compares the real model against all ten archived
Keras 2 sample predictions, and starts the complete Docker stack for HTTP/mail tests.
The [Actions page](https://github.com/oddissblue/JANOS/actions) is the source of truth
for the latest CI results. A local Docker daemon is required for container verification.

Direct dependencies were refreshed against stable releases on 2026-10-11:
TensorFlow 2.21.0, Keras 3.15.1, NumPy 2.5.4, Pillow 12.3.0, Flask 3.1.3, and
SQLAlchemy 2.1.4. `uv.lock` records the complete compatible resolution. Upstream
constraints still apply: TensorFlow 2.21 requires h5py below 3.15, so the lock uses
3.14 rather than overriding the requirement to install 3.16.

```sh
uv lock --upgrade
uv sync --locked --extra inference
uv run --extra inference pytest
uv export --frozen --extra inference --no-dev --no-hashes --output-file requirements.txt
```

`requirements.txt` is an export for pip consumers, not a separately maintained source.
Dependabot proposes weekly updates to uv dependencies, container images, and Actions.
Review and test updates; they are not automatically merged.

## Project layout

```text
app/                 Factory, extensions, models, routes, forms, inference
  templates/         Server-rendered frontend
  static/            CSS, image assets, sample X-rays
migrations/          Alembic schema revisions
scripts/             Docker management, health checks, HTTP smoke test
tests/               App/migration tests and model regression fixtures
docs/                Architecture, operations, upgrade instructions
compose.yaml         Web + PostgreSQL + Redis + Mailpit
Dockerfile           Non-root Python/uv application image
pyproject.toml       Dependency and tooling declarations
uv.lock              Reproducible resolved dependencies
```

See [architecture](docs/ARCHITECTURE.md), [operations](docs/OPERATIONS.md),
[upgrade instructions](docs/UPGRADING.md), and [contributing](CONTRIBUTING.md).
