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

from typing import Dict
from typing_extensions import TypedDict

from .number_filter_param import NumberFilterParam
from ..shared_params.datetime_filter import DatetimeFilter

__all__ = ["ExperimentFilterParam"]


class ExperimentFilterParam(TypedDict, total=False):
    """Filter for listing Experiments."""

    cost_usd: Dict[str, NumberFilterParam]
    """Filter by a cost_usd rollup stat, e.g. filter[cost_usd.mean][$lte]=0.5."""

    created_at: DatetimeFilter
    """
    Filter experiments by creation timestamp; supports `$gte` and `$lte` for ranges.
    """

    created_by: str
    """Filter experiments by the principal that created them."""

    dataset_name: str
    """Filter experiments by dataset name."""

    dataset_version: str
    """Filter experiments by dataset version."""

    evaluators: Dict[str, Dict[str, NumberFilterParam]]
    """Filter by an evaluator rollup stat, e.g.

    filter[evaluators.<name>.mean][$gte]=0.8.
    """

    experiment_group_id: str
    """Filter experiments by owning group id."""

    is_deleted: bool
    """When true, returns only soft-deleted experiments.

    Omit (or false) to see only live experiments.
    """

    is_pinned: bool
    """When true, returns only pinned experiments.

    When false, returns only unpinned experiments. Omit to return both.
    """

    latency_ms: Dict[str, NumberFilterParam]
    """Filter by a latency_ms rollup stat, e.g. filter[latency_ms.p95][$lte]=1000."""

    name: str
    """Filter experiments by name."""

    run_count: NumberFilterParam
    """Filter by run count, e.g. filter[run_count][$gte]=5."""

    updated_at: DatetimeFilter
    """
    Filter experiments by last-updated timestamp; supports `$gte` and `$lte` for
    ranges.
    """
