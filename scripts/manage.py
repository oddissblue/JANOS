"""Portable Docker management commands; only the Python standard library is needed."""

import argparse
import os
import secrets
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def configure(root: Path = ROOT) -> Path:
    """Create local secrets once, without overwriting an existing environment file."""
    target = root / ".env"
    if target.exists():
        return target
    contents = (root / ".env.example").read_text(encoding="utf-8")
    contents = contents.replace("SECRET_KEY=change-me", f"SECRET_KEY={secrets.token_hex(32)}")
    contents = contents.replace(
        "POSTGRES_PASSWORD=change-me", f"POSTGRES_PASSWORD={secrets.token_hex(24)}"
    )
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(contents)
    if os.name != "nt":
        target.chmod(0o600)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["configure", "start", "stop", "logs", "status", "backup"]
    )
    parser.add_argument("--output", type=Path, help="New PostgreSQL backup path (backup only)")
    args = parser.parse_args()
    if args.command == "configure":
        configure()
        print("Local .env is ready; existing values were preserved.")
        return
    if not shutil.which("docker"):
        parser.error("Docker with Compose v2 is required. Install/start Docker Desktop first.")
    subprocess.run(["docker", "compose", "version"], check=True, cwd=ROOT)
    if args.command == "start":
        configure()
        subprocess.run(
            ["docker", "compose", "up", "--build", "-d", "--wait", "--wait-timeout", "300"],
            check=True,
            cwd=ROOT,
        )
        print(
            "JANOS is running. Default URLs: http://localhost:8000 and http://localhost:8025 (mail)."
        )
    elif args.command == "backup":
        if args.output is None:
            parser.error("backup requires --output PATH")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as output:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "db",
                    "pg_dump",
                    "-U",
                    "janos",
                    "-d",
                    "janos",
                    "-Fc",
                ],
                check=True,
                cwd=ROOT,
                stdout=output,
            )
        print(f"Database backup saved to {args.output}. Uploads must be backed up separately.")
    else:
        commands = {
            "stop": ["down"],
            "logs": ["logs", "--follow", "--tail", "100"],
            "status": ["ps"],
        }
        subprocess.run(["docker", "compose", *commands[args.command]], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
