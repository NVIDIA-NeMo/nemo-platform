# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The top-level profiling pipeline.

``profile(source)`` lists the files behind a :class:`FileSource`, groups them into partitions and
splits, reads them, and assembles a ``DatasetProfile``. This stage produces the structural envelope
— partitions, splits, FileRecords, content digest, sampling metadata — the derived row schema
(``features``), and per-column ``stats``. Classification is added by a later stage; until then each
partition carries an ``unknown`` classification.

Reads are exhaustive (every row of every file). Sampling large datasets with bounded probes is a
later, drop-in optimization behind the same reader seam.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nemo_platform_plugin.files.dataset_profile import (
    DatasetProfile,
    FileRecord,
    PartitionClassification,
    PartitionProfile,
    SamplingInfo,
    SplitProfile,
)

from nemo_datasets_plugin.profiler.digest import content_digest
from nemo_datasets_plugin.profiler.file_source import FileSource
from nemo_datasets_plugin.profiler.partition import group_partitions
from nemo_datasets_plugin.profiler.readers import detect_format, get_reader
from nemo_datasets_plugin.profiler.schema import derive_features
from nemo_datasets_plugin.profiler.splits import resolve_splits
from nemo_datasets_plugin.profiler.stats import derive_stats

PROFILER_NAME = "nemo-dataset-profiler"
PROFILER_VERSION = "0.1.0"


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
    all_exact = True

    for partition_name, partition_entries in group_partitions(data_entries):
        partition_rows: list[dict] = []
        arrow_schema = None
        partition_exact = True
        split_profiles: list[SplitProfile] = []
        for split in resolve_splits(partition_entries):
            file_records: list[FileRecord] = []
            split_examples = 0
            split_exact = True
            for entry in split.entries:
                reader = get_reader(detect_format(entry.path))
                try:
                    result = reader.read(source, entry)
                except Exception:
                    # Failure isolation: keep the file's identity, skip its rows, keep going.
                    result = None
                if result is None:
                    num_rows = None
                else:
                    num_rows = result.num_rows
                    rows_scanned += result.rows_scanned
                    partition_rows.extend(result.rows)
                    if arrow_schema is None:
                        arrow_schema = result.arrow_schema
                file_records.append(
                    FileRecord(
                        path=entry.path,
                        size_bytes=entry.size_bytes,
                        checksum=entry.checksum,
                        num_rows=num_rows,
                    )
                )
                if num_rows is None:
                    split_exact = False
                else:
                    split_examples += num_rows
            all_exact = all_exact and split_exact
            partition_exact = partition_exact and split_exact
            split_profiles.append(
                SplitProfile(
                    name=split.name,
                    canonical=split.canonical,
                    files=file_records,
                    num_examples=split_examples if split_exact else None,
                )
            )
        features = derive_features(partition_rows, arrow_schema)
        partitions.append(
            PartitionProfile(
                name=partition_name,
                file_format=detect_format(partition_entries[0].path),
                splits=split_profiles,
                features=features,
                stats=derive_stats(features, partition_rows, exhaustive=partition_exact),
                classification=PartitionClassification(dataset_type="unknown"),
            )
        )

    sampling = SamplingInfo(
        exhaustive=all_exact,
        strategy="full",
        rows_scanned=rows_scanned,
        rows_total=rows_scanned if all_exact else None,
        files_scanned=len(data_entries),
        per_file_row_cap=None,
        seed=None,
    )
    return DatasetProfile(
        content_digest=content_digest(all_entries),
        created_at=created_at,
        profiler_info={"name": PROFILER_NAME, "version": PROFILER_VERSION},
        sampling=sampling,
        partitions=partitions,
    )
