# Operations

## Start, inspect, and stop

```sh
python scripts/manage.py start
python scripts/manage.py status
python scripts/manage.py logs
python scripts/manage.py stop
```

Use `uv run --no-project --python 3.13` before the script when Python is not installed.
`stop` runs `docker compose down` and preserves named volumes. It does not delete
accounts, images, or mail. `docker compose down --volumes` permanently removes that
state; reserve it for disposable test environments.

To rebuild after changing code or dependencies, rerun `start`. Container versions
are explicit in Compose. Pull updated images intentionally and run the integration
checks after any change. Do not change PostgreSQL major versions against an existing
volume without a tested upgrade plan.

## Backups

```sh
python scripts/manage.py backup --output backups/janos.dump
```

The script creates a PostgreSQL custom-format dump and refuses to overwrite an
existing file. Back up the `janos_uploads` volume separately, and protect `.env` in a
secure secret store. Database-only backups do not contain image files. Redis limits
are transient operational state. Captured Mailpit messages may contain reset links;
protect or discard them according to your retention policy.

Test restoration into a separate environment before relying on a backup. A typical
restore uses `pg_restore -U janos -d janos --clean --if-exists` with the dump streamed
into the database container. This replaces matching database objects; do not run it
against the active database without a reviewed recovery plan.

## Production adaptation

The included stack is a local deployment baseline. Bindings are deliberately limited
to 127.0.0.1. For a public service, use an HTTPS reverse proxy, configure the canonical
`PUBLIC_BASE_URL`, set `COOKIE_SECURE=true`, and configure a real SMTP provider. Keep
Mailpit private or remove it when adapting the stack. Do not expose PostgreSQL or
Redis to the public network.

Proxy identity forwarding is not trusted by default. Rate limits identify the direct
peer IP. If you introduce a proxy, configure trusted proxy handling for the exact
number of proxies and block direct application access; otherwise clients can forge
forwarded IP headers. A proxy shared by many users can cause shared rate limits until
that configuration is implemented.

Provision sufficient RAM for each model-owning worker. The default one worker/four
threads avoids multiplying model memory; predictions within the worker are serialized.
Set `WEB_WORKERS` or `WEB_THREADS` in the container environment only after load testing.
For replicas, apply migrations once as a release step before starting replicas.

Monitor application logs, readiness, database capacity, upload storage, and SMTP
failures. Set retention and access policies appropriate to the data. The app has no
admin dashboard, audit-log system, clinical certification, or automatic upload-expiry
job. These must be designed before a clinical or multi-tenant production deployment.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Docker command missing | Install/start Docker Desktop with Linux containers and Compose v2. |
| Build says run Git LFS | Run `git lfs pull` and confirm the model is about 381 MB, not a pointer file. |
| Compose rejects secrets | Run `scripts/manage.py configure`; edit an existing `.env` if it still contains placeholders. |
| Web remains unhealthy | Inspect `docker compose logs web db redis`. Check migrations, model file, and Redis availability. |
| Scan fails | Inspect web logs, then run `docker compose exec web flask --app app check-model "app/static/sample test images/NORMAL/IM-0001-0001.jpeg"`. |
| Email never arrives | Local mail appears in Mailpit. For external mail, verify server, sender, credentials, and TLS/SSL settings. |
| Login stops after restart | Ensure a stable `SECRET_KEY` is configured across workers and restarts. |
| Old SQLite schema fails on startup | Follow the legacy stamp/upgrade procedure in `UPGRADING.md`. |
| Local reset link uses port 8000 | Change `PUBLIC_BASE_URL` to the actual local origin. |
