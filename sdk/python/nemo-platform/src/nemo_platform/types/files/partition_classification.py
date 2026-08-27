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

from typing import List, Optional

from .evidence import Evidence
from ..._models import BaseModel
from .verifiability import Verifiability

__all__ = ["PartitionClassification"]


class PartitionClassification(BaseModel):
    """
    What the data *is*, described objectively — the stored basis a downstream reader uses to decide
    which tasks the dataset can train.

    Holds the partition-level findings only: column-level semantics are the ``semantic_role`` markers
    on the feature nodes they describe, but the evidence for *why* they were assigned is recorded here.
    """

    candidates: Optional[List[str]] = None
    """
    Every dataset type the assigned roles satisfy (prompt_completion,
    preference_pair, ...), most specific first. `candidates[0]` is the best single
    answer and the tail is structures the same columns also satisfy: prompt +
    completion + score + label is genuinely both `scored_response` and
    `unpaired_preference`, and a consumer that cares picks by its own rule rather
    than by ours. EMPTY means the roles matched no known structure, which is also
    what a partition that could not be classified at all reports; the two are not
    distinguishable from this model alone, because an `error` evidence entry is also
    how a partition that classified fine reports a degradation along the way -- a
    column cap, a column whose measurement failed, a probe that could not run. A
    SUMMARY either way: the `semantic_role` markers are what a consumer should match
    on.
    """

    evidence: Optional[List[Evidence]] = None
    """
    Why the type / roles / axes were assigned: one flat list, detail strings
    self-describe what they support. A profile-time snapshot; unrecoverable once the
    data or profiler version move.
    """

    format: Optional[str] = None
    """standard | conversational | mixed"""

    modality: Optional[str] = None
    """text | image_text | audio_text | ..."""

    prompt_form: Optional[str] = None
    """explicit | implicit | n/a"""

    verifiability: Optional[Verifiability] = None
    """A found verification target.

    Present only when one exists; absence _is_ the claim (not verifiable).
    """
