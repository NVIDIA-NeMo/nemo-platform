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
from pathlib import PurePosixPath

import pyarrow as pa
from nemo_datasets_plugin.profiler.classify import classify
from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.readers.base import detect_format, get_reader, is_unsupported_data
from nemo_datasets_plugin.profiler.schema import derive_features
from nemo_datasets_plugin.profiler.splits import resolve_splits
from nemo_datasets_plugin.profiler.stats import derive_probes, derive_stats, quote_enumerations
from nemo_platform_plugin.files.dataset_profile import (
    ColumnStats,
    DatasetProfile,
    Evidence,
    FeatureSchema,
    FileError,
    PartitionClassification,
    PartitionProfile,
    SamplingInfo,
    SplitProfile,
)

PROFILER_NAME = "nemo-dataset-profiler"
PROFILER_VERSION = "0.1.0"

# Rows a partition may read, in total, by default. Every file is still opened — head-sampling a
# *subset of files* would hide columns that appear only in later shards — but the budget is divided
# across them, so peak memory tracks the budget rather than the shard count. A per-file cap put the
# knob on the wrong axis: at 1000 rows each, resharding a dataset from 100 files to 10,000 took peak
# heap from 135 MB to 13.5 GB while describing exactly the same data. Ten thousand rows is ample for
# the statistics computed here (length quantiles, rates, cardinality); pass ``row_budget=None`` for a
# genuinely exhaustive scan.
DEFAULT_ROW_BUDGET = 10_000

# Rows read from a file however thin the budget gets. Below this a file cannot contribute the columns
# it alone witnesses, which is the whole reason every file is opened rather than a subset sampled. It
# is what makes the budget a target rather than a ceiling: 10,000 shards read this many each.
MIN_ROWS_PER_FILE = 10


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
    row_budget: int | None = DEFAULT_ROW_BUDGET,
    column_roles: dict[str, str] | None = None,
) -> DatasetProfile:
    """Profile the dataset behind ``source`` into a ``DatasetProfile``.

    ``row_budget`` bounds how many rows each *partition* reads in total, divided across its files;
    ``None`` reads every row, which is exact but scales memory with the dataset. Files smaller than
    their share are read to the end, so a budgeted profile of a small dataset stays complete.

    ``column_roles`` maps a column name to a role the caller is asserting, for datasets whose column
    names the role table does not recognize. Hints take precedence over name detection but still have
    to pass the dtype gates, and a rejected one is reported as evidence rather than dropped.

    ``created_at`` is injectable so a profile can be made reproducible byte-for-byte in tests; it
    defaults to the current UTC time.
    """
    created_at = created_at or datetime.now(timezone.utc)
    all_entries = source.list_files()
    data_entries = [entry for entry in all_entries if detect_format(entry.path) is not None]
    # Files that plainly hold records but have no reader yet. They are not profiled, but they must be
    # reported: silently dropping them let a directory of .csv shards profile as an exhaustively
    # scanned, empty dataset — indistinguishable from a dataset that really is empty. They get real
    # FileErrors like any other file the profiler could not read, just at the envelope, since no
    # partition ever grouped them. Kept as entries, not just paths, because their bytes still count
    # toward the size of the fileset even though no partition will ever weigh them.
    unreadable_entries = [
        entry
        for entry in sorted(all_entries, key=lambda entry: entry.path)
        if detect_format(entry.path) is None and is_unsupported_data(entry.path)
    ]
    file_errors = [
        FileError(
            path=entry.path,
            error=f"no reader for '{PurePosixPath(entry.path).suffix.lower()}' files",
        )
        for entry in unreadable_entries
    ]

    partitions: list[PartitionProfile] = []
    rows_scanned = 0
    files_read = 0
    # None once any file's row count is unknown: the fileset's total is then unknowable, not zero.
    rows_present: int | None = 0

    for name, partition_entries in group_partitions(data_entries):
        outcome = _profile_partition(source, name, partition_entries, row_budget, column_roles or {})
        partitions.append(outcome.partition)
        rows_scanned += outcome.rows_scanned
        files_read += outcome.files_read
        rows_present = _add_known(rows_present, outcome.rows_present)
        file_errors.extend(outcome.file_errors)

    # A file the profiler could not use holds an unknown number of rows, so it makes the fileset
    # total unknown — whether it was skipped for want of a reader or failed mid-read.
    if file_errors:
        rows_present = None

    sampling = SamplingInfo(
        rows_scanned=rows_scanned,
        rows_present=rows_present,
        files_read=files_read,  # files actually opened and read, not files merely listed
        # Every data file, readable or not: the denominator that makes `files_read` a fraction rather
        # than a bare count. Non-data files (a README, a LICENSE) are not data and are counted nowhere.
        files_present=len(data_entries) + len(unreadable_entries),
        # Weighed over the same set, so a fileset the profiler could not read still reports its size.
        # Summing the splits would miss the unreadable files, which never reach a partition.
        bytes_present=sum(entry.size_bytes for entry in data_entries)
        + sum(entry.size_bytes for entry in unreadable_entries),
        row_budget=row_budget,
    )
    return DatasetProfile(
        created_at=created_at,
        profiler_info={"name": PROFILER_NAME, "version": PROFILER_VERSION},
        sampling=sampling,
        partitions=partitions,
        # Sorted so a reader scanning for trouble sees it in a stable order, whatever partition it
        # came from; partitions contribute theirs as they are profiled.
        file_errors=sorted(file_errors, key=lambda error: error.path),
    )


