# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parquet reader — the footer gives an exact row count and the declared schema for free."""

from __future__ import annotations

from collections.abc import Iterator

import pyarrow.parquet as pq
from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.readers.base import FilePreview, ReadResult, register_reader

# Rows handed over at a time. Small enough that the working set is a knob independent of the
# dataset, large enough that per-batch overhead stays invisible.
_BATCH_ROWS = 1024


class ParquetReader:
    file_format = "parquet"

    def peek(self, source: FileSource, entry: FileEntry) -> FilePreview:
        """Schema and exact row count from the footer. Reads no rows, so a partition's whole shape is
        knowable for the cost of one seek per file."""
        with source.open(entry.path) as stream:
            parquet_file = pq.ParquetFile(stream)
            return FilePreview(arrow_schema=parquet_file.schema_arrow, num_rows=parquet_file.metadata.num_rows)

    def batches(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> Iterator[list[dict]]:
        """Rows in chunks, so the caller can fold them and let each chunk go."""
        scanned = 0
        with source.open(entry.path) as stream:
            parquet_file = pq.ParquetFile(stream)
            if row_cap == 0:
                return
            for batch in parquet_file.iter_batches(batch_size=min(row_cap or _BATCH_ROWS, _BATCH_ROWS)):
                rows = batch.to_pylist()
                if row_cap is not None and scanned + len(rows) > row_cap:
                    rows = rows[: row_cap - scanned]
                scanned += len(rows)
                if rows:
                    yield rows
                if row_cap is not None and scanned >= row_cap:
                    return

    def read(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> ReadResult:
        with source.open(entry.path) as stream:
            parquet_file = pq.ParquetFile(stream)
            num_rows = parquet_file.metadata.num_rows
            arrow_schema = parquet_file.schema_arrow
            if row_cap == 0:
                return ReadResult(rows=[], rows_scanned=0, num_rows=num_rows, arrow_schema=arrow_schema)

            rows: list[dict] = []
            for batch in parquet_file.iter_batches(batch_size=row_cap or 1024):
                rows.extend(batch.to_pylist())
                if row_cap is not None and len(rows) >= row_cap:
                    break

        if row_cap is not None:
            rows = rows[:row_cap]
        return ReadResult(rows=rows, rows_scanned=len(rows), num_rows=num_rows, arrow_schema=arrow_schema)


register_reader(ParquetReader())
