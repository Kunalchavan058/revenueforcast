"""Predict with a pinned saved model, then persist complete forecasts atomically."""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from threading import BoundedSemaphore

from pydantic import ValidationError
from sqlalchemy import select

from retailforecast.data.pipeline_config import content_hash
from retailforecast.features.contracts import ForecastKey
from retailforecast.forecasting.contracts import (
    ForecastContext,
    ForecastData,
    ForecastDay,
    ForecastModel,
    ForecastRequest,
    ForecastResponse,
    OutputPolicy,
)
from retailforecast.forecasting.errors import ForecastError
from retailforecast.forecasting.policy import apply_output_policy
from retailforecast.forecasting.snapshot import ForecastInputs, load_sql_inputs
from retailforecast.forecasting.totals import forecast_totals
from retailforecast.lifecycle.registry import ModelRegistry, TrainingRecord, schema_fingerprint
from retailforecast.storage.database import new_id, utc_now
from retailforecast.storage.models import (
    DatasetVersion,
    ForecastPoint,
    ForecastRun,
    ModelVersion,
    Store,
)
from retailforecast.training.adapters import TreeModel

FORECAST_CONCURRENCY = 1
SALES_QUANTUM = Decimal("0.0001")
MAX_POINT_SALES = Decimal("99999999999999.9999")


def predict_days(
    model: TreeModel, request: ForecastRequest, inputs: ForecastInputs, context: ForecastContext
) -> tuple[tuple[ForecastDay, ...], bool]:
    """Predict direct horizons with frozen history, saved encoding and evaluated adjustments."""
    points: list[ForecastDay] = []
    unknown_category_used = False
    for horizon in range(1, request.horizon_days + 1):
        for store_id in request.store_ids:
            features = inputs.builder.build(
                ForecastKey(
                    store_id=store_id,
                    cutoff_date=request.cutoff_date,
                    horizon_days=horizon,
                )
            )
            unknown_category_used |= any(
                features.values[name] is not None and features.values[name] not in vocabulary
                for name, vocabulary in model.preprocessing.categories.items()
            )
            flag = features.values["target_open"]
            known_open = None if flag is None else bool(flag)
            adjustment = apply_output_policy(
                model.predict(features), known_open, context.policy.closure_policy
            )
            if adjustment.predicted_sales is None:
                raise ForecastError(
                    "unsupported_history", "Saved model cannot predict this history", 409
                )
            raw_amount = Decimal(str(adjustment.predicted_sales))
            if raw_amount > MAX_POINT_SALES:
                raise ForecastError(
                    "prediction_out_of_range", "Prediction exceeds the supported storage range", 409
                )
            amount = raw_amount.quantize(SALES_QUANTUM, rounding=ROUND_HALF_EVEN)
            points.append(
                ForecastDay(
                    store_id=store_id,
                    target_date=features.key.target_date,
                    horizon=horizon,
                    predicted_sales=amount,
                    known_open=known_open,
                    nonnegative_clamped=adjustment.nonnegative_clamped,
                    closure_adjusted=adjustment.closure_adjusted,
                )
            )
    return tuple(points), unknown_category_used


