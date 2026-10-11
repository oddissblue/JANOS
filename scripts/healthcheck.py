"""Readiness probe usable by Docker without installing curl."""

import sys
from urllib.error import URLError
from urllib.request import urlopen

if __name__ == "__main__":
    try:
        with urlopen("http://127.0.0.1:8000/health/ready", timeout=4) as response:
            sys.exit(0 if response.status == 200 else 1)
    except (URLError, TimeoutError):
        sys.exit(1)
