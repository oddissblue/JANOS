$ErrorActionPreference = 'Stop'
uv run --no-project --python 3.13 "$PSScriptRoot/manage.py" start
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
