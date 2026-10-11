# Architecture

## Request and storage flow

The Flask factory creates independent application instances and initializes shared
extension objects. Importing the package does not connect to or modify the database,
load TensorFlow, or create schema tables. Alembic migrations manage the schema.

The `main` blueprint serves HTML pages and handles account and upload requests.
Flask-WTF validates forms and protects all state-changing routes with CSRF tokens.
Flask-Login authenticates sessions; Flask-Limiter uses Redis in Compose to apply
limits to registration, sign-in, password reset, contact, and scanning requests.

An upload is checked for size, filename extension, actual PNG/JPEG content, and image
decompression limits. The app assigns a random filename, stores it outside the
static directory, performs inference, and commits a scan row with its owner. If
inference or persistence fails, the transaction is rolled back and the file removed.
Uploaded-image and scan-result routes query both the record and the authenticated
user ID before serving data. Ownership persists across sign-outs and server restarts.

The frontend uses semantic HTML and a small responsive stylesheet. It has labeled
forms, validation messages, keyboard focus states, a skip link, native FAQ controls,
and horizontally scrollable tables. It loads no external JavaScript dependencies.

## Inference compatibility

`app/inference.py` lazily loads one model per application instance. A lock serializes
model initialization and prediction so threaded requests do not initialize duplicate
models or run concurrent calls. Each Gunicorn worker owns its own model; the default
is one worker with four threads to limit memory use.

The original HDF5 artifact contains a Keras 2 Sequential network with a nested VGG16
Functional model. Keras 3 preserves a one-element output list from the nested model,
which breaks the subsequent Flatten layer. The compatibility loader reconstructs
the saved layers with public Keras APIs, unwraps that single output, normalizes
one-element BatchNormalization axes, and loads all original weights. It does not
edit the HDF5 artifact or download substitute weights. Unsupported legacy layers
fail explicitly. Modern `.keras` files use the standard Keras loader.

Preprocessing intentionally preserves the original contract: RGB input, nearest
resize to 224 × 224, conversion to float32, scaling by 255, and one-image batches.
Inference runs without training behavior. The scalar must be finite and in [0, 1].
Values above 0.5 select pneumonia; other values select normal. The displayed score
is the selected class's model score multiplied by 100.

`tests/fixtures/legacy_predictions.json` records the model and image SHA-256 hashes
and all ten sample scores from TensorFlow 2.15.1/Keras 2.15. The regression test
requires the same class and scores within 0.002 percentage points under the latest
runtime. This verifies software compatibility, not clinical accuracy.

## Authentication and email

New passwords use Werkzeug scrypt. Existing bcrypt hashes are checked using their
original 72-byte truncation behavior and upgraded to scrypt after a successful
sign-in. New passwords must contain 12–128 characters.

Session IDs include a fingerprint of the current password hash. Password changes
invalidate existing login sessions and remember cookies. Reset links expire after
30 minutes and contain that same fingerprint, making them unusable after a reset.
Responses to reset requests do not disclose whether an account exists. Reset URLs
use `PUBLIC_BASE_URL` rather than the untrusted request Host header.

Mail delivery is synchronous. SMTP failures are logged and contact requests show
an error instead of claiming success. The local Docker stack captures messages in
Mailpit. Operators supply an authenticated SMTP provider for actual mail delivery.

## Databases and deployment boundaries

SQLite supports local development and tests; PostgreSQL is used by Compose.
Revision `0001` represents the original tables and revision `0002` expands password
storage and adds persistent private-image ownership. Legacy scans without filenames
remain viewable as metadata.

Redis is internal to the Compose network, as is PostgreSQL. Only the application and
Mailpit UI publish loopback ports. Persistent volumes keep state when containers are
recreated. The web image runs as UID/GID 10001 and drops Linux capabilities.

`/health/live` confirms that Flask can answer. `/health/ready` checks the database,
an application table, model-file presence/signature, and rate-limit storage. It does
not run inference on every probe; the real-model test and HTTP smoke test verify that
separately. Database migrations execute before Gunicorn starts.
