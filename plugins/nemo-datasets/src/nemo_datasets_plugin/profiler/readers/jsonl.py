# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Line-delimited JSON reader. No declared schema; the row count is exact only on a full read."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import BinaryIO

from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.readers.base import FilePreview, ReadResult, register_reader

# Rows per batch, matching the parquet reader so the caller's working set does not depend on the
# format being folded.
_BATCH_ROWS = 1024

# Signatures of the formats a `.jsonl` most often turns out to be. Only *binary* ones are listed,
# which is the discipline: none of these bytes can begin a text file, so the check cannot produce a
# false positive. A file that is text but not line-delimited objects -- a pretty-printed array, a
# file of bare scalars -- is left to `_records`, which reports "skipped N unparseable line(s)".
_BINARY_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"PAR1", "a parquet file"),
    (b"\x1f\x8b", "a gzip archive"),
    (b"PK\x03\x04", "a zip archive"),
    (b"ARROW1", "an arrow IPC file"),
)

# Enough for the longest signature above. Read once, from a stream the caller is opening anyway.
_SNIFF_BYTES = 16


def _check_magic(stream: BinaryIO) -> None:
    """Reject a file whose leading bytes say it is some other format entirely.

    Line-delimited JSON has no signature of its own, so this can only say what the file is *not*.
    That is still the difference between "begins with the magic bytes of a gzip archive" and forty
    thousand lines of ``Expecting value``, which reads like corrupt data.

    Called from every entry point rather than :meth:`JsonlReader.peek` alone, because the pipeline
    discards what a peek raises and the read path is where this reaches a ``FileError``.
    """
    head = stream.read(_SNIFF_BYTES)
    stream.seek(0)
    for magic, description in _BINARY_MAGIC:
        if head.startswith(magic):
            raise ValueError(f"not line-delimited JSON: the file begins with the magic bytes of {description}")


def _records(stream) -> Iterator[tuple[dict | None, str | None]]:
    """Each line of the stream as either a record or a reason it was not one.

    Shared by :meth:`JsonlReader.read` and :meth:`JsonlReader.batches` so the two cannot disagree
    on what counts as a row: a blank line, a stray scalar and a truncated line are three different
    things, and only one is an error.
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
        """Nothing but a format check. A line-delimited file declares no schema and carries no row
        count, which is why a partition holding one cannot be folded without reading it first."""
        with source.open(entry.path) as stream:
            _check_magic(stream)
        return FilePreview()

    def batches(
        self,
        source: FileSource,
        entry: FileEntry,
        *,
        row_cap: int | None = None,
        errors: list[str] | None = None,
    ) -> Iterator[list[dict]]:
        """Rows in chunks, reporting any line it could not read into ``errors``.

        A corrupt line costs that line, never the file: dropping the file would erase its row count
        and every column it alone witnessed. The caller still has to be told, or a partially parsed
        file folds silently and looks complete.
        """
        rows: list[dict] = []
        scanned = 0
        unparseable = 0
        first_failure: str | None = None
        with source.open(entry.path) as stream:
            _check_magic(stream)
            for record, failure in _records(stream):
                if record is None:
                    unparseable += 1
                    if first_failure is None:
                        first_failure = failure
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
        if unparseable and errors is not None:
            errors.append(f"skipped {unparseable} unparseable line(s); first at {first_failure}")

    def read(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> ReadResult:
        rows: list[dict] = []
        unparseable = 0
        first_failure: str | None = None
        hit_cap = False
        with source.open(entry.path) as stream:
            _check_magic(stream)
            for record, failure in _records(stream):
                # Branch on the record, not the failure: the two are exclusive, and this narrows the
                # type without an ignore comment standing in for the reasoning.
                if record is None:
                    unparseable += 1
                    if first_failure is None:
                        first_failure = failure
                    continue
                rows.append(record)
                if row_cap is not None and len(rows) >= row_cap:
                    hit_cap = True
                    break

        # `num_rows` counts records the reader could parse. A line of valid JSON that is not a row (a
        # stray scalar) is not a row of this dataset, so it leaves the count exact and sets no error;
        # an unparseable line is data we failed to read, so it is reported and the pipeline uses
        # `error` to decide the file was not exhaustively scanned. A cap costs the exact count only
        # when it actually stopped the read -- a file smaller than the cap was read to EOF and keeps
        # an exact count, which lets a capped profile of a small dataset stay exhaustive.
        num_rows = None if hit_cap else len(rows)
        error = f"skipped {unparseable} unparseable line(s); first at {first_failure}" if unparseable else None
        return ReadResult(rows=rows, rows_scanned=len(rows), num_rows=num_rows, arrow_schema=None, error=error)


register_reader(JsonlReader())
