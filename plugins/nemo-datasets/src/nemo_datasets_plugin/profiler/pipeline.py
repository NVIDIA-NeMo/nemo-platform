# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The top-level profiling pipeline.

``profile(source)`` lists the files behind a :class:`FileSource`, groups them into partitions and
splits, reads them, and assembles a ``DatasetProfile``. This stage produces the structural envelope
— partitions, splits, FileRecords, content digest, sampling metadata — the derived row schema
(``features``), per-column ``stats``, and the full ``classification`` (roles, format, prompt form,
dataset type, and verifiability).

Every file is opened — sampling a subset of files would hide columns that appear only in later shards
— but each is read up to ``row_cap`` rows, so peak memory tracks the file count rather than the
dataset size. Files smaller than the cap are read to the end and keep their exact counts, so capping
costs nothing on a small dataset. Pass ``row_cap=None`` for a genuinely exhaustive scan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pyarrow as pa
from nemo_datasets_plugin.profiler.classify import classify
from nemo_datasets_plugin.profiler.digest import content_digest
from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.readers.base import detect_format, get_reader, is_unsupported_data
from nemo_datasets_plugin.profiler.schema import derive_features
from nemo_datasets_plugin.profiler.splits import resolve_splits
from nemo_datasets_plugin.profiler.stats import derive_probes, derive_stats
from nemo_platform_plugin.files.dataset_profile import (
    ColumnStats,
    DatasetProfile,
    Evidence,
    FeatureSchema,
    FileRecord,
    PartitionClassification,
    PartitionProfile,
    SamplingInfo,
    SplitProfile,
)

PROFILER_NAME = "nemo-dataset-profiler"
PROFILER_VERSION = "0.1.0"

# Rows read per file by default. Every file is still opened — head-sampling a *subset of files* would
# hide columns that appear only in later shards — but each is capped, so peak memory scales with the
# file count rather than the dataset size. Uncapped, a partition materializes every row of every file
# as Python dicts at roughly 6x the on-disk parquet size, which puts a 10 GB dataset far past any
# reasonable machine. A thousand rows per file is ample for the statistics computed here (length
# quantiles, rates, cardinality); pass ``row_cap=None`` for a genuinely exhaustive scan.
DEFAULT_ROW_CAP = 1000


def _format_of(path: str) -> str:
    """The registered format of a data file. Callers pass only pre-filtered ``data_entries``, so the
    format is always known; a None here would mean that invariant was broken."""
    file_format = detect_format(path)
    if file_format is None:
        raise ValueError(f"no registered format for {path!r}")
    return file_format


