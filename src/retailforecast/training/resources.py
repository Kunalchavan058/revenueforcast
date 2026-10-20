"""Cross-platform one-job locking and process-tree memory/time supervision."""

from __future__ import annotations

import os
import subprocess
import time
import warnings
from pathlib import Path

import psutil
from filelock import FileLock, Timeout

from retailforecast.training.contracts import ResourceSettings

MEGABYTE = 1024 * 1024


class ResourceLimitError(RuntimeError):
    """A supervised job exceeded its declared memory or elapsed-time budget."""


def training_lock(path: Path) -> FileLock:
    """Acquire the single laptop training slot without waiting or starting another job."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(path, timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise RuntimeError("Another training job holds the single laptop training slot") from exc
    return lock


def terminate_job(process: subprocess.Popen[bytes]) -> None:
    """Stop only this owned worker and its descendants, preserving all other services."""
    try:
        root = psutil.Process(process.pid)
        children = root.children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        root.kill()
    except psutil.NoSuchProcess:
        pass
    process.wait(timeout=15)


def supervise(
    process: subprocess.Popen[bytes], settings: ResourceSettings, seconds: float
) -> dict[str, float]:
    """Enforce hard limits across Python and native fitting, not just between trials.

    Memory is sampled aggregate RSS of coordinator/worker/descendants; shared
    pages can be counted twice. This conservative budget is not a Windows Job
    Object or cgroup guarantee, and very short allocation spikes may be missed.
    """
    started = time.monotonic()
    peak = 0.0
    warned = False
    try:
        while process.poll() is None:
            try:
                members = [psutil.Process(os.getpid()), psutil.Process(process.pid)]
                members.extend(members[-1].children(recursive=True))
            except psutil.NoSuchProcess:
                if process.poll() is not None:
                    break
                continue
            memory = 0.0
            for member in members:
                try:
                    memory += member.memory_info().rss / MEGABYTE
                except psutil.NoSuchProcess:
                    pass
            peak = max(peak, memory)
            elapsed = time.monotonic() - started
            if memory >= settings.warning_memory_mb and not warned:
                warnings.warn(
                    f"Training RSS {memory:.0f} MB exceeds warning threshold",
                    RuntimeWarning,
                    stacklevel=2,
                )
                warned = True
            if memory > settings.max_memory_mb:
                raise ResourceLimitError("Training exceeded the process-tree memory budget")
            if psutil.virtual_memory().available / MEGABYTE < settings.min_available_memory_mb:
                raise ResourceLimitError(
                    "System available memory is below the configured safety floor"
                )
            if elapsed > seconds:
                raise ResourceLimitError("Training exceeded the elapsed-time budget")
            time.sleep(settings.poll_seconds)
        if process.returncode != 0:
            raise RuntimeError(
                f"Training worker exited with code {process.returncode}; inspect worker.log"
            )
    except BaseException:
        if process.poll() is None:
            terminate_job(process)
        raise
    return {
        "duration_seconds": time.monotonic() - started,
        "peak_rss_mb": peak,
        "memory_warning_emitted": float(warned),
    }
