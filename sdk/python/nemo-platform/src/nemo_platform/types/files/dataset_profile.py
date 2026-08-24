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

from ..._models import BaseModel
from .file_error import FileError
from .sampling_info import SamplingInfo

__all__ = ["DatasetProfile"]


class DatasetProfile(BaseModel):
    """The machine-owned dataset profile — the root of the stored contract.

    Deliberately carries no staleness marker, and no per-file manifest to reconstruct one from. A
    stored digest would freeze "which files count as inputs" into the data at write time, and that
    judgment moves: once card front-matter drives split declaration, ``README.md`` becomes an input.
    Changing the rule would then invalidate every stored profile at once, with no way to tell a real
    change from a definition change.

    So a profile says when it was made and nothing about whether it still holds. ``created_at`` is
    the whole of it. That is deliberate while profiling is user-triggered and nothing consumes
    freshness; when something does, the cheap primitive is a fileset version token from the storage
    backend, which costs no listing and freezes no policy — not a manifest reconstructed here.
    """

    created_at: datetime

    partitions: List["PartitionProfile"]
    """
    Single partition in the common homogeneous case; there is no fileset-level
    rollup.
    """

    sampling: SamplingInfo
    """How much of the data the profile is based on — coverage, stated as numbers.

    Deliberately carries no `exhaustive` flag. That bit was answering two questions
    at once: "are these measurements facts or estimates?", which is a property of
    each measurement and is now stated by each of them, and "did I see all the
    data?", which is this block's job and needs numerators and denominators rather
    than a boolean. It also folded together causes that call for different people to
    act — a short read is the caller's choice, a corrupt shard is the data owner's
    problem, and a missing reader is ours.

    Nor does it record the caller's row limit. Reading everything is now the default
    and costs what reading some of it costs, so a short read is unusual — and when
    it happens `rows_scanned` against `rows_present` already says so. _Why_ is not
    the profile's business: a limit is an input, and the only other cause is a file
    that failed, which is named on `file_errors`.

    The dataset-wide question is still one expression away, and still says which
    half failed::

        all(p.rows_complete for p in profile.partitions) and not profile.file_errors
    """

    file_errors: Optional[List[FileError]] = None
    """
    Every file the profiler could not fully use, from anywhere in the fileset: a
    format with no reader, a corrupt shard, a partially parsed one. Reporting them
    is what keeps a directory of .csv shards from profiling as an exhaustively
    scanned _empty_ dataset, indistinguishable from one that really is empty. One
    list rather than two, because "a file I could not use" is the same finding
    whether or not a partition managed to group it first, and a reader asking "did
    anything go wrong?" should not have to look twice.
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
