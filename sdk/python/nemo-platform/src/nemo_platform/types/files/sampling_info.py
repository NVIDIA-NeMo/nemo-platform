# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing import Optional

from ..._models import BaseModel

__all__ = ["SamplingInfo"]


class SamplingInfo(BaseModel):
    """How much of the data the profile is based on — coverage, stated as numbers.

    Deliberately carries no ``exhaustive`` flag. That bit was answering two questions at once: "are
    these measurements facts or estimates?", which is a property of each measurement and is now
    stated by each of them, and "did I see all the data?", which is this block's job and needs
    numerators and denominators rather than a boolean. It also folded together causes that call for
    different people to act — a short read is the caller's choice, a corrupt shard is the data
    owner's problem, and a missing reader is ours.

    Nor does it record the caller's row limit. Reading everything is now the default and costs what
    reading some of it costs, so a short read is unusual — and when it happens ``rows_scanned``
    against ``rows_present`` already says so. *Why* is not the profile's business: a limit is an
    input, and the only other cause is a file that failed, which is named on ``file_errors``.

    The dataset-wide question is still one expression away, and still says which half failed::

        all(p.rows_complete for p in profile.partitions) and not profile.file_errors
    """

    files_present: int
    """
    Data files the fileset holds, whether or not this run could read them — the
    denominator `files_read` is a fraction of. Includes files in formats with no
    reader, since those are data that went unprofiled (they are named on
    `DatasetProfile.file_errors`). A README is not data and is counted nowhere.
    Every readable file should be opened, since head-sampling a _subset of files_
    hides columns that appear only in later shards, so expect these two to match
    until scale forces file-level sampling.
    """

    files_read: int
    """Files actually opened and read from.

    A count, not a list -- the paths of healthy shards are the one part of a profile
    that grows without bound and informs no decision; `SplitProfile.num_files`
    counts them per split, and only the ones that went wrong are named, on
    `DatasetProfile.file_errors`.
    """

    rows_scanned: int
    """Total rows actually parsed across all files."""

    bytes_present: Optional[int] = None
    """
    On-disk bytes of every data file the fileset holds, whether or not this run
    could read it — the size of the dataset as it sits, independent of how much was
    profiled. Redundant with the sum over `SplitProfile.size_bytes` exactly when
    nothing failed, and load-bearing when something did: a file in a format with no
    reader never reaches a partition, so a directory of .csv shards beside one
    .parquet would otherwise weigh in at the parquet alone. Same reason
    `files_present` is kept alongside the per-split counts — a denominator stops
    being derivable the moment coverage is partial, which is the only time it is
    read.
    """

    rows_present: Optional[int] = None
    """
    How many rows the fileset holds, scanned or not — the denominator `rows_scanned`
    is a fraction of. Populated whenever every file's count is _known_, regardless
    of how much was read: a row-capped run over parquet still knows its totals from
    the footers, and that is exactly when the ratio carries information. None means
    at least one file's count is unknown — never zero, never an estimate.
    """
