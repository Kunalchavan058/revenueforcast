"""Initialize DVC with a private, out-of-repository local filesystem remote."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dvc(*arguments: str) -> None:
    """Run the locked environment's DVC without echoing private remote paths."""
    subprocess.run([sys.executable, "-m", "dvc", *arguments], cwd=ROOT, check=True)


def main() -> None:
    """Create only local storage; absolute location is saved in ignored config.local."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", type=Path, default=ROOT.parent / ".dvc-remotes" / ROOT.name)
    args = parser.parse_args()
    remote = args.remote.resolve()
    if remote.is_relative_to(ROOT):
        raise ValueError("The local DVC remote must be outside the repository")
    remote.mkdir(parents=True, exist_ok=True)
    if not (ROOT / ".dvc").exists():
        dvc("init")
    dvc("config", "cache.type", "copy")
    dvc("config", "core.analytics", "false")
    dvc("config", "core.autostage", "false")
    dvc("remote", "add", "--local", "--default", "--force", "laptop", str(remote))
    print("DVC is ready. The laptop remote is outside the repository; its path is private.")


if __name__ == "__main__":
    main()
