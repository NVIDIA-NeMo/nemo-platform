# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Line-delimited JSON reader. No declared schema; the row count is exact only on a full read."""

from __future__ import annotations

import json

from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.readers.base import ReadResult, register_reader


class JsonlReader:
    file_format = "jsonl"

    def read(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> ReadResult:
        rows: list[dict] = []
        with source.open(entry.path) as stream:
            for raw_line in stream:
                stripped = raw_line.strip()
                if not stripped:  # tolerate blank lines between records
                    continue
                rows.append(json.loads(stripped))
                if row_cap is not None and len(rows) >= row_cap:
                    break

        num_rows = len(rows) if row_cap is None else None
        return ReadResult(rows=rows, rows_scanned=len(rows), num_rows=num_rows, arrow_schema=None)


register_reader(JsonlReader())
