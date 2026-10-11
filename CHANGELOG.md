# Changelog

## 0.2.0 — 2026-10-11

- Upgrade to Python 3.13 and current stable compatible dependencies, including
  TensorFlow 2.21, Keras 3, NumPy 2.5, and Pillow 12.
- Adapt the original Keras 2 model configuration without changing its weights;
  preserve predictions across all ten sample images.
- Replace global initialization and deprecated queries with an application factory,
  initialized extensions, SQLAlchemy selects, and Alembic migrations.
- Store uploaded-image ownership in PostgreSQL/SQLite and protect results across
  sessions; handle invalid uploads and inference/storage failures.
- Modernize password hashing, invalidate sessions on password changes, make reset
  links single-use, and add shared request limits through Redis.
- Replace legacy Bootstrap/jQuery assets and placeholder pages with an accessible,
  responsive server-rendered frontend.
- Add a Docker Compose stack, non-root web image, persistent volumes, Mailpit,
  readiness checks, management scripts, and cross-platform/integration CI.
- Document installation, configuration, architecture, operations, backups, upgrades,
  dependency maintenance, contribution checks, and known deployment limits.

## 0.1.0 — 2026-10-11

Initial published project with Git LFS model storage, uv configuration, initial
runtime fixes, and setup documentation.