def profile(
    source: FileSource,
    *,
    created_at: datetime | None = None,
    row_cap: int | None = DEFAULT_ROW_CAP,
) -> DatasetProfile:
    """Profile the dataset behind ``source`` into a ``DatasetProfile``.

    ``row_cap`` bounds how many rows are read from each file; ``None`` reads every row, which is
    exact but scales memory with the dataset rather than the file count. Files smaller than the cap
    are still read to the end, so a capped profile of a small dataset stays exhaustive.

    ``created_at`` is injectable so a profile can be made reproducible byte-for-byte in tests; it
    defaults to the current UTC time.
    """
    created_at = created_at or datetime.now(timezone.utc)
    all_entries = source.list_files()
    data_entries = [entry for entry in all_entries if detect_format(entry.path) is not None]
    # Files that plainly hold records but have no reader yet. They are not profiled, but they must be
    # reported: silently dropping them let a directory of .csv shards profile as an exhaustively
    # scanned, empty dataset — indistinguishable from a dataset that really is empty.
    unsupported = sorted(
        entry.path for entry in all_entries if detect_format(entry.path) is None and is_unsupported_data(entry.path)
    )

    partitions: list[PartitionProfile] = []
    rows_scanned = 0
    files_read = 0
    all_scanned = True

    for partition_name, partition_entries in group_partitions(data_entries):
        format_groups = _split_by_format(partition_entries)
        for file_format, format_entries in format_groups:
            # A directory that holds more than one format yields one partition per format; qualify
            # the name so the partitions stay distinct. A single-format directory keeps its bare name.
            name = f"{partition_name}:{file_format}" if len(format_groups) > 1 else partition_name
            outcome = _profile_partition(source, name, file_format, format_entries, row_cap)
            partitions.append(outcome.partition)
            rows_scanned += outcome.rows_scanned
            files_read += outcome.files_read
            all_scanned = all_scanned and outcome.scanned_all

    # Data we could not read is data we did not scan, so unsupported files defeat exhaustiveness just
    # as an unreadable file does.
    exhaustive = all_scanned and not unsupported
    profiler_info: dict = {"name": PROFILER_NAME, "version": PROFILER_VERSION}
    if unsupported:
        profiler_info["unsupported_files"] = unsupported

    sampling = SamplingInfo(
        exhaustive=exhaustive,
        # The policy in effect, which `exhaustive` deliberately does not encode: a capped run over
        # files that all fit under the cap is still a full scan, and an uncapped run can still fall
        # short of exhaustive because a file was unreadable.
        strategy="full" if row_cap is None else "head_per_file",
        # `rows_total` is documented as never zero: a 0 here would read as "this dataset is empty"
        # when it more often means nothing was recognized. Unknown is the honest answer.
        rows_total=rows_scanned if exhaustive and rows_scanned else None,
        rows_scanned=rows_scanned,
        files_scanned=files_read,  # files actually opened and read, not files merely listed
        per_file_row_cap=row_cap,
        seed=None,  # head sampling makes no random choices; a seed would be theatre
    )
    return DatasetProfile(
        # Digest only the files stored as FileRecords, so the profile can recompute its own digest.
        content_digest=content_digest(data_entries),
        created_at=created_at,
        profiler_info=profiler_info,
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


def _unify_schemas(schemas: list[pa.Schema]) -> pa.Schema | None:
    """One schema describing every file of the partition, or None when they cannot be reconciled.

    Taking the first file's schema and ignoring the rest makes the profile depend on which shard
    happens to sort first: a column that appears only in a later shard would vanish from ``features``
    (and so from ``stats``), and the same data would classify differently under a different file
    order. Unifying is order-independent for the common case — later shards adding columns.

    A genuine type conflict for the same column name has no correct answer here, so we return None
    and let the caller fall back to inferring from the rows themselves, which widens the conflicting
    column to ``json`` rather than asserting one shard's type over the other's.
    """
    if not schemas:
        return None
    if len(schemas) == 1:
        return schemas[0]
    try:
        return pa.unify_schemas(schemas)
    except pa.ArrowException:
        return None


def _measure(
    partition_rows: list[dict],
    arrow_schemas: list[pa.Schema],
    *,
    exhaustive: bool,
    all_declared: bool,
) -> tuple[list[FeatureSchema], dict[str, ColumnStats], PartitionClassification]:
    """Derive schema, stats and classification, degrading to structure-only if any of it fails.

    ``all_declared`` says whether *every* file that contributed rows carried a declared schema. When
    one did not, the unified schema describes only some of the rows, and using it would erase any
    column the schemaless files were the sole witness for — so infer from the rows instead, which
    sees all of them. Declared type fidelity (int32 widening to int64) is the cost, and it is the
    honest one: a declared schema cannot be asserted over files that declare nothing.

    These stages are pure computation over rows already in memory, so a failure here is either a
    profiler bug or data shaped in a way no detector anticipated. Reads are already isolated per
    file; leaving this stage unguarded meant one odd value — a chat message whose ``role`` is a number
    — could abort an otherwise complete profile from the one place nothing was catching. The
    partition's structure (files, splits, row counts) is established by then and stays useful, so the
    failure costs its measurements and says so, rather than the entire run.
    """
    try:
        declared = _unify_schemas(arrow_schemas) if all_declared else None
        features = derive_features(partition_rows, declared)
        stats = derive_stats(features, partition_rows, exhaustive=exhaustive)
        # Probes are measured over every column, independent of the roles classify is about to
        # assign, so a content signal survives a column name the alias table does not know.
        probes = derive_probes(features, partition_rows)
        return features, stats, classify(features, stats, partition_rows, probes=probes)
    except Exception as exc:
        detail = f"could not measure this partition: {type(exc).__name__}: {exc}"
        return [], {}, PartitionClassification(dataset_type="unknown", evidence=[Evidence(kind="error", detail=detail)])


@dataclass(frozen=True)
class _PartitionOutcome:
    """One partition plus what it contributes to the dataset-level sampling envelope."""

    partition: PartitionProfile
    rows_scanned: int
    files_read: int  # files actually opened and read, so `files_scanned` can exclude failures
    scanned_all: bool


def _profile_partition(
    source: FileSource, name: str, file_format: str, entries: list[FileEntry], row_cap: int | None
) -> _PartitionOutcome:
    """Profile one format-homogeneous partition.

    An unreadable file (or a format with no registered reader) is isolated: it keeps its FileRecord,
    records *why* on ``FileRecord.error``, contributes no rows, and flips ``scanned_all`` off — it
    never aborts the profile.
    """
    partition_rows: list[dict] = []
    arrow_schemas: list[pa.Schema] = []
    all_declared = True  # every file that contributed rows carried a declared schema
    rows_scanned = 0
    files_read = 0
    partition_scanned = True
    split_profiles: list[SplitProfile] = []
    for split in resolve_splits(entries):
        file_records: list[FileRecord] = []
        split_examples = 0
        split_counts_known = True  # every file's exact total row count is known (footer or full scan)
        split_scanned = True  # every row of every file was actually parsed
        for entry in split.entries:
            error: str | None = None
            try:
                result = get_reader(file_format).read(source, entry, row_cap=row_cap)
            except Exception as exc:
                # Failure isolation: an unreadable file (or missing reader) keeps its identity,
                # skips its rows, and does not abort the profile. The reason is recorded rather than
                # swallowed, so a consumer can tell corrupt input from a profiler bug.
                result = None
                error = f"{type(exc).__name__}: {exc}"
            if result is None:
                num_rows = None
                scanned_all = False
            else:
                files_read += 1
                error = result.error
                num_rows = result.num_rows
                rows_scanned += result.rows_scanned
                partition_rows.extend(result.rows)
                if result.arrow_schema is not None:
                    arrow_schemas.append(result.arrow_schema)
                elif result.rows:
                    # Rows with no schema behind them: the unified schema no longer covers the
                    # partition, so _measure must infer from rows rather than trust a partial one.
                    all_declared = False
                # Exhaustive requires parsing every row; a known footer count alone is not enough, and
                # a partial read (corrupt lines skipped) is not exhaustive however many rows it got.
                scanned_all = num_rows is not None and result.rows_scanned >= num_rows and error is None
            file_records.append(
                FileRecord(
                    path=entry.path,
                    size_bytes=entry.size_bytes,
                    checksum=entry.checksum,
                    num_rows=num_rows,
                    error=error,
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
    features, stats, classification = _measure(
        partition_rows, arrow_schemas, exhaustive=partition_scanned, all_declared=all_declared
    )
    partition = PartitionProfile(
        name=name,
        file_format=file_format,
        splits=split_profiles,
        features=features,
        stats=stats,
        classification=classification,
    )
    return _PartitionOutcome(
        partition=partition, rows_scanned=rows_scanned, files_read=files_read, scanned_all=partition_scanned
    )
