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

from typing_extensions import TypedDict

from .experiment_filter_param import ExperimentFilterParam

__all__ = ["ExperimentListParams"]


class ExperimentListParams(TypedDict, total=False):
    workspace: str

    filter: ExperimentFilterParam
    """
    Filter experiments by name, experiment_group_id, dataset_name, dataset_version,
    created_by, created_at, or updated_at. Pass is_deleted=true to return only
    soft-deleted experiments; omit to see only live ones. Pass is_pinned=true (or
    false) to filter by pinned state; omit to return both. Filter by a rollup metric
    with numeric range operators ($gte/$lte/$gt/$lt/$eq): filter[run_count][$gte]=5,
    filter[cost_usd.mean][$lte]=0.5, filter[latency_ms.p95][$lte]=1000, or
    filter[evaluators.<name>.mean][$gte]=0.8.
    """

    page: int
    """Page number."""

    page_size: int
    """Page size."""

    sort: str
    """Field to sort by; prefix with '-' for descending.

    Sort by an experiment attribute (name, created_at, updated_at, pinned_at) or by
    an aggregate metric: run_count, cost_usd.<stat>, latency_ms.<stat>, or
    evaluators.<name>.<stat>, where <stat> is one of mean, median, p90, p95, p99,
    sum, count.
    """
