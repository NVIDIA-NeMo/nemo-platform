# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The top-level profiling pipeline.

``profile(source)`` lists the files behind a :class:`FileSource`, groups them into partitions and
splits, reads them, and assembles a ``DatasetProfile``: the structural envelope (partitions, splits
with their counts and sizes, the files it could not use, the coverage figures) plus the derived row
schema (``features``), per-column ``stats``, and the full ``classification``.

Every file is opened, since sampling a subset of files would hide columns that appear only in later
shards. Every partition is **folded**: batches are measured and let go, and nothing kept grows with
the file, so an exhaustive read costs what a short one costs. ``row_budget`` survives only as a way
to ask for a shorter run.

A declared schema does not change the mechanism, only what is known when. Parquet footers are read
first, so the columns are named and typed before a row is parsed; line-delimited data declares
neither, so columns are discovered as they appear and typed once the last row has gone by."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

import pyarrow as pa
from nemo_datasets_plugin.profiler.classify import PrefixPairFold, classify
from nemo_datasets_plugin.profiler.file_source import FileEntry, FileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.readers.base import (
    FilePreview,
    detect_format,
    get_reader,
    is_unsupported_data,
)
from nemo_datasets_plugin.profiler.schema import MAX_COLUMNS, columns_were_capped, derive_features
from nemo_datasets_plugin.profiler.splits import infer_data_files, resolve_splits
from nemo_datasets_plugin.profiler.stats import RowFold, quote_enumerations
from nemo_platform_plugin.files.dataset_profile import (
    ColumnStats,
    Coverage,
    DatasetProfile,
    Evidence,
    FeatureSchema,
    FileError,
    PartitionClassification,
    PartitionProfile,
    SplitProfile,
)

PROFILER_NAME = "nemo-dataset-profiler"
PROFILER_VERSION = "0.1.0"

# Read everything. Nothing is materialised, so an exhaustive read costs what a short one costs.
DEFAULT_ROW_BUDGET = None

