"""Generate only hand-authored synthetic CSVs; never fetch or disguise real records."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from retailforecast.data.pipeline_config import profile_paths, rooted_path
from retailforecast.data.validation import SOURCE_MODELS


class FixtureFile(BaseModel):
    """A source-shaped header and string rows stored in a small Git-safe JSON fixture."""

    model_config = ConfigDict(extra="forbid")
    columns: list[str]
    rows: list[list[str]]


class SyntheticFixture(BaseModel):
    """Require an explicit synthetic label and exactly the supported four CSV names."""

    model_config = ConfigDict(extra="forbid")
    synthetic_only: Literal[True]
    description: str
    files: dict[str, FixtureFile]


def generate_synthetic(config_path: Path, profile_name: str) -> None:
    """Write deterministic LF CSV bytes without touching the real Rossmann profile."""
    _, profile, source, _ = profile_paths(config_path, profile_name)
    if profile.kind != "synthetic" or profile.fixture is None:
        raise ValueError("Synthetic generation requires a synthetic profile and fixture")
    root = config_path.resolve().parent.parent
    fixture_path = rooted_path(root, profile.fixture)
    fixture = SyntheticFixture.model_validate(json.loads(fixture_path.read_text(encoding="utf-8")))
    if set(fixture.files) != set(SOURCE_MODELS):
        raise ValueError("Synthetic fixture must define the exact four Rossmann-shaped files")
    source.mkdir(parents=True, exist_ok=True)
    for filename, definition in fixture.files.items():
        destination = source / filename
        with destination.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(definition.columns)
            writer.writerows(definition.rows)
