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
        unparseable = 0
        first_failure: str | None = None
        hit_cap = False
        with source.open(entry.path) as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                stripped = raw_line.strip()
                if not stripped:  # tolerate blank lines between records
                    continue
                try:
                    record = json.loads(stripped)
                except ValueError as exc:
                    # A truncated or corrupt line costs that line, never the file. Dropping the whole
                    # file would erase its row count and every column it was the only witness for.
                    unparseable += 1
                    if first_failure is None:
                        first_failure = f"line {line_number}: {exc}"
                    continue
                if not isinstance(record, dict):
                    continue  # a record is a column map; skip stray scalars/arrays rather than crash downstream
                rows.append(record)
                if row_cap is not None and len(rows) >= row_cap:
                    hit_cap = True
                    break

        # `num_rows` counts records the reader could parse. A line of valid JSON that simply is not a
        # row (a stray scalar or array) is not a row of this dataset, so it leaves the count exact and
        # sets no error. An *unparseable* line is data we failed to read, so it is reported: the
        # pipeline reads `error` to decide the file was not exhaustively scanned.
        #
        # A cap only costs the exact count when it actually stopped the read. A file smaller than the
        # cap was still read to EOF, so it keeps an exact count — which is what lets a capped profile
        # of a small dataset stay exhaustive instead of degrading every stat for no reason.
        num_rows = None if hit_cap else len(rows)
        error = f"skipped {unparseable} unparseable line(s); first at {first_failure}" if unparseable else None
        return ReadResult(rows=rows, rows_scanned=len(rows), num_rows=num_rows, arrow_schema=None, error=error)


register_reader(JsonlReader())
