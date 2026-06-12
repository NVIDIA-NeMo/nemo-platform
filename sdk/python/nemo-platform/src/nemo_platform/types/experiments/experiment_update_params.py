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
from typing_extensions import Required, Annotated, TypedDict

from ..._utils import PropertyInfo

__all__ = ["ExperimentUpdateParams"]


class ExperimentUpdateParams(TypedDict, total=False):
    workspace: str

    agent_name: Required[str]
    """Name of the agent under test."""

    agent_version: Required[str]
    """Version of the agent under test."""

    dataset_name: Required[str]
    """Producer-supplied dataset name."""

    experiment_group_id: Required[str]
    """Entity id of the owning ExperimentGroup.

    Required — the group must already exist.
    """

    body_name: Required[Annotated[str, PropertyInfo(alias="name")]]
    """Producer-supplied, workspace-unique experiment id."""

    dataset_version: str
    """Producer-supplied dataset version."""

    description: str
    """Human-readable description."""

    metadata: Dict[str, object]
    """Free-form producer metadata."""

    source_link: str
    """Optional URL for the source experiment."""

    summary: str
    """Human-authored summary of results."""
