# Security

This repository is a research prototype. Keep deployments private until their data,
retention, access, and clinical-use requirements have been reviewed.

Security defects should be reported privately to the repository owner using GitHub
private vulnerability reporting if enabled. Do not post credentials, patient images,
reset tokens, or private data in public issues.

The application protects writes with CSRF tokens, rate-limits sensitive routes, hashes
new passwords with scrypt, verifies upload ownership, and stores images outside static
assets. Password resets expire and invalidate prior sessions. These controls do not
replace HTTPS, secure SMTP configuration, operational monitoring, or storage policy.

`.env` and runtime data are excluded from Git and Docker build contexts. Use stable
random secrets, rotate compromised credentials, and keep database/Redis/mail access
private. The original mail credential must be rotated if it was ever active.

Dependency updates are proposed by Dependabot and require passing regression checks.
Run `uv run --extra inference pip-audit` to check installed packages against the
current advisory database; investigate findings rather than overriding compatibility
constraints without testing.
