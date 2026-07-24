# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The top-level profiling pipeline.

``profile(source)`` lists the files behind a :class:`FileSource`, groups them into partitions and
splits, reads them, and assembles a ``DatasetProfile``. This stage produces the structural envelope
— partitions, splits, FileRecords, content digest, sampling metadata — the derived row schema
(``features``), per-column ``stats``, and the full ``classification`` (roles, format, prompt form,
dataset type, and verifiability).

Reads are exhaustive (every row of every file). Sampling large datasets with bounded probes is a
later, drop-in optimization behind the same reader seam.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nemo_datasets_plugin.profiler.classify import classify
from nemo_datasets_plugin.profiler.digest import content_digest
from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.readers.base import detect_format, get_reader
from nemo_datasets_plugin.profiler.schema import derive_features
from nemo_datasets_plugin.profiler.splits import resolve_splits
from nemo_datasets_plugin.profiler.stats import derive_stats
from nemo_platform_plugin.files.dataset_profile import (
    DatasetProfile,
    FileRecord,
    PartitionProfile,
    SamplingInfo,
    SplitProfile,
)

PROFILER_NAME = "nemo-dataset-profiler"
PROFILER_VERSION = "0.1.0"


def _format_of(path: str) -> str:
    """The registered format of a data file. Callers pass only pre-filtered ``data_entries``, so the
    format is always known; a None here would mean that invariant was broken."""
    file_format = detect_format(path)
    if file_format is None:
        raise ValueError(f"no registered format for {path!r}")
    return file_format


def profile(source: FileSource, *, created_at: datetime | None = None) -> DatasetProfile:
    """Profile the dataset behind ``source`` into a ``DatasetProfile``.

    ``created_at`` is injectable so a profile can be made reproducible byte-for-byte in tests; it
    defaults to the current UTC time.
    """
    created_at = created_at or datetime.now(timezone.utc)
    all_entries = source.list_files()
    data_entries = [entry for entry in all_entries if detect_format(entry.path) is not None]

    partitions: list[PartitionProfile] = []
    rows_scanned = 0
    all_scanned = True

    for partition_name, partition_entries in group_partitions(data_entries):
        format_groups = _split_by_format(partition_entries)
        for file_format, format_entries in format_groups:
            # A directory that holds more than one format yields one partition per format; qualify
            # the name so the partitions stay distinct. A single-format directory keeps its bare name.
            name = f"{partition_name}:{file_format}" if len(format_groups) > 1 else partition_name
            partition, partition_rows_scanned, partition_scanned = _profile_partition(
                source, name, file_format, format_entries
            )
            partitions.append(partition)
            rows_scanned += partition_rows_scanned
            all_scanned = all_scanned and partition_scanned

    sampling = SamplingInfo(
        exhaustive=all_scanned,
        strategy="full",
        rows_scanned=rows_scanned,
        rows_total=rows_scanned if all_scanned else None,
        files_scanned=len(data_entries),
        per_file_row_cap=None,
        seed=None,
    )
    return DatasetProfile(
        # Digest only the files stored as FileRecords, so the profile can recompute its own digest.
        content_digest=content_digest(data_entries),
        created_at=created_at,
        profiler_info={"name": PROFILER_NAME, "version": PROFILER_VERSION},
        sampling=sampling,
        partitions=partitions,
    )


def _split_by_format(entries: list[FileEntry]) -> list[tuple[str, list[FileEntry]]]:
    """Sub-group a directory's files by format so each profiled partition is format-homogeneous.

    ``group_partitions`` groups by directory only, but one directory can hold more than one format
    (a stray ``.jsonl`` beside ``.parquet`` shards). Left mixed, a partition would derive its schema
    from whichever format was read first and then measure rows from both. Sorted for deterministic
    partition order; ``entries`` are pre-filtered ``data_entries`` so every format is registered.
    """
    by_format: dict[str, list[FileEntry]] = {}
    for entry in entries:
        by_format.setdefault(_format_of(entry.path), []).append(entry)
    return sorted(by_format.items())


def _profile_partition(
    source: FileSource, name: str, file_format: str, entries: list[FileEntry]
) -> tuple[PartitionProfile, int, bool]:
    """Profile one format-homogeneous partition.

    Returns the partition plus its ``(rows_scanned, scanned_all)`` contribution to the dataset-level
    sampling envelope. An unreadable file (or a format with no registered reader) is isolated: it
    keeps its FileRecord, contributes no rows, and flips ``scanned_all`` off — it never aborts.
    """
    partition_rows: list[dict] = []
    arrow_schema = None
    rows_scanned = 0
    partition_scanned = True
    split_profiles: list[SplitProfile] = []
    for split in resolve_splits(entries):
        file_records: list[FileRecord] = []
        split_examples = 0
        split_counts_known = True  # every file's exact total row count is known (footer or full scan)
        split_scanned = True  # every row of every file was actually parsed
        for entry in split.entries:
            try:
                result = get_reader(file_format).read(source, entry)
            except Exception:
                # Failure isolation: an unreadable file (or missing reader) keeps its identity,
                # skips its rows, and does not abort the profile.
                result = None
            if result is None:
                num_rows = None
                scanned_all = False
            else:
                num_rows = result.num_rows
                rows_scanned += result.rows_scanned
                partition_rows.extend(result.rows)
                if arrow_schema is None:
                    arrow_schema = result.arrow_schema
                # Exhaustive requires parsing every row; a known footer count alone is not enough.
                scanned_all = num_rows is not None and result.rows_scanned >= num_rows
            file_records.append(
                FileRecord(
                    path=entry.path,
                    size_bytes=entry.size_bytes,
                    checksum=entry.checksum,
                    num_rows=num_rows,
                )
            )
            if num_rows is None:
                split_counts_known = False
            else:
                split_examples += num_rows
            if not scanned_all:
                split_scanned = False
        partition_scanned = partition_scanned and split_scanned
        split_profiles.append(
            SplitProfile(
                name=split.name,
                canonical=split.canonical,
                files=file_records,
                num_examples=split_examples if split_counts_known else None,
            )
        )
    features = derive_features(partition_rows, arrow_schema)
    stats = derive_stats(features, partition_rows, exhaustive=partition_scanned)
    partition = PartitionProfile(
        name=name,
        file_format=file_format,
        splits=split_profiles,
        features=features,
        stats=stats,
        classification=classify(features, stats, partition_rows),
    )
    return partition, rows_scanned, partition_scanned
