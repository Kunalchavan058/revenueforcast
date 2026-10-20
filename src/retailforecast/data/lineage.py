"""Trusted append-only SQL lineage shared by job eligibility, promotion and fresh forecasts."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from retailforecast.storage.models import DatasetLineage, DatasetVersion

MAX_LINEAGE_DEPTH = 1000


def is_descendant(session: Session, child_id: str, ancestor_id: str) -> bool:
    """Accept only identical snapshots or validated immutable append-only parent chains."""
    seen: set[str] = set()
    current = child_id
    for _ in range(MAX_LINEAGE_DEPTH):
        if current == ancestor_id:
            return True
        if current in seen:
            raise ValueError("Dataset lineage contains a cycle")
        seen.add(current)
        edge = session.get(DatasetLineage, current)
        if edge is None:
            return False
        current = edge.parent_version_id
    raise ValueError("Dataset lineage exceeds the supported traversal bound")


def latest_descendant(session: Session, ancestor_id: str) -> DatasetVersion:
    """Choose fresh validated actuals in the same lineage, never an unrelated newest import."""
    candidates = session.scalars(
        select(DatasetVersion).order_by(
            DatasetVersion.available_through.desc(),
            DatasetVersion.ingested_at.desc(),
            DatasetVersion.id,
        )
    )
    for candidate in candidates:
        if is_descendant(session, candidate.id, ancestor_id):
            return candidate
    raise ValueError("Imported ancestor dataset is missing")
