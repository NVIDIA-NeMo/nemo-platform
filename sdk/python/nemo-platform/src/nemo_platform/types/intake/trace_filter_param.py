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

from .span_status import SpanStatus
from ..shared_params.datetime_filter import DatetimeFilter

__all__ = ["TraceFilterParam"]


class TraceFilterParam(TypedDict, total=False):
    id: str
    """Filter by canonical Intake trace id."""

    dataset_id: str
    """Filter by root-span dataset id."""

    dataset_name: str
    """Filter by root-span dataset name."""

    dataset_version: str
    """Filter by root-span dataset version."""

    evaluation_id: str
    """Filter by root-span evaluation id."""

    evaluation_run_id: str
    """Filter by root-span evaluation run id."""

    evaluation_sha: str
    """Filter by root-span evaluation sha."""

    session_id: str
    """Filter by session id."""

    started_at: DatetimeFilter
    """Filter by root span start timestamp."""

    status: SpanStatus
    """Filter by rolled-up trace status."""

    test_case_id: str
    """Filter by root-span dataset test case id."""
