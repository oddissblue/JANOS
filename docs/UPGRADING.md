# Upgrading an existing installation

## Preserve the original data

The database and uploads are deliberately excluded from Git. Back up your runtime
directory and record the existing signing/mail configuration before changing the
application. The original local database normally resides at `instance/database.db`.
The earlier cleanup preserved historical uploads in `instance/legacy-uploads/`.

The original scan schema has no filename mapping, so older result rows cannot be
reliably matched to uploaded images. Migration preserves those records but shows
metadata without an image. New scans store explicit owner/filename associations.

## Upgrade the original SQLite schema

Stop the application and copy `instance/database.db` to a separate backup location.
Point `DATABASE_URL` to the database you intend to migrate. An original database has
`user` and `scans` tables but no `alembic_version` table. Only for that exact schema:

```sh
uv sync --locked --extra inference
uv run --extra inference flask --app app db stamp 0001
uv run --extra inference flask --app app db upgrade
uv run --extra inference flask --app app db check
```

`stamp` records the starting revision without changing tables. Do not stamp an empty,
different, or already-versioned database. Fresh databases need only `db upgrade`.
The tested migration keeps original accounts, bcrypt hashes, scan results, and dates,
then expands password storage and adds the nullable image filename and owner index.
Downgrading refuses to truncate modern password hashes.

Existing bcrypt users can sign in with their old passwords; hashes are upgraded on
successful login. Password changes and resets require 12–128 characters. Previously
issued sessions and reset links are invalidated by the new fingerprint format.
Rotate the mail password that was embedded in the original source; the app now reads
all credentials from the environment.

## Move from SQLite to Docker/PostgreSQL

The Docker stack starts a separate PostgreSQL database. It does not silently import
local SQLite data. Keep the backup and test an explicit data export/import process
in a separate environment if existing accounts and scans must be retained. Schema
migrations change a database in place; they do not move data between database engines.
Do not delete the old runtime directory until the new deployment has been verified.

## Update dependencies and model behavior

The runtime moved from TensorFlow/Keras 2.15 and NumPy 1 to TensorFlow 2.21, Keras 3,
and NumPy 2. The original model remains byte-for-byte unchanged and is stored in Git
LFS. The compatibility loader adapts legacy serialization, and regression fixtures
verify all bundled sample outputs against the original runtime.

Use the pinned Python 3.13 environment and `uv.lock`. Do not force transitive package
versions that contradict TensorFlow's declared requirements. When refreshing the
lockfile, run app tests, migration tests, model regression tests, and the full Docker
HTTP/mail smoke test before deploying.
