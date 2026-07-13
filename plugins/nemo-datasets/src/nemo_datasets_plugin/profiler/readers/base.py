# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-format reader contract and registry.

Each reader is a stateless handler for one on-disk format, safe to reuse across files. Readers are
looked up by ``file_format`` (from :func:`detect_format`) so the pipeline never branches on format
itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol

import pyarrow as pa

from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource


@dataclass(frozen=True)
class ReadResult:
    """What a format reader returns for one file."""

    rows: list[dict[str, Any]]  # the rows read (a sample, or all of them)
    rows_scanned: int  # number of rows actually parsed
    num_rows: int | None = None  # exact total when cheaply known (e.g. a parquet footer), else None
    arrow_schema: pa.Schema | None = None  # the declared column schema, when the format carries one


class FormatReader(Protocol):
    """Reads schema and rows for one file format."""

    file_format: ClassVar[str]

    def read(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> ReadResult:
        """Read up to ``row_cap`` rows (all rows when None) plus whatever the format declares cheaply."""
        ...


_READERS: dict[str, FormatReader] = {}


def register_reader(reader: FormatReader) -> None:
    _READERS[reader.file_format] = reader


def get_reader(file_format: str) -> FormatReader:
    try:
        return _READERS[file_format]
    except KeyError:
        raise KeyError(f"no reader registered for file format {file_format!r}") from None


_EXTENSION_FORMATS = {
    ".parquet": "parquet",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
}


def detect_format(path: str) -> str | None:
    """Map a file path to a registered format by extension, or None when unrecognized."""
    return _EXTENSION_FORMATS.get(Path(path).suffix.lower())
