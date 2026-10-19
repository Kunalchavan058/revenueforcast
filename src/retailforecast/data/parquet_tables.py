"""Fixed normalized Parquet schemas and bounded, order-preserving CSV conversion."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from retailforecast.data.pipeline_config import ProcessingSettings
from retailforecast.data.validation import SOURCE_MODELS, source_rows

TABLE_NAMES = {
    "store.csv": "stores",
    "train.csv": "daily_sales",
    "test.csv": "forecast_inputs",
    "sample_submission.csv": "submission_template",
}


def table_schema(filename: str) -> pa.Schema:
    """Declare explicit integer/decimal/date/category types; never infer from mixed CSVs."""
    calendar = [
        pa.field("store_id", pa.int32(), nullable=False),
        pa.field("date", pa.date32(), nullable=False),
        pa.field("day_of_week", pa.int8(), nullable=False),
        pa.field("is_open", pa.bool_(), nullable=filename == "test.csv"),
        pa.field("promotion", pa.bool_(), nullable=False),
        pa.field("state_holiday", pa.string(), nullable=False),
        pa.field("school_holiday", pa.bool_(), nullable=False),
    ]
    if filename == "train.csv":
        fields = calendar + [
            pa.field("sales", pa.decimal128(18, 4), nullable=False),
            pa.field("customers", pa.int32(), nullable=False),
        ]
    elif filename == "test.csv":
        fields = calendar + [pa.field("submission_id", pa.int32(), nullable=False)]
    elif filename == "sample_submission.csv":
        fields = [
            pa.field("submission_id", pa.int32(), nullable=False),
            pa.field("placeholder_sales", pa.decimal128(18, 4), nullable=False),
        ]
    elif filename == "store.csv":
        fields = [
            pa.field("store_id", pa.int32(), nullable=False),
            pa.field("store_type", pa.string()),
            pa.field("assortment", pa.string()),
            pa.field("competition_distance", pa.decimal128(18, 4)),
            pa.field("competition_open_since_month", pa.int8()),
            pa.field("competition_open_since_year", pa.int16()),
            pa.field("promo2", pa.bool_()),
            pa.field("promo2_since_week", pa.int8()),
            pa.field("promo2_since_year", pa.int16()),
            pa.field("promo_interval", pa.string()),
        ]
    else:
        raise ValueError(f"Unknown source file: {filename}")
    return pa.schema(fields)


def normalized_row(filename: str, values: dict[str, str | None]) -> dict[str, object]:
    """Reuse source contracts; rename placeholders and preserve NULL/actual label values."""
    parsed = SOURCE_MODELS[filename].model_validate(values)
    row: dict[str, object] = parsed.model_dump()
    if filename == "sample_submission.csv":
        row["placeholder_sales"] = row.pop("sales")
    for name in ["is_open", "promotion", "school_holiday", "promo2"]:
        if name in row and row[name] is not None:
            row[name] = bool(row[name])
    return row


def write_normalized_table(
    source: Path,
    destination: Path,
    settings: ProcessingSettings,
) -> int:
    """Stream fixed-size row groups, atomically replacing one completed Parquet file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    schema = table_schema(source.name)
    count = 0
    batch: list[dict[str, object]] = []
    try:
        with pq.ParquetWriter(
            temporary,
            schema,
            version="2.6",
            data_page_version="1.0",
            compression=settings.compression,
            compression_level=settings.compression_level,
            use_dictionary=True,
            write_statistics=True,
        ) as writer:
            for _, values in source_rows(source):
                batch.append(normalized_row(source.name, values))
                if len(batch) == settings.batch_rows:
                    writer.write_table(
                        pa.Table.from_pylist(batch, schema=schema),
                        row_group_size=settings.batch_rows,
                    )
                    count += len(batch)
                    batch.clear()
            if batch:
                writer.write_table(
                    pa.Table.from_pylist(batch, schema=schema), row_group_size=settings.batch_rows
                )
                count += len(batch)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return count
