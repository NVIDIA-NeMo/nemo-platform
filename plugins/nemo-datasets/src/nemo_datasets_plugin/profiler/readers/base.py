# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-format reader contract and registry.

Each reader is a stateless handler for one on-disk format, safe to reuse across files. Readers are
looked up by ``file_format`` (from :func:`detect_format`) so the pipeline never branches on format
itself. Built-in readers self-register (a ``register_reader`` call at the bottom of each module) and
are loaded lazily on the first :func:`get_reader` call, so importing this module does not pull in
pyarrow until a reader is actually needed.
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
    # Why the read understood less than the whole file, when that happened. None means nothing was
    # lost. This is the only channel a reader has to explain a partial result, so a consumer can tell
    # "corrupt input" from "unsupported format" from "profiler bug" instead of seeing a silent gap.
    error: str | None = None


class FormatReader(Protocol):
    """Reads schema and rows for one file format."""

    file_format: ClassVar[str]

    def read(self, source: FileSource, entry: FileEntry, *, row_cap: int | None = None) -> ReadResult:
        """Read up to ``row_cap`` rows (all rows when None) plus whatever the format declares cheaply."""
        ...


_READERS: dict[str, FormatReader] = {}
_builtins_loaded = False


def _load_builtin_readers() -> None:
    """Import the built-in reader modules so their self-registration runs (once).

    Deferred to call time — not import time — so there is no cycle with the reader modules that import
    from this one, and pyarrow stays out of the import graph until a reader is actually resolved.
    """
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    from nemo_datasets_plugin.profiler.readers import jsonl, parquet  # noqa: F401  self-registering


def register_reader(reader: FormatReader) -> None:
    _READERS[reader.file_format] = reader


def get_reader(file_format: str) -> FormatReader:
    _load_builtin_readers()
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


# Extensions that plainly hold dataset records but have no reader yet. Naming them explicitly is what
# lets the profiler say "there is data here I cannot read" instead of treating a dataset it does not
# understand as an empty one — a README or a LICENSE is genuinely not data and stays ignored.
_UNSUPPORTED_DATA_EXTENSIONS = {".csv", ".tsv", ".arrow", ".feather", ".json", ".avro", ".orc"}


def is_unsupported_data(path: str) -> bool:
    """Whether a path looks like dataset records this profiler has no reader for."""
    return Path(path).suffix.lower() in _UNSUPPORTED_DATA_EXTENSIONS
