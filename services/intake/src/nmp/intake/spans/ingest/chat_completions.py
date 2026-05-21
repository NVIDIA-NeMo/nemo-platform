# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenAI-compatible chat-completions ingest.

Producers POST a captured chat-completion request + response. Intake stores
one IntakeSpan per response (one model invocation), preserving the raw
request and response payloads verbatim so downstream dataset export does not
need format conversion.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, status
from nmp.intake.entities.values import FlexibleEntryRequest, FlexibleEntryResponse
from nmp.intake.spans.api.dependencies import SpansServiceDep, require_workspace_access
from nmp.intake.spans.domain import IntakeSpan, SpanKind, SpanStatus, TraceBatch
from nmp.intake.spans.ingest.evaluation_context import EvaluationContext
from nmp.intake.spans.span_attribute_bags import SpanAttributeBags
from nmp.intake.spans.span_semantic_attributes import SpanSemanticAttributes
from nmp.intake.spans.storage import json_dumps_preserve, stable_id, utc_now
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(dependencies=[Depends(require_workspace_access)])
API_TAG = "Ingest"

SOURCE_FORMAT = "chat_completions"


class ChatCompletionsIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: FlexibleEntryRequest
    response: FlexibleEntryResponse

    session_id: str | None = Field(
        default=None,
        description="Groups related chat-completions calls without forcing them into the same trace.",
    )
    trace_id: str | None = Field(
        default=None,
        description=(
            "Opt into joining an existing trace built via OTel or ATIF. This is not a grouping mechanism for "
            "chat-completions calls; use session_id to group related calls."
        ),
    )
    evaluation_context: EvaluationContext | None = None
    provider: str | None = None


class ChatCompletionsIngestResponse(BaseModel):
    session_id: str
    span_id: str


@router.post(
    "/v2/workspaces/{workspace}/ingest/chat-completions",
    response_model=ChatCompletionsIngestResponse,
    tags=[API_TAG],
    status_code=status.HTTP_201_CREATED,
)
async def ingest_chat_completion(
    workspace: str,
    body: ChatCompletionsIngestRequest,
    service: SpansServiceDep,
) -> ChatCompletionsIngestResponse:
    ingested_at = utc_now()
    span = _chat_completion_to_span(workspace=workspace, body=body, ingested_at=ingested_at)
    await service.ingest_batch(TraceBatch(spans=[span]))
    return ChatCompletionsIngestResponse(
        session_id=span.session_id,
        span_id=span.external_span_id,
    )


def _chat_completion_to_span(
    *, workspace: str, body: ChatCompletionsIngestRequest, ingested_at: datetime
) -> IntakeSpan:
    request = body.request.model_dump(mode="json")
    response = body.response.model_dump(mode="json")
    usage = _dict_or_empty(response.get("usage"))

    external_span_id = _external_span_id(response, request)
    trace_id = body.trace_id or external_span_id
    session_id = body.session_id or trace_id

    error = response.get("error") if isinstance(response.get("error"), dict) else None
    span_status = SpanStatus.ERROR if error is not None else SpanStatus.SUCCESS

    parsed_start = _datetime_from_unix_seconds(response.get("created"))
    start_time = parsed_start if parsed_start is not None and parsed_start <= ingested_at else ingested_at

    model = _as_str(response.get("model")) or _as_str(request.get("model")) or ""
    attribute_bags = _build_attribute_bags(body=body, request=request, response=response, usage=usage, error=error)

    return IntakeSpan(
        workspace=workspace,
        session_id=session_id,
        trace_id=trace_id,
        source_format=SOURCE_FORMAT,
        external_span_id=external_span_id,
        external_parent_span_id="",
        kind=SpanKind.LLM,
        name=model,
        status=span_status,
        start_time=start_time,
        end_time=ingested_at,
        attributes_string=attribute_bags.string,
        attributes_number=attribute_bags.number,
        attributes_bool=attribute_bags.boolean,
        input=json_dumps_preserve(request),
        output=json_dumps_preserve(response),
        event_ts=ingested_at,
    )


def _build_attribute_bags(
    *,
    body: ChatCompletionsIngestRequest,
    request: dict[str, Any],
    response: dict[str, Any],
    usage: dict[str, Any],
    error: dict[str, Any] | None,
) -> SpanAttributeBags:
    prompt_details = _dict_or_empty(usage.get("prompt_tokens_details"))
    completion_details = _dict_or_empty(usage.get("completion_tokens_details"))

    error_type: str | None = None
    error_message: str | None = None
    if error is not None:
        error_type = _as_str(error.get("type")) or _as_str(error.get("code"))
        error_message = _as_str(error.get("message"))

    evaluation_context = body.evaluation_context
    semantic = SpanSemanticAttributes(
        model=_as_str(response.get("model")) or _as_str(request.get("model")),
        provider=body.provider or _infer_provider(response),
        evaluation_id=evaluation_context.evaluation_id if evaluation_context is not None else None,
        evaluation_sha=evaluation_context.evaluation_sha if evaluation_context is not None else None,
        evaluation_run_id=evaluation_context.evaluation_run_id if evaluation_context is not None else None,
        dataset_id=evaluation_context.dataset_id if evaluation_context is not None else None,
        dataset_name=evaluation_context.dataset_name if evaluation_context is not None else None,
        dataset_version=evaluation_context.dataset_version if evaluation_context is not None else None,
        test_case_id=evaluation_context.test_case_id if evaluation_context is not None else None,
        error_type=error_type,
        error_message=error_message,
        input_tokens=_clean_int(usage.get("prompt_tokens")),
        output_tokens=_clean_int(usage.get("completion_tokens")),
        total_tokens=_clean_int(usage.get("total_tokens")),
        cached_tokens=_clean_int(prompt_details.get("cached_tokens")),
        prompt_audio_tokens=_clean_int(prompt_details.get("audio_tokens")),
        completion_reasoning_tokens=_clean_int(completion_details.get("reasoning_tokens")),
        completion_audio_tokens=_clean_int(completion_details.get("audio_tokens")),
    )
    attribute_bags = semantic.to_bags()
    if evaluation_context is not None:
        attribute_bags.put_json("evaluation.metadata", evaluation_context.metadata)
    return attribute_bags


def _external_span_id(response: dict[str, Any], request: dict[str, Any]) -> str:
    """OpenAI chat-completion responses carry a stable `id` like 'chatcmpl-...'.

    When that id is missing (e.g. self-rolled providers, partial captures),
    fall back to a deterministic hash of the request+response so retries of
    the same payload still dedupe.
    """

    response_id = _as_str(response.get("id"))
    if response_id:
        return response_id
    return stable_id(
        json_dumps_preserve(request),
        json_dumps_preserve(response),
        prefix="chatcmpl-hash",
    )


def _infer_provider(response: dict[str, Any]) -> str | None:
    response_id = _as_str(response.get("id")) or ""
    if response_id.startswith("chatcmpl-"):
        return "openai"
    return None


def _datetime_from_unix_seconds(value: Any) -> datetime | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_int(value: Any) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if value >= 0 else None
