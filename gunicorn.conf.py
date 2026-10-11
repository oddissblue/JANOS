"""One model-owning worker with bounded request concurrency."""

import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_WORKERS", "1"))
threads = int(os.environ.get("WEB_THREADS", "4"))
timeout = 180
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
# Each worker loads its own ~381 MB model; increase only after measuring memory.
worker_class = "gthread"
