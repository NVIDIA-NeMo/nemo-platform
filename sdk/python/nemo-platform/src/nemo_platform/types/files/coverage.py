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

__all__ = ["Coverage"]


class Coverage(BaseModel):
    """
    How much of the data the profile is based on, stated as numbers rather than as a verdict.

    It carries no ``exhaustive`` flag. That bit answered two questions at once -- whether a given
    measurement is a fact or an estimate, which each measurement now states for itself, and whether
    all the data was seen, which needs numerators and denominators. It also folded together causes
    that call for different people to act: a short read is the caller's choice, a corrupt shard is
    the data owner's problem, a missing reader is ours.

    The dataset-wide question is one expression away, and still says which half failed::

        all(p.rows_complete for p in profile.partitions) and not profile.file_errors
    """

    files_present: int
    """
    Data files the fileset holds, whether or not this run could read them -- the
    denominator `files_read` is a fraction of. Counts files in formats with no
    reader too, since those are data the profile does not describe. Non-data files
    (a README, a LICENSE) are counted nowhere.
    """

    files_read: int
    """Files the profiler opened and did not fail on.

    This counts a file it opened and took no rows from, which a zero `row_budget`
    makes every file. A count, not a list: the paths worth naming are the ones that
    failed, and those are on `file_errors`.
    """

    rows_scanned: int
    """Total rows actually parsed across all files."""

    bytes_present: Optional[int] = None
    """
    On-disk bytes of every data file the fileset holds, whether or not this run
    could read it -- the size of the dataset as it sits, independent of how much was
    profiled. Equal to the sum over `SplitProfile.size_bytes` when nothing failed,
    and load-bearing when something did: a file in a format with no reader never
    reaches a partition.
    """

    rows_present: Optional[int] = None
    """
    How many rows the fileset holds, scanned or not -- the denominator
    `rows_scanned` is a fraction of. None once any file's count is unknown, since a
    total that omits it would read low as though it were a fact.
    """
