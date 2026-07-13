# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parquet reader — the footer gives an exact row count and the declared schema for free."""

from __future__ import annotations

import pyarrow.parquet as pq
from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.readers.base import ReadResult, register_reader


class ParquetReader:
    file_format = "parquet"

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
