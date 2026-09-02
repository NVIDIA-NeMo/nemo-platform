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

from typing import Optional
from typing_extensions import Literal

from ..._models import BaseModel

__all__ = ["FilesetProfileResponse"]


class FilesetProfileResponse(BaseModel):
    """The stored profile plus the status of profiling for this fileset."""

    state: Literal["ready", "running", "paused", "cancelled", "failed", "absent"]
    """
    ready (a profile exists) | running (a job is in flight) | paused (a job exists
    but is suspended and will produce nothing until resumed) | cancelled (the last
    job was stopped deliberately and no profile exists; just re-run) | failed (the
    last job errored and no profile exists; worth investigating) | absent (never
    profiled). `cancelled` is kept apart from `failed` because nothing is broken and
    the remedy differs; callers that do not care can treat the two alike. There is
    no `stale`: a profile carries no content digest to check a fresh listing
    against, so a profile that exists always reads `ready` and describes the fileset
    as of its `created_at`.
    """

    job_name: Optional[str] = None
    """
    Name of the profiling job behind the state: the in-flight job when running or
    paused, and the job that ended when cancelled or failed.
    """

    profile: Optional["DatasetProfile"] = None
    """The machine-owned dataset profile -- the root of the stored contract.

    It carries no staleness marker, and no per-file manifest to reconstruct one
    from. A stored digest would freeze "which files count as inputs" into the data
    at write time, and that judgment moves: once card front-matter drives split
    declaration, `README.md` becomes an input, and changing the rule would
    invalidate every stored profile at once.

    So a profile says when it was made and nothing about whether it still holds.
    When something does consume freshness, the cheap primitive is a fileset version
    token from the storage backend.
    """


from .dataset_profile import DatasetProfile