def _per_file_cap(row_budget: int | None, file_count: int) -> int | None:
    """Split a partition's row budget across its files.

    Bounded below by :data:`MIN_ROWS_PER_FILE`, which is what makes the budget a target rather than a
    ceiling: at a thousand shards the arithmetic share is ten rows, and at ten thousand it would be
    one, which is too thin to witness a column. Overshooting the budget there is the right trade --
    the alternative is sampling a *subset of files*, which hides columns that appear only in later
    shards, and file-level sampling is the tier of this problem still to solve.
    """
    if row_budget is None:
        return None
    if file_count <= 1:
        return row_budget
    return max(MIN_ROWS_PER_FILE, row_budget // file_count)


def _add_known(total: int | None, addend: int | None) -> int | None:
    """Sum two counts, where ``None`` means unknown and poisons the total.

    A fileset whose row count is unknown for even one file has an unknown total — reporting the sum
    of the rest would look like a fact and read low.
    """
    if total is None or addend is None:
        return None
    return total + addend


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
    all_declared: bool,
    column_roles: dict[str, str],
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
        stats = derive_stats(features, partition_rows)
        # Probes are measured over every column, independent of the roles classify is about to
        # assign, so a content signal survives a column name the alias table does not know.
        probes = derive_probes(features, partition_rows)
        classification = classify(features, stats, partition_rows, probes=probes, column_roles=column_roles)
        # Last, because the roles classification assigns are what decide whether a column's values
        # may be quoted at all — cardinality only bounds how many.
        quote_enumerations(features, stats, partition_rows)
        return features, stats, classification
    except Exception as exc:
        detail = f"could not measure this partition: {type(exc).__name__}: {exc}"
        return [], {}, PartitionClassification(dataset_type="unknown", evidence=[Evidence(kind="error", detail=detail)])


@dataclass(frozen=True)
class _PartitionOutcome:
    """One partition plus what it contributes to the dataset-level sampling envelope."""

    partition: PartitionProfile
    rows_scanned: int
    files_read: int  # files actually opened and read, so `files_read` can exclude failures
    rows_present: int | None  # rows known to exist here, or None once any file's count is unknown
    file_errors: list[FileError]  # files this partition grouped but could not fully read


def _profile_partition(
    source: FileSource,
    name: str,
    entries: list[FileEntry],
    row_budget: int | None,
    column_roles: dict[str, str],
) -> _PartitionOutcome:
    """Profile one partition — the files of one source directory, whatever formats they are in.

    The reader is resolved per file rather than per partition. Format is a property of a file, and
    a directory holding two of them is a stray file, not a second dataset; splitting the partition
    to keep one scalar ``file_format`` true is what made partition names unstable. Mixed formats
    instead flow through to ``_measure``, which infers the schema from rows when not every file
    declared one.

    An unreadable file (or a format with no registered reader) is isolated: it is named on a
    :class:`FileError` the envelope collects, contributes no rows, and flips ``scanned_all`` off — it
    never aborts the profile. Files that read cleanly are counted, not listed.
    """
    partition_rows: list[dict] = []
    arrow_schemas: list[pa.Schema] = []
    all_declared = True  # every file that contributed rows carried a declared schema
    rows_scanned = 0
    files_read = 0
    rows_present: int | None = 0
    partition_scanned = True
    row_cap = _per_file_cap(row_budget, len(entries))
    file_errors: list[FileError] = []
    file_formats: set[str] = set()
    split_profiles: list[SplitProfile] = []
    for split in resolve_splits(entries):
        split_examples = 0
        split_counts_known = True  # every file's exact total row count is known (footer or full scan)
        split_scanned = True  # every row of every file was actually parsed
        for entry in split.entries:
            file_formats.add(_format_of(entry.path))
            error: str | None = None
            try:
                result = get_reader(_format_of(entry.path)).read(source, entry, row_cap=row_cap)
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
            if error is not None:
                file_errors.append(FileError(path=entry.path, error=error))
            rows_present = _add_known(rows_present, num_rows)
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
                num_files=len(split.entries),
                # From the listing, not from reading, so a file that failed mid-read still weighs
                # what it weighs — unlike `num_examples`, this never goes unknown.
                size_bytes=sum(entry.size_bytes for entry in split.entries),
                num_examples=split_examples if split_counts_known else None,
            )
        )
    features, stats, classification = _measure(
        partition_rows, arrow_schemas, all_declared=all_declared, column_roles=column_roles
    )
    partition = PartitionProfile(
        name=name,
        # Observed, not chosen: the partition reports the formats its files turned out to be in
        # rather than picking one and splitting to keep that true.
        file_formats=sorted(file_formats),
        splits=split_profiles,
        features=features,
        stats=stats,
        # Scoped to this partition, which is where it was decided all along: `partition_scanned` is
        # the value that already gated whether `categorical.values` could quote a proven enumeration.
        stats_complete=partition_scanned,
        classification=classification,
    )
    return _PartitionOutcome(
        partition=partition,
        rows_scanned=rows_scanned,
        files_read=files_read,
        rows_present=rows_present,
        file_errors=file_errors,
    )
