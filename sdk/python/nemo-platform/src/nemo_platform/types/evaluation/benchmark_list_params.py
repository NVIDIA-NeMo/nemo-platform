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
from typing_extensions import Literal, TypedDict

from .fileset_ref import FilesetRef
from ..shared_params.datetime_filter import DatetimeFilter

__all__ = ["BenchmarkListParams", "Filter"]


class BenchmarkListParams(TypedDict, total=False):
    workspace: str

    extended_response: bool
    """Whether to return the extended benchmark."""

    filter: Filter
    """Filter benchmarks by name, description, dataset, project, and dates.

    Supports JSON filter syntax with operators: $eq, $like, $lt, $lte, $gt, $gte,
    $in, $nin, $and, $or, $not. Also supports text filter syntax.
    """

    page: int
    """Page number."""

    page_size: int
    """Page size."""

    sort: Literal["-created_at", "created_at", "-updated_at", "updated_at", "-name", "name"]
    """The field to sort by.

    To sort in decreasing order, use `-` in front of the field name.
    """


class Filter(TypedDict, total=False):
    """Filter benchmarks by name, description, dataset, project, and dates.

    Supports JSON filter syntax with operators: $eq, $like, $lt, $lte, $gt, $gte, $in, $nin, $and, $or, $not. Also supports text filter syntax.
    """

    created_at: DatetimeFilter
    """Filter benchmarks by creation date range."""

    dataset: FilesetRef
    """Reference to a Fileset in the Files API.

    A reference is a string with format 'workspace/fileset-name' that points to a
    persisted fileset entity. When used as a dataset source, all files within the
    fileset will be downloaded to the job container.

    See [Entity references](docs/get-started/concepts/entity-references.md) for the
    general entity reference pattern used across the platform.
    """

    description: str
    """Filter benchmarks by description."""

    labels: Dict[str, str]
    """Filter by labels.

    Address an individual label as a sub-path, e.g.
    filter[labels.eval_category]=agentic.
    """

    name: str
    """Filter benchmarks by name."""

    project: str
    """Filter benchmarks by project name."""

    updated_at: DatetimeFilter
    """Filter benchmarks by last update date range."""
