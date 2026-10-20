"""Typed local model-inspection and checked lifecycle endpoints; no training side effects."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from retailforecast.lifecycle.registry import ModelRegistry, SlotView, VersionView
from retailforecast.storage.database import ROOT, database_engine

router = APIRouter(prefix="/api/v1/models", tags=["models"])


def model_registry() -> ModelRegistry:
    """Resolve lazy infrastructure only when a model endpoint is called."""
    return ModelRegistry(database_engine(), ROOT / "artifacts/registry", ROOT / "artifacts/mlflow")


RegistryDependency = Annotated[ModelRegistry, Depends(model_registry)]


class ActivationRequest(BaseModel):
    """Require a generation token and an explicit reason to override missing metric evidence."""

    model_config = ConfigDict(extra="forbid")
    expected_generation: int = Field(ge=0)
    approval_reason: str | None = Field(default=None, min_length=1, max_length=1000)


@router.get("/versions", response_model=list[VersionView])
@router.get("", response_model=list[VersionView])
def list_models(registry: RegistryDependency) -> list[VersionView]:
    """List versions, lineage and actual decision evidence; never infer readiness from health."""
    return registry.list_versions()


@router.get("/active", response_model=SlotView)
def active_slot(registry: RegistryDependency) -> SlotView:
    """Expose the authoritative pointer and its current compare-and-swap generation."""
    return registry.slot()


@router.get("/{version_id}", response_model=VersionView)
def inspect_model(version_id: str, registry: RegistryDependency) -> VersionView:
    """Inspect historical metrics and last comparison without loading untrusted model bytes."""
    versions = [version for version in registry.list_versions() if version.id == version_id]
    if not versions:
        raise HTTPException(status_code=404, detail="Unknown model version")
    return versions[0]


def transition(
    registry: ModelRegistry, version_id: str, request: ActivationRequest, *, rollback: bool
) -> SlotView:
    """Share local API error handling and the same domain gates as the CLI."""
    try:
        return registry.activate(
            version_id,
            expected_generation=request.expected_generation,
            approval_reason=request.approval_reason,
            rollback=rollback,
            data_config=ROOT / "configs/data.yaml",
            profile="rossmann",
        )
    except (ValueError, FileNotFoundError) as error:
        # Native/file error messages can contain local paths; expose an actionable
        # category while preserving details for CLI diagnostics.
        if "Stale generation" in str(error):
            raise HTTPException(
                status_code=409, detail="Stale generation; refresh the active slot"
            ) from error
        raise HTTPException(
            status_code=422,
            detail="Model transition failed validation; inspect the model and CLI diagnostics",
        ) from error


@router.post("/{version_id}/activate", response_model=SlotView)
def activate_model(
    version_id: str, request: ActivationRequest, registry: RegistryDependency
) -> SlotView:
    """Activate only after artifact and shared-window checks; pending evidence retains incumbent."""
    return transition(registry, version_id, request, rollback=False)


@router.post("/{version_id}/rollback", response_model=SlotView)
def rollback_model(
    version_id: str, request: ActivationRequest, registry: RegistryDependency
) -> SlotView:
    """Restore a retained compatible archived version, requiring a reason and generation."""
    return transition(registry, version_id, request, rollback=True)
