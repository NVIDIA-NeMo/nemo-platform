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

    dataset_type: str
    """Dataset-type vocabulary (prompt_completion, preference_pair, ...).

    A SUMMARY, not the basis for a decision — it is the most specific single
    structure the roles satisfy, and a dataset routinely satisfies several. The
    `semantic_role` markers are what a consumer should match on; `candidates` lists
    everything this one is a projection of.
    """

    candidates: Optional[List[str]] = None
    """
    Every dataset type the assigned roles satisfy, most specific first, so
    `candidates[0] == dataset_type`. prompt + completion + score + label is
    genuinely both scored_response and unpaired_preference; reporting only the first
    made rule order an invisible tie-break and hid that the data supports more than
    one use. Deliberately not a capability list ("supports DPO") — trainer
    requirements shift and differ per framework, so that mapping belongs in the
    consumer, computed from the roles.
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
