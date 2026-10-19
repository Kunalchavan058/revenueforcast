"""Cross-platform commands for the two-service starter and its quality checks."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
POLL_INTERVAL_SECONDS = 0.2
SHUTDOWN_TIMEOUT_SECONDS = 10
TASKS = (
    "api",
    "web",
    "dev",
    "lint",
    "format",
    "format-check",
    "typecheck",
    "test",
    "build",
    "check",
)


def npm_command(*arguments: str) -> list[str]:
    """Resolve npm on either Windows or POSIX, failing with setup guidance."""
    executable = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if executable is None:
        raise RuntimeError("npm is missing. Install Node.js with npm, then retry.")
    return [executable, *arguments]


def api_command() -> list[str]:
    """Start one local API process without reload or infrastructure workers."""
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--app-dir",
        "services/api",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]


def run_checked(command: list[str]) -> None:
    """Print and execute a command, preserving failure as a nonzero exit."""
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def stop_process(process: subprocess.Popen[bytes]) -> None:
    """Stop a managed service and its descendants, including Windows npm children."""
    if sys.platform == "win32":
        # Terminating npm alone can leave Next.js workers holding the port.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    elif process.poll() is None:
        os.killpg(process.pid, 15)
    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            process.kill()
        else:
            os.killpg(process.pid, 9)
        process.wait()


def run_development() -> None:
    """Supervise API/web and stop both on interruption or a service exit."""
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for command in [api_command(), npm_command("run", "dev", "--workspace", "apps/web")]:
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    start_new_session=sys.platform != "win32",
                )
            )
        while all(process.poll() is None for process in processes):
            time.sleep(POLL_INTERVAL_SECONDS)
        raise RuntimeError("A development service exited. Both services have been stopped.")
    finally:
        for process in reversed(processes):
            stop_process(process)


def run_task(task: str) -> None:
    """Dispatch starter tasks; check runs every quality gate without skipping failures."""
    python = sys.executable
    web = ["--workspace", "apps/web"]
    commands: dict[str, list[list[str]]] = {
        "api": [api_command()],
        "web": [npm_command("run", "dev", *web)],
        "lint": [[python, "-m", "ruff", "check", "."], npm_command("run", "lint", *web)],
        "format": [
            [python, "-m", "ruff", "format", "."],
            npm_command("exec", "--", "prettier", "--write", "."),
        ],
        "format-check": [
            [python, "-m", "ruff", "format", "--check", "."],
            npm_command("exec", "--", "prettier", "--check", "."),
        ],
        "typecheck": [[python, "-m", "mypy"], npm_command("run", "typecheck", *web)],
        "test": [[python, "-m", "pytest"], npm_command("run", "test", *web)],
        "build": [npm_command("run", "build", *web)],
    }
    if task == "dev":
        run_development()
    elif task == "check":
        for name in ["lint", "format-check", "typecheck", "test"]:
            run_task(name)
    else:
        for command in commands[task]:
            run_checked(command)


def main() -> int:
    """Load optional local settings and execute one explicit development command."""
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=TASKS)
    arguments = parser.parse_args()
    try:
        run_task(arguments.task)
    except KeyboardInterrupt:
        return 130
    except (subprocess.CalledProcessError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
