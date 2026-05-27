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
from typing_extensions import Required, TypedDict

from ..evaluation_context_param import EvaluationContextParam
from ..flexible_entry_request_param import FlexibleEntryRequestParam
from ..flexible_entry_response_param import FlexibleEntryResponseParam

__all__ = ["ChatCompletionCreateParams"]


class ChatCompletionCreateParams(TypedDict, total=False):
    workspace: str

    request: Required[FlexibleEntryRequestParam]
    """Flexible entry request that accepts any object shape.

    This flexibility enables the Intake service to store requests from various LLM
    providers (OpenAI, Anthropic, NIM, etc.) and future model types (embeddings,
    multimodal, etc.) without requiring schema updates.

    Required fields: `messages` and `model` Common optional fields: `temperature`,
    `max_tokens`, `top_p`, `tools`, `tool_choice`, `stream`, `response_format`, etc.
    """

    response: Required[FlexibleEntryResponseParam]
    """Flexible entry response that accepts any object shape.

    This flexibility enables the Intake service to store responses from various LLM
    providers and future model types without requiring schema updates.

    Required: either `choices` (successful response) or `error` (failed call).
    Common optional fields: `id`, `created`, `model`, `usage`, `system_fingerprint`,
    etc.
    """

    cost_details: Dict[str, float]
    """Additional estimated cost breakdown fields in USD."""

    cost_input_usd: float
    """Estimated input-token cost of this model call in USD."""

    cost_output_usd: float
    """Estimated output-token cost of this model call in USD."""

    cost_usd: float
    """Total estimated cost of this model call in USD.

    This matches ATIF step metrics; Intake stores it as semantic cost_total_usd on
    spans.
    """

    evaluation_context: EvaluationContextParam

    provider: str

    session_id: str
    """Groups related chat-completions calls without forcing them into the same trace."""

    trace_id: str
    """Opt into joining an existing trace built via OTel or ATIF.

    This is not a grouping mechanism for chat-completions calls; use session_id to
    group related calls.
    """