# Rows read from a file however thin a caller-supplied budget gets. Below this a file cannot
# contribute the columns it alone witnesses, which is why every file is opened rather than a subset
# sampled. It makes a budget a target rather than a ceiling: 10,000 shards read this many each.
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

    ``row_budget`` bounds how many rows each *partition* reads in total, divided across its files.
    It defaults to ``None``, which reads every row: memory is flat in rows either way, so a budget
    buys only a shorter run. Files smaller than their share are read to the end.

    ``column_roles`` maps a column name to a role the caller is asserting, for datasets whose column
    names the role table does not recognize. Hints take precedence over name detection but still
    have to pass the dtype gates, and a rejected one is reported as evidence rather than dropped.

    ``created_at`` is injectable so a profile can be made reproducible byte-for-byte in tests.
    """
    created_at = created_at or datetime.now(timezone.utc)
    all_entries = source.list_files()
    data_entries = [entry for entry in all_entries if detect_format(entry.path) is not None]
    # Files that hold records but have no reader yet. Reported rather than dropped, or a directory
    # of .csv shards would profile as an exhaustively scanned empty dataset. They get FileErrors at
    # the envelope, since no partition grouped them, and keep their bytes in the fileset size.
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

    # Every path the source listed, data or not. A split's glob is verified against this rather than
    # the partition's own files, so a pattern can never pull in a README sitting beside the shards.
    all_paths = [entry.path for entry in all_entries]

    for name, partition_entries in group_partitions(data_entries):
        outcome = _profile_partition(
            source, name, partition_entries, row_budget, column_roles or {}, all_paths=all_paths
        )
        partitions.append(outcome.partition)
        rows_scanned += outcome.rows_scanned
        files_read += outcome.files_read
        rows_present = _add_known(rows_present, outcome.rows_present)
        file_errors.extend(outcome.file_errors)

    # A file the profiler could not use holds an unknown number of rows, so it makes the fileset
    # total unknown — whether it was skipped for want of a reader or failed mid-read.
    if file_errors:
        rows_present = None

    coverage = Coverage(
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
    )
    return DatasetProfile(
        created_at=created_at,
        profiler_info={"name": PROFILER_NAME, "version": PROFILER_VERSION},
        coverage=coverage,
        partitions=partitions,
        # Sorted so a reader scanning for trouble sees it in a stable order, whatever partition it
        # came from; partitions contribute theirs as they are profiled.
        file_errors=sorted(file_errors, key=lambda error: error.path),
    )


def _per_file_cap(row_budget: int | None, file_count: int) -> int | None:
    """Split a partition's row budget across its files.

    Bounded below by :data:`MIN_ROWS_PER_FILE`, which makes the budget a target rather than a
    ceiling: at ten thousand shards the arithmetic share is one row, too thin to witness a column.
    Overshooting there beats sampling a subset of files and hiding columns that appear only in later
    shards.
    """
    if row_budget is None:
        return None
    if file_count <= 1:
        return row_budget
    return max(MIN_ROWS_PER_FILE, row_budget // file_count)


def _add_known(total: int | None, addend: int | None) -> int | None:
    """Sum two counts, where ``None`` means unknown and poisons the total.

    A fileset whose count is unknown for even one file has an unknown total; reporting the sum of
    the rest would look like a fact and read low.
    """
    if total is None or addend is None:
        return None
    return total + addend


def _unify_schemas(schemas: list[pa.Schema]) -> pa.Schema | None:
    """One schema describing every file of the partition, or None when they cannot be reconciled.

    Taking the first file's schema would make the profile depend on which shard sorts first: a column
    appearing only in a later shard would vanish from ``features``, and the same data would classify
    differently under a different file order.

    A genuine type conflict for one column name has no correct answer here, so this returns None and
    the caller infers from the rows instead, widening the conflicting column to ``json``.
    """
    if not schemas:
        return None
    if len(schemas) == 1:
        return schemas[0]
    try:
        return pa.unify_schemas(schemas)
    except pa.ArrowException:
        return None


@dataclass(frozen=True)
class _PartitionOutcome:
    """One partition plus what it contributes to the dataset-level coverage envelope."""

    partition: PartitionProfile
    rows_scanned: int
    files_read: int  # files actually opened and read, so `files_read` can exclude failures
    rows_present: int | None  # rows known to exist here, or None once any file's count is unknown
    file_errors: list[FileError]  # files this partition grouped but could not fully read


def _capped_columns_evidence(features: list[FeatureSchema]) -> list[Evidence]:
    """Say so when the schema stopped at the cap rather than at the end of the data.

    A profile describing 4,096 of a file's columns as though they were all of them is worse than one
    that failed, since the reader cannot tell a wide table from a broken one.
    """
    if not columns_were_capped(features):
        return []
    return [
        Evidence(
            kind="error",
            detail=(
                f"stopped at {MAX_COLUMNS} columns; the rest of this partition's schema was not "
                f"described. A file whose rows carry unique keys will do this."
            ),
        )
    ]


def _peek_files(source: FileSource, entries: list[FileEntry]) -> dict[str, FilePreview]:
    """What each file declares about itself, before any of them is read.

    A failure here is not reported: it surfaces as a :class:`FileError` with a reason when the file
    is read, and reporting it twice would double-count. All this decides is what the partition knows
    before it starts.
    """
    previews: dict[str, FilePreview] = {}
    for entry in entries:
        try:
            previews[entry.path] = get_reader(_format_of(entry.path)).peek(source, entry)
        except Exception:
            previews[entry.path] = FilePreview()
    return previews


class _PartitionFolds:
    """The two folds a partition needs, driven together over the same batches.

    One is per column; the other compares two columns of a row against each other and so belongs to
    neither. Keeping them side by side is what lets the file loop hand over a batch and forget it.
    """

    def __init__(self, features: list[FeatureSchema] | None) -> None:
        # None means the partition declared no schema, which the fold reads as "discover the columns
        # as they appear". Either way the fold that measured them reports them, so there is one copy
        # of the schema rather than two that can drift.
        self._columns = RowFold(features)
        self._prefix = PrefixPairFold()
        self._prefix_error: Evidence | None = None

    def update(self, rows: list[dict]) -> None:
        self._columns.update(rows)
        # Guarded like the columns are. Unguarded, only the per-file handler would catch it, and it
        # would report odd *data* as a bad *file*.
        if self._prefix_error is None:
            try:
                self._prefix.update(rows)
            except Exception as exc:
                self._prefix_error = Evidence(
                    kind="error",
                    detail=f"the chosen/rejected prefix probe could not run: {type(exc).__name__}: {exc}",
                )

    def measure(
        self, column_roles: dict[str, str]
    ) -> tuple[list[FeatureSchema], dict[str, ColumnStats], PartitionClassification]:
        """Schema, stats and classification from what was folded.

        The columns have their own per-column guard inside the fold; this is the wide one, for
        anything structural that no single column owns -- a schema that cannot be resolved,
        a classifier that trips over a shape no detector anticipated.
        """
        try:
            features, measured = self._columns.finalize()
            classification = classify(
                features,
                measured.stats,
                probes=measured.probes,
                prefix_pair=self._prefix.result(),
                column_roles=column_roles,
            )
            quote_enumerations(features, measured.stats, measured.vocabularies)
            classification.evidence.extend(_capped_columns_evidence(features))
            classification.evidence.extend(measured.errors)
            if self._prefix_error is not None:
                classification.evidence.append(self._prefix_error)
            return features, measured.stats, classification
        except Exception as exc:
            detail = f"could not measure this partition: {type(exc).__name__}: {exc}"
            return (
                [],
                {},
                # `candidates` carries `dataset_type` at its head, so it cannot be left empty here:
                # the field is documented as `candidates[0] == dataset_type` and a consumer reading
                # the primary candidate would hit an IndexError on the one path that never classified.
                PartitionClassification(
                    dataset_type="unknown",
                    candidates=["unknown"],
                    evidence=[Evidence(kind="error", detail=detail)],
                ),
            )


def _profile_partition(
    source: FileSource,
    name: str,
    entries: list[FileEntry],
    row_budget: int | None,
    column_roles: dict[str, str],
    *,
    all_paths: list[str],
) -> _PartitionOutcome:
    """Profile one partition -- the files of one source directory, whatever formats they are in.

    The reader is resolved per file rather than per partition, since format is a property of a file
    and a directory holding two of them has a stray file, not a second dataset.

    An unreadable file, or one in a format with no registered reader, is isolated: named on a
    :class:`FileError` the envelope collects, contributing no rows, and flipping ``scanned_all`` off
    without aborting the profile.
    """
    # Footers first. A parquet file declares its schema and exact row count there, so one seek per
    # file establishes the partition's shape.
    previews = _peek_files(source, entries)
    arrow_schemas = [preview.arrow_schema for preview in previews.values() if preview.arrow_schema is not None]
    declared = _unify_schemas(arrow_schemas) if len(arrow_schemas) == len(entries) and arrow_schemas else None
    # Declared or not, the partition folds the same way. A schema names and types the columns before
    # the first batch; without one they are discovered as they appear and typed at the end.
    row_cap = _per_file_cap(row_budget, len(entries))
    folds = _PartitionFolds(derive_features([], declared) if declared is not None else None)
    rows_scanned = 0
    files_read = 0
    rows_present: int | None = 0
    partition_scanned = True
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
            num_rows: int | None = None
            scanned_all = False
            scanned = 0
            try:
                # Inside the guard: resolving the reader can fail too, and a format with no reader
                # registered is a file the profiler could not use like any other.
                reader = get_reader(_format_of(entry.path))
                preview = previews[entry.path]
                read_errors: list[str] = []
                for batch in reader.batches(source, entry, row_cap=row_cap, errors=read_errors):
                    folds.update(batch)
                    scanned += len(batch)
                # A file the reader only partly understood is named, the same as one it could not
                # open at all. Folding it silently would make a corrupt shard look complete.
                error = "; ".join(read_errors) or None
                # A footer knows the count before the read; a line-delimited file only knows it by
                # reaching the end, which a capped read does not do.
                if preview.num_rows is not None:
                    num_rows = preview.num_rows
                elif row_cap is None or scanned < row_cap:
                    num_rows = scanned
                # Exhaustive requires parsing every row. A known count alone is not enough, and a
                # partial read is not exhaustive however many rows it managed to get.
                scanned_all = num_rows is not None and scanned >= num_rows and error is None
            except Exception as exc:
                # Failure isolation: the file keeps its identity, skips its remaining rows, and does
                # not abort the profile. The reason is recorded so a consumer can tell corrupt input
                # from a profiler bug.
                error = f"{type(exc).__name__}: {exc}"
                num_rows = None
                scanned_all = False
            # Counted outside the guard, for what was consumed: a fold cannot give rows back, so a
            # file that failed on its fifth batch still contributed four.
            rows_scanned += scanned
            if scanned or error is None:
                files_read += 1
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
                # Inferred from the same paths the split itself was read off, then verified against
                # the whole listing; None when one pattern cannot express the split exactly.
                data_files=infer_data_files(split.name, split.entries, all_paths),
                num_files=len(split.entries),
                # From the listing, not from reading, so a file that failed mid-read still weighs
                # what it weighs — unlike `num_examples`, this never goes unknown.
                size_bytes=sum(entry.size_bytes for entry in split.entries),
                num_examples=split_examples if split_counts_known else None,
            )
        )
    features, stats, classification = folds.measure(column_roles)
    partition = PartitionProfile(
        name=name,
        # Observed, not chosen: the partition reports the formats its files turned out to be in
        # rather than picking one and splitting to keep that true.
        file_formats=sorted(file_formats),
        splits=split_profiles,
        features=features,
        stats=stats,
        # Scoped to this partition, where it was decided all along: `partition_scanned` already
        # gated whether `categorical.values` could quote a proven enumeration.
        rows_complete=partition_scanned,
        classification=classification,
    )
    return _PartitionOutcome(
        partition=partition,
        rows_scanned=rows_scanned,
        files_read=files_read,
        rows_present=rows_present,
        file_errors=file_errors,
    )
