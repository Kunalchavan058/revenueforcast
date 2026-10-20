"""Read-only forecasting form context, pinned to the active model's compatible source."""

from sqlalchemy import func, select

from retailforecast.data.lineage import latest_descendant
from retailforecast.forecasting.contracts import ForecastModel, ForecastResponse
from retailforecast.forecasting.errors import ForecastError
from retailforecast.forecasting.totals import forecast_totals
from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.reporting.contracts import ForecastOptions, ForecastView, StoreCoverage
from retailforecast.reporting.history import source_coverage
from retailforecast.storage.models import DailySale, DatasetVersion, ModelVersion


def forecast_options(registry: ModelRegistry) -> ForecastOptions:
    """Verify saved serving context without fitting, registering or creating a forecast."""
    slot = registry.slot()
    if slot.active_model_version_id is None:
        return ForecastOptions(model=None, coverage=None)
    try:
        model, record = registry.load(slot.active_model_version_id)
    except (ValueError, OSError) as error:
        raise ForecastError(
            "model_unavailable", "The saved model could not be validated; inspect Model Studio", 503
        ) from error
    with registry.sessions() as session:
        version = session.get(ModelVersion, slot.active_model_version_id)
        assert version is not None
        source = session.get(DatasetVersion, version.dataset_version_id)
        if source is None or source.checksum != (
            record.business_source_checksum or record.ingestion_dataset_checksum
        ):
            raise ForecastError(
                "dataset_incompatible", "Active model and source provenance do not match", 409
            )
        source = latest_descendant(session, source.id)
        rows = session.execute(
            select(DailySale.store_id, func.min(DailySale.date), func.max(DailySale.date))
            .where(
                DailySale.source_version == source.id,
                DailySale.store_id.in_(model.metadata.training_span.store_ids),
            )
            .group_by(DailySale.store_id)
            .order_by(DailySale.store_id)
        )
        stores = tuple(
            StoreCoverage(store_id=row[0], observed_from=row[1], observed_through=row[2])
            for row in rows
        )
        return ForecastOptions(
            model=ForecastModel(
                version_id=version.id,
                algorithm=version.algorithm,
                generation=slot.generation,
                trained_until=model.trained_until,
                feature_schema_fingerprint=version.feature_schema_fingerprint,
            ),
            coverage=source_coverage(session, source),
            stores=stores,
            sales_delay_days=record.protocol.config.assumptions.sales_delay_days,
        )


def forecast_view(response: ForecastResponse, store_id: int | None = None) -> ForecastView:
    """Reuse server exact-decimal aggregation for a selected store; never re-predict."""
    if store_id is not None and store_id not in response.request.store_ids:
        raise ForecastError("unknown_store", "This store is not part of the saved forecast")
    points = tuple(row for row in response.points if store_id is None or row.store_id == store_id)
    history = tuple(
        row for row in response.data.history if store_id is None or row.store_id == store_id
    )
    return ForecastView(
        forecast_id=response.forecast_id,
        store_ids=tuple(row.store_id for row in history),
        points=points,
        totals=forecast_totals(points),
        actual_data_cutoff=max(row.observed_through for row in history),
        history=history,
    )
