#!/bin/sh
set -eu
exec uv run --no-project --python 3.13 "$(dirname "$0")/manage.py" start
