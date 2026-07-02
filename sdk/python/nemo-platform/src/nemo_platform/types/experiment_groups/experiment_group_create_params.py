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

from typing import Dict, Iterable
from typing_extensions import Required, TypedDict

from .sort_criterion_param import SortCriterionParam

__all__ = ["ExperimentGroupCreateParams"]


class ExperimentGroupCreateParams(TypedDict, total=False):
    workspace: str

    name: Required[str]
    """Workspace-unique group name."""

    default_sort: Iterable[SortCriterionParam]
    """
    Ordered default sort (priority order; first is primary, rest are tiebreakers)
    for this group's experiments list. Each field must be a numeric rollup metric:
    run_count, cost_usd.<stat>, latency_ms.<stat>, or evaluators.<name>.<stat>.
    """

    description: str
    """Human-readable purpose of the group."""

    insight_id: str
    """Reference to an external insight that seeded this group, if any."""

    metadata: Dict[str, object]
    """Free-form producer metadata for the group."""

    summary: str
    """Human- or agent-authored summary of the group's findings."""
