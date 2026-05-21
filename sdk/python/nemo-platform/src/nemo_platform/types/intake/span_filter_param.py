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

from .span_kind import SpanKind
from .span_status import SpanStatus
from ..shared_params.datetime_filter import DatetimeFilter

__all__ = ["SpanFilterParam"]


class SpanFilterParam(TypedDict, total=False):
    agent_id: str
    """Filter by agent identifier."""

    agent_name: str
    """Filter by agent application name (e.g. 'claude-code', 'codex')."""

    dataset_id: str
    """Filter by dataset id."""

    dataset_name: str
    """Filter by dataset name."""

    dataset_version: str
    """Filter by dataset version."""

    evaluation_id: str
    """Filter by evaluation id."""

    evaluation_run_id: str
    """Filter by evaluation run id.

    ATIF evaluation context is stored on root trajectory spans; use session_id from
    a matched root to fetch the full trace tree.
    """

    evaluation_sha: str
    """Filter by evaluation sha."""

    kind: SpanKind
    """Filter by normalized span kind."""

    model: str
    """Filter by model name."""

    parent_span_id: str
    """Filter by parent span id. Use to fetch direct children of a span."""

    project: str
    """Filter by project name."""

    prompt_name: str
    """Filter by prompt template name."""

    prompt_version: str
    """Filter by prompt template version."""

    provider: str
    """Filter by provider (e.g. 'openai', 'nim', 'anthropic')."""

    session_id: str
    """Filter by span session id."""

    source: str
    """Filter by ingest source (e.g. 'otel', 'atif', 'chat_completions')."""

    started_at: DatetimeFilter
    """Filter by span start timestamp."""

    status: SpanStatus
    """Filter by normalized span status."""

    test_case_id: str
    """Filter by dataset test case id."""

    tool_name: str
    """Filter by tool name."""
