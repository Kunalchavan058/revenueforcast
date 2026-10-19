"""Typed portable file-pipeline settings and canonical provenance serialization."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "data.yaml"


class Profile(BaseModel):
    """Select a dataset kind and repository-relative raw/output locations."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["synthetic", "rossmann"]
    source_dir: str
    output_dir: str
    fixture: str | None = None

    @field_validator("source_dir", "output_dir", "fixture")
    @classmethod
    def portable_path(cls, value: str | None) -> str | None:
        """Reject absolute/private paths and traversal in shared configuration."""
        if value is not None:
            path = Path(value)
            if (
                path.is_absolute()
                or PurePosixPath(value).is_absolute()
                or PureWindowsPath(value).drive
                or ".." in path.parts
                or "\\" in value
            ):
                raise ValueError("Use a repository-relative path without '..'")
        return value


class ValidationSettings(BaseModel):
    """Pin historical validation bounds and the information-availability assumption."""

    model_config = ConfigDict(extra="forbid")
    minimum_date: date
    maximum_date: date
    availability_policy: str = Field(min_length=1)


class ProcessingSettings(BaseModel):
    """Bound Parquet row-group memory with explicit deterministic writer settings."""

    model_config = ConfigDict(extra="forbid")
    batch_rows: int = Field(ge=1, le=50000)
    compression: Literal["zstd"]
    compression_level: int = Field(ge=1, le=9)


class DataConfig(BaseModel):
    """The sole preprocessing configuration, used by DVC and Python commands."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    profiles: dict[str, Profile]
    validation: ValidationSettings
    processing: ProcessingSettings

    @model_validator(mode="after")
    def distinct_datasets(self) -> DataConfig:
        """Keep synthetic and real raw/output directories physically separate."""
        sources = [profile.source_dir for profile in self.profiles.values()]
        outputs = [profile.output_dir for profile in self.profiles.values()]
        if len(sources) != len(set(sources)) or len(outputs) != len(set(outputs)):
            raise ValueError("Dataset profiles must have distinct source/output directories")
        return self


def canonical_json(value: object) -> bytes:
    """Encode stable JSON with no wall-clock time, local paths, or unordered keys."""
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def content_hash(value: object) -> str:
    """Fingerprint a portable JSON value rather than its machine-local location."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def text_hash(path: Path) -> str:
    """Hash code/locks with normalized newlines across Windows and POSIX checkouts."""
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").encode()).hexdigest()


def load_config(path: Path) -> DataConfig:
    """Validate YAML without executing constructors or accepting unknown settings."""
    return DataConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def rooted_path(root: Path, relative: str) -> Path:
    """Resolve a configured path inside the project, including symlink containment."""
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("Configured path must stay inside the project")
    return candidate


def profile_paths(config_path: Path, profile_name: str) -> tuple[DataConfig, Profile, Path, Path]:
    """Return validated settings plus distinct owned raw and processed directories."""
    config = load_config(config_path)
    profile = config.profiles[profile_name]
    root = config_path.resolve().parent.parent
    source = rooted_path(root, profile.source_dir)
    output = rooted_path(root, profile.output_dir)
    if not source.is_relative_to(root / "data" / "raw") or source == root / "data" / "raw":
        raise ValueError("Source directory must be under data/raw")
    if (
        not output.is_relative_to(root / "data" / "processed")
        or output == root / "data" / "processed"
    ):
        raise ValueError("Output directory must be under data/processed")
    return config, profile, source, output
