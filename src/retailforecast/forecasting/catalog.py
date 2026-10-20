"""Typed historical dataset and store discovery without exposing local source paths."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field
from sqlalchemy import String, cast, func, select

from retailforecast.data.lineage import is_descendant, latest_descendant
from retailforecast.forecasting.contracts import ApiContract
from retailforecast.forecasting.errors import ForecastError
from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.storage.models import DatasetVersion, ModelVersion, Store


class DatasetSummary(ApiContract):
    """An imported historical source; ingestion time is distinct from label freshness."""

    id: str
    source: str
    checksum: str
    version: str
    ingested_at: datetime
    rows: int
    available_through: date
    availability_policy: str


class DatasetStatus(ApiContract):
    """Latest import and the active model's pinned dataset may differ."""

    latest: DatasetSummary | None
    active_model_dataset_version_id: str | None
    source_kind: str = "imported_historical_snapshot"
    notice: str = "Historical imports only; ingestion timestamps do not make source sales current."


class StoreInfo(ApiContract):
    """Source store metadata plus explicit active-model cohort support."""

    store_id: int
    store_type: str | None
    assortment: str | None
    forecast_supported: bool


class StorePage(ApiContract):
    """Stable store-ID ordering with bounded, one-based pagination."""

    dataset_version_id: str | None
    source_available_through: date | None
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int
    items: tuple[StoreInfo, ...]


class CatalogService:
    """Inspect business metadata; never train or reinterpret unlabeled test rows as truth."""

    def __init__(self, registry: ModelRegistry) -> None:
        """Share the registry's explicit database boundary."""
        self.registry = registry
        self.sessions = registry.sessions

    def status(self) -> DatasetStatus:
        """Expose latest ingestion provenance and active dataset identity separately."""
        slot = self.registry.slot()
        with self.sessions() as session:
            latest = session.scalar(
                select(DatasetVersion)
                .order_by(DatasetVersion.ingested_at.desc(), DatasetVersion.id.desc())
                .limit(1)
            )
            version = (
                session.get(ModelVersion, slot.active_model_version_id)
                if slot.active_model_version_id
                else None
            )
            summary = (
                DatasetSummary(
                    **{name: getattr(latest, name) for name in DatasetSummary.model_fields}
                )
                if latest
                else None
            )
            return DatasetStatus(
                latest=summary,
                active_model_dataset_version_id=version.dataset_version_id if version else None,
            )

    def stores(
        self,
        *,
        search: str = "",
        page: int = 1,
        page_size: int = 25,
        dataset_version_id: str | None = None,
    ) -> StorePage:
        """Search numeric source IDs; default to the active model's source, else latest import."""
        if page < 1 or not 1 <= page_size <= 100:
            raise ForecastError("invalid_pagination", "Page must be positive and page_size 1..100")
        slot = self.registry.slot()
        supported: set[int] = set()
        with self.sessions() as session:
            active = (
                session.get(ModelVersion, slot.active_model_version_id)
                if slot.active_model_version_id
                else None
            )
            source_id = dataset_version_id or (active.dataset_version_id if active else None)
            source = (
                session.get(DatasetVersion, source_id)
                if source_id
                else session.scalar(
                    select(DatasetVersion)
                    .order_by(DatasetVersion.ingested_at.desc(), DatasetVersion.id.desc())
                    .limit(1)
                )
            )
            if active and source is not None and dataset_version_id is None:
                source = latest_descendant(session, active.dataset_version_id)
            if source is None and dataset_version_id:
                raise ForecastError(
                    "dataset_not_found", "No imported dataset has this version ID", 404
                )
            if source is None:
                return StorePage(
                    dataset_version_id=None,
                    source_available_through=None,
                    page=page,
                    page_size=page_size,
                    total=0,
                    items=(),
                )
            if active and is_descendant(session, source.id, active.dataset_version_id):
                try:
                    model, _ = self.registry.load(active.id)
                    supported = set(model.metadata.training_span.store_ids)
                except (ValueError, OSError) as error:
                    raise ForecastError(
                        "model_unavailable",
                        "Active model failed validation; inspect its artifacts",
                        503,
                    ) from error
            filters = [Store.source_version == source.id]
            if search.strip():
                filters.append(
                    cast(Store.store_id, String).contains(search.strip(), autoescape=True)
                )
            count = session.scalar(select(func.count()).select_from(Store).where(*filters)) or 0
            rows = session.scalars(
                select(Store)
                .where(*filters)
                .order_by(Store.store_id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return StorePage(
                dataset_version_id=source.id,
                source_available_through=source.available_through,
                page=page,
                page_size=page_size,
                total=count,
                items=tuple(
                    StoreInfo(
                        store_id=row.store_id,
                        store_type=row.store_type,
                        assortment=row.assortment,
                        forecast_supported=row.store_id in supported,
                    )
                    for row in rows
                ),
            )
