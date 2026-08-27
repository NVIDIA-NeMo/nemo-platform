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

from __future__ import annotations

from typing import Dict, List, Optional
from datetime import datetime
from typing_extensions import Literal

from .coverage import Coverage
from ..._models import BaseModel
from .file_error import FileError

__all__ = ["DatasetProfile"]


class DatasetProfile(BaseModel):
    """The machine-owned dataset profile -- the root of the stored contract.

    It carries no staleness marker, and no per-file manifest to reconstruct one from. A stored digest
    would freeze "which files count as inputs" into the data at write time, and that judgment moves:
    once card front-matter drives split declaration, ``README.md`` becomes an input, and changing the
    rule would invalidate every stored profile at once.

    So a profile says when it was made and nothing about whether it still holds. When something does
    consume freshness, the cheap primitive is a fileset version token from the storage backend.
    """

    coverage: Coverage
    """
    How much of the data the profile is based on, stated as numbers rather than as a
    verdict.

    It carries no `exhaustive` flag. That bit answered two questions at once --
    whether a given measurement is a fact or an estimate, which each measurement now
    states for itself, and whether all the data was seen, which needs numerators and
    denominators. It also folded together causes that call for different people to
    act: a short read is the caller's choice, a corrupt shard is the data owner's
    problem, a missing reader is ours.

    The dataset-wide question is one expression away, and still says which half
    failed::

        all(p.rows_complete for p in profile.partitions) and not profile.file_errors
    """

    created_at: datetime

    partitions: List["PartitionProfile"]
    """
    Single partition in the common homogeneous case; there is no fileset-level
    rollup.
    """

    file_errors: Optional[List[FileError]] = None
    """
    Every file the profiler could not fully use, from anywhere in the fileset,
    sorted by path. Files that read cleanly are counted rather than listed, so this
    is a findings list and not a manifest. A non-empty list does NOT by itself make
    `rows_present` unknown: a file that failed part-way through the data keeps the
    exact count its footer already declared. What unknows the total is a file whose
    count could not be established at all -- one with no registered reader, or a
    line-delimited file whose read fell short of its end.
    """

    kind: Optional[Literal["dataset"]] = None
    """What this profile describes.

    Pinned rather than an open vocabulary, unlike the value vocabularies above: a
    discriminator has to be exact, and a `DatasetProfile` whose kind says anything
    else is malformed, not forward-compatible. Today `dataset` is the only member,
    so a consumer sees `DatasetProfile` directly; when a second profiler lands, the
    stored and returned type widens to a discriminated union and this is what tells
    them apart. It carries a default, so profiles written before it existed validate
    cleanly — which is precisely why it is cheap to add now and expensive to add
    once a union is in the wire format.
    """

    profile_schema_version: Optional[str] = None
    """Semver of THIS contract (e.g. "1.0") — gates consumer compatibility."""

    profiler_info: Optional[Dict[str, object]] = None
    """Free-form profiler metadata (name, version, git sha, timings)."""


from .partition_profile import PartitionProfile