class ForecastService:
    """A bounded host-side prediction service; no path calls fit, training or model registration."""

    def __init__(self, registry: ModelRegistry) -> None:
        """Reuse infrastructure, not mutable weights; each request verifies and pins one bundle."""
        self.registry = registry
        self.sessions = registry.sessions
        self._prediction_slots = BoundedSemaphore(FORECAST_CONCURRENCY)

    def create(self, request: ForecastRequest) -> ForecastResponse:
        """Save a forecast or an actionable error; an existing model is mandatory."""
        if not self._prediction_slots.acquire(blocking=False):
            raise ForecastError(
                "forecast_busy", "A forecast is running; retry after it completes", 503
            )
        try:
            return self._create(request)
        finally:
            self._prediction_slots.release()

    def _create(self, request: ForecastRequest) -> ForecastResponse:
        slot = self.registry.slot()
        if slot.active_model_version_id is None:
            raise ForecastError(
                "no_active_model", "Activate a validated model before requesting forecasts", 503
            )
        version_id = slot.active_model_version_id
        try:
            # Pin the version before loading. It remains loadable if a concurrent
            # activation archives it, and every point keeps this exact identity.
            model, record = self.registry.load(version_id)
        except (ValueError, OSError) as error:
            raise ForecastError(
                "model_unavailable",
                "Active model artifacts or feature schema failed validation; inspect the model",
                503,
            ) from error
        if model.trained_until > request.cutoff_date:
            raise ForecastError(
                "model_trained_after_cutoff",
                (
                    "The active model was trained after this cutoff; "
                    "select a compatible earlier version"
                ),
                409,
            )
        with self.sessions() as session:
            version = session.get(ModelVersion, version_id)
            assert version is not None
            source = session.get(DatasetVersion, version.dataset_version_id)
            if source is None or source.checksum != record.ingestion_dataset_checksum:
                raise ForecastError(
                    "dataset_incompatible", "Model and imported dataset lineage do not match", 409
                )
            latest_knowledge_date = source.available_through + timedelta(
                days=record.protocol.config.assumptions.sales_delay_days
            )
            if request.cutoff_date > latest_knowledge_date:
                raise ForecastError(
                    "cutoff_beyond_observed_data",
                    (
                        "Choose a historical cutoff no later than "
                        f"{latest_knowledge_date.isoformat()}; "
                        "this is not a live sales feed"
                    ),
                )
            existing = set(
                session.scalars(
                    select(Store.store_id).where(
                        Store.source_version == source.id, Store.store_id.in_(request.store_ids)
                    )
                )
            )
            missing = sorted(set(request.store_ids) - existing)
            if missing:
                raise ForecastError(
                    "unknown_store", f"Unknown store IDs in this dataset: {missing}"
                )
            unsupported = sorted(
                set(request.store_ids) - set(model.metadata.training_span.store_ids)
            )
            if unsupported:
                raise ForecastError(
                    "unsupported_store",
                    (
                        f"Model does not cover store IDs {unsupported}; "
                        f"supported IDs: {list(model.metadata.training_span.store_ids)}"
                    ),
                )
            try:
                inputs = load_sql_inputs(session, source.id, request, record.protocol.snapshot)
            except ValidationError as error:
                raise ForecastError(
                    "invalid_history",
                    "Imported historical records do not satisfy the feature contract",
                    409,
                ) from error
            context = self._context(
                request, version_id, slot.generation, source, model, record, inputs
            )
        try:
            points, unknown_category_used = predict_days(model, request, inputs, context)
        except ValueError as error:
            raise ForecastError(
                "feature_schema_incompatible",
                (
                    "Saved preprocessing or input features are incompatible; "
                    "inspect the active model"
                ),
                409,
            ) from error
        warnings = list(context.warnings)
        if unknown_category_used:
            warnings.append(
                "Some categorical inputs were unseen during training; "
                "the saved unknown-category encoding was used."
            )
        if any(point.nonnegative_clamped for point in points):
            warnings.append(
                "Negative raw predictions were clipped at zero under the evaluated model policy."
            )
        context = context.model_copy(update={"warnings": tuple(warnings)})
        return self._persist(context, points)

    def _context(
        self,
        request: ForecastRequest,
        version_id: str,
        generation: int,
        source: DatasetVersion,
        model: TreeModel,
        record: TrainingRecord,
        inputs: ForecastInputs,
    ) -> ForecastContext:
        warnings = [
            f"Imported historical snapshot; latest source actual date is "
            f"{source.available_through.isoformat()}. This is not a live sales feed."
        ]
        if record.protocol.config.assumptions.calendar_known_as_of is None:
            warnings.append(
                "Future opening, promotion and holiday flags are unknown unless "
                "explicitly supplied as known scenario plans."
            )
        if request.scenarios:
            warnings.append(
                "Scenarios are user-asserted known plans, not verified actuals "
                "or causal promotion-uplift estimates."
            )
        if any(row.missing_days_in_last_28 for row in inputs.history):
            warnings.append(
                "Some recent calendar dates have no available observation; "
                "saved missing-value preprocessing is used, never fabricated zero sales."
            )
        return ForecastContext(
            request=request,
            input_fingerprint=content_hash(
                {"inputs": inputs.input_fingerprint, "model_version_id": version_id}
            ),
            model=ForecastModel(
                version_id=version_id,
                algorithm=model.metadata.algorithm,
                generation=generation,
                trained_until=model.trained_until,
                feature_schema_fingerprint=schema_fingerprint(model),
            ),
            data=ForecastData(
                dataset_version_id=source.id,
                dataset_fingerprint=record.protocol.snapshot.dataset_fingerprint,
                source_checksum=source.checksum,
                source=source.source,
                source_available_through=source.available_through,
                actual_data_cutoff=max(row.observed_through for row in inputs.history),
                history=inputs.history,
                assumptions=record.protocol.config.assumptions,
            ),
            policy=OutputPolicy(closure_policy=record.protocol.config.closure_policy),
            warnings=tuple(warnings),
        )

    def _persist(
        self, context: ForecastContext, points: tuple[ForecastDay, ...]
    ) -> ForecastResponse:
        forecast_id, generated_at = new_id(), utc_now()
        response = ForecastResponse(
            **context.model_dump(),
            forecast_id=forecast_id,
            generated_at=generated_at,
            points=points,
            totals=forecast_totals(points),
        )
        # Metadata and all points commit together. A failed point insert cannot
        # leave a successful-looking partial report or change the active model.
        with self.sessions.begin() as session:
            session.add(
                ForecastRun(
                    id=forecast_id,
                    source_version=context.data.dataset_version_id,
                    model_version_id=context.model.version_id,
                    cutoff_date=context.request.cutoff_date,
                    created_at=generated_at,
                    request_context=context.model_dump(mode="json"),
                )
            )
            session.flush()
            session.add_all(
                [
                    ForecastPoint(
                        run_id=forecast_id,
                        source_version=context.data.dataset_version_id,
                        store_id=point.store_id,
                        target_date=point.target_date,
                        horizon=point.horizon,
                        predicted_sales=point.predicted_sales,
                        known_open=point.known_open,
                        nonnegative_clamped=point.nonnegative_clamped,
                        closure_adjusted=point.closure_adjusted,
                    )
                    for point in points
                ]
            )
        return response

    def get(self, forecast_id: str) -> ForecastResponse:
        """Read persisted results without loading a model, predicting again or needing MLflow."""
        with self.sessions() as session:
            run = session.get(ForecastRun, forecast_id)
            if run is None:
                raise ForecastError("forecast_not_found", "No saved forecast has this ID", 404)
            try:
                context = ForecastContext.model_validate(run.request_context)
            except ValidationError as error:
                raise ForecastError(
                    "stored_forecast_incompatible",
                    "Saved forecast metadata require a schema migration",
                    409,
                ) from error
            rows = session.scalars(
                select(ForecastPoint)
                .where(ForecastPoint.run_id == forecast_id)
                .order_by(ForecastPoint.target_date, ForecastPoint.store_id)
            )
            points = tuple(
                ForecastDay(
                    store_id=row.store_id,
                    target_date=row.target_date,
                    horizon=row.horizon,
                    predicted_sales=row.predicted_sales,
                    known_open=row.known_open,
                    nonnegative_clamped=row.nonnegative_clamped,
                    closure_adjusted=row.closure_adjusted,
                )
                for row in rows
            )
            expected_keys = {
                (store_id, context.request.cutoff_date + timedelta(days=h), h)
                for store_id in context.request.store_ids
                for h in range(1, context.request.horizon_days + 1)
            }
            if {(p.store_id, p.target_date, p.horizon) for p in points} != expected_keys:
                raise ForecastError(
                    "stored_forecast_incomplete", "Saved forecast has incomplete daily values", 409
                )
            return ForecastResponse(
                **context.model_dump(),
                forecast_id=run.id,
                generated_at=run.created_at,
                points=points,
                totals=forecast_totals(points),
            )
