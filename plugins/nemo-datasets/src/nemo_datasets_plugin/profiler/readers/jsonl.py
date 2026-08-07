# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Line-delimited JSON reader. No declared schema; the row count is exact only on a full read."""

from __future__ import annotations

import json
from collections.abc import Iterator

from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.readers.base import FilePreview, ReadResult, register_reader

# Rows handed over at a time by :meth:`JsonlReader.batches`, matching the parquet reader so the
# caller's working set does not depend on which format it happens to be folding.
_BATCH_ROWS = 1024


def _records(stream) -> Iterator[tuple[dict | None, str | None]]:
    """Each line of the stream as either a record or a reason it was not one.

    Shared by :meth:`JsonlReader.read` and :meth:`JsonlReader.batches` so the two cannot drift on
    what counts as a row -- a blank line, a stray scalar and a truncated line are three different
    things and only one of them is an error.
    """
    for line_number, raw_line in enumerate(stream, start=1):
        stripped = raw_line.strip()
        if not stripped:  # tolerate blank lines between records
            continue
        try:
            record = json.loads(stripped)
        except ValueError as exc:
            # A truncated or corrupt line costs that line, never the file. Dropping the whole file
            # would erase its row count and every column it was the only witness for.
            yield None, f"line {line_number}: {exc}"
            continue
        if isinstance(record, dict):
            yield record, None
        # a record is a column map; stray scalars/arrays are skipped rather than crash downstream


class JsonlReader:
    file_format = "jsonl"

    def peek(self, source: FileSource, entry: FileEntry) -> FilePreview:
        """Nothing. A line-delimited file declares no schema and carries no row count, which is why
        a partition holding one cannot be folded without reading it first."""
        return FilePreview()

    def batches(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> Iterator[list[dict]]:
        """Rows in chunks. Parse errors are silent here -- :meth:`read` is the path that accounts for
        them, and the fold path does not reach a file with no declared schema."""
        rows: list[dict] = []
        scanned = 0
        with source.open(entry.path) as stream:
            for record, _ in _records(stream):
                if record is None:
                    continue
                rows.append(record)
                scanned += 1
                if len(rows) >= _BATCH_ROWS:
                    yield rows
                    rows = []
                if row_cap is not None and scanned >= row_cap:
                    break
        if rows:
            yield rows

    def read(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> ReadResult:
        rows: list[dict] = []
        unparseable = 0
        first_failure: str | None = None
        hit_cap = False
        with source.open(entry.path) as stream:
            for record, failure in _records(stream):
                # Branching on the record rather than the failure: the two are exclusive, and this
                # way the type narrows without an ignore standing in for the reasoning.
                if record is None:
                    unparseable += 1
                    if first_failure is None:
                        first_failure = failure
                    continue
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
