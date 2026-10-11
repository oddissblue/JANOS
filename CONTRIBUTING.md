# Contributing

Create a branch for your change and follow the local setup in the README. Keep the
application factory independent of mutable database or model state. Use committed
Alembic migrations for schema changes; do not create tables during imports.

Before opening a pull request:

```sh
uv sync --locked --extra inference
uv run --extra inference ruff check .
uv run --extra inference ruff format --check .
uv run --extra inference pytest
uv lock --check
```

For deployment changes, run the full Docker stack and
`python scripts/smoke.py --mail-url http://localhost:8025` in a disposable environment.
The smoke test creates a test user and scan. Do not run it against a live user database.

Change `pyproject.toml` and regenerate `uv.lock` when updating dependencies. Export
`requirements.txt` with the command in the README. Keep examples runnable on both
Windows and Linux, avoid shell-specific setup assumptions, and document operational
limitations. Never commit credentials, runtime databases, uploaded images, or virtual
environments.

If modifying inference, preserve the input/preprocessing contract and verify all
archived sample outputs. Do not regenerate reference fixtures using the same new
implementation being tested. Model accuracy claims need separate documented evidence.
