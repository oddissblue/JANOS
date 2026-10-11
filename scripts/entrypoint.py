"""Apply committed migrations, then replace this process with the web server."""

import os
import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "flask", "--app", "app", "db", "upgrade"], check=True)
    if len(sys.argv) < 2:
        raise SystemExit("A server command is required.")
    os.execvp(sys.argv[1], sys.argv[1:])
