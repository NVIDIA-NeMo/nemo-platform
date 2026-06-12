# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Map ATIF trajectories into Intake spans.

Preserved-only ATIF fields remain in ``raw_attributes`` when Intake has no
dedicated span column for them. That includes agent tool definitions,
``final_metrics.total_steps``, step reasoning effort, and copied-context flags.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from nmp.intake.spans.domain import (
    EvaluatorResult,
    EvaluatorResultDataType,
    IntakeSpan,
    SpanKind,
    SpanStatus,
)
from nmp.intake.spans.ingest.atif_domain import (
    AtifMetrics,
    AtifObservation,
    AtifObservationResult,
    AtifStep,
    AtifStepAgent,
    AtifSubagentTrajectoryRef,
    AtifToolCall,
    AtifTrajectory,
)
from nmp.intake.spans.ingest.evaluation_context import EvaluationContext
from nmp.intake.spans.span_attribute_bags import SpanAttributeBags
from nmp.intake.spans.span_semantic_attributes import SpanSemanticAttributes
from nmp.intake.spans.storage import json_dumps, json_dumps_preserve, stable_id
from pydantic import BaseModel


def trajectory_to_spans(
    *,
    workspace: str,
    trajectory: AtifTrajectory,
    ingested_at: datetime,
) -> list[IntakeSpan]:
    trajectory_span = _trajectory_to_span(
        workspace=workspace,
        trajectory=trajectory,
        ingested_at=ingested_at,
    )
    spans = [trajectory_span]
    spans.extend(
        _evaluator_result_to_span(
            workspace=workspace,
            trajectory=trajectory,
            parent_span=trajectory_span,
            ingested_at=ingested_at,
        )
    )
    for index, step in enumerate(trajectory.steps):
        step_span = _step_to_span(
            workspace=workspace,
            default_session_id=trajectory.session_id,
            default_agent_name=trajectory.agent.name,
            default_agent_version=trajectory.agent.version,
            default_model_name=trajectory.agent.model_name,
            external_parent_span_id=trajectory_span.external_span_id,
            step=step,
            index=index,
            ingested_at=ingested_at,
        )
        spans.append(step_span)
        spans.extend(
            _tool_call_to_span(
                workspace=workspace,
                default_session_id=trajectory.session_id,
                default_agent_name=trajectory.agent.name,
                default_agent_version=trajectory.agent.version,
                default_model_name=trajectory.agent.model_name,
                external_parent_span_id=step_span.external_span_id,
                step=step,
                step_index=index,
                tool_index=tool_index,
                tool_call=tool_call,
                ingested_at=ingested_at,
            )
            for tool_index, tool_call in enumerate(_step_tool_calls(step))
        )
        spans.extend(
            _subagent_ref_to_span(
                workspace=workspace,
                default_session_id=trajectory.session_id,
                default_agent_name=trajectory.agent.name,
                default_agent_version=trajectory.agent.version,
                default_model_name=trajectory.agent.model_name,
                external_parent_span_id=step_span.external_span_id,
                step=step,
                step_index=index,
                result_index=result_index,
                ref_index=ref_index,
                result=result,
                subagent_ref=subagent_ref,
                ingested_at=ingested_at,
            )
            for result_index, result in _observation_results_with_subagents(step)
            for ref_index, subagent_ref in enumerate(result.subagent_trajectory_ref or [])
        )
    return spans


def _trajectory_to_span(
    *,
    workspace: str,
    trajectory: AtifTrajectory,
    ingested_at: datetime,
) -> IntakeSpan:
    raw_attributes = _model_dict(trajectory)
    raw_attributes.pop("steps", None)
    raw_attributes.pop("evaluation_context", None)
    # Embedded ATIF-v1.7 subagent trajectories are accepted and preserved in
    # atif.raw for now. Only subagent_trajectory_ref entries are materialized as
    # lightweight delegation spans until embedded trajectory expansion has
    # explicit trace identity and parentage semantics.
    # ATIF span IDs are trace-native by design: session_id is the trace identity,
    # while evaluation_context is queryable metadata on the root span.
    #
    # Token/cost accounting belongs on the spans that incurred the LLM calls
    # when a source emits per-step metrics. Some ATIF producers only emit
    # trajectory.final_metrics, so use those root totals field-by-field when
    # the matching per-step accounting is absent.
    final_metrics = trajectory.final_metrics
    input_tokens = (
        final_metrics.total_prompt_tokens
        if final_metrics is not None and not _trajectory_has_step_prompt_metrics(trajectory)
        else None
    )
    output_tokens = (
        final_metrics.total_completion_tokens
        if final_metrics is not None and not _trajectory_has_step_completion_metrics(trajectory)
        else None
    )
    cached_tokens = (
        final_metrics.total_cached_tokens
        if final_metrics is not None and not _trajectory_has_step_cached_metrics(trajectory)
        else None
    )
    cost_total_usd = (
        _decimal(final_metrics.total_cost_usd)
        if final_metrics is not None and not _trajectory_has_step_cost_metrics(trajectory)
        else None
    )
    external_span_id = stable_id(workspace, trajectory.session_id, "trajectory", prefix="span")
    attribute_bags = _span_attributes(
        model=trajectory.agent.model_name,
        agent_name=trajectory.agent.name,
        agent_version=trajectory.agent.version,
        evaluation_context=trajectory.evaluation_context,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        total_tokens=_sum_ints(input_tokens, output_tokens),
        cost_total_usd=cost_total_usd,
        raw_attributes=raw_attributes,
    )
    return IntakeSpan(
        workspace=workspace,
        session_id=trajectory.session_id,
        trace_id=trajectory.session_id,
        source_format="atif",
        external_span_id=external_span_id,
        kind=SpanKind.AGENT,
        name=trajectory.agent.name,
        status=SpanStatus.ERROR if _trajectory_has_error(trajectory) else SpanStatus.SUCCESS,
        start_time=_trajectory_started_at(trajectory, ingested_at),
        end_time=_trajectory_ended_at(trajectory),
        attributes_string=attribute_bags.string,
        attributes_number=attribute_bags.number,
        attributes_bool=attribute_bags.boolean,
        input=_trajectory_input(trajectory) or "",
        output=_trajectory_output(trajectory) or "",
        event_ts=ingested_at,
    )


def _step_to_span(
    *,
    workspace: str,
    default_session_id: str,
    default_agent_name: str,
    default_agent_version: str | None,
    default_model_name: str | None,
    external_parent_span_id: str,
    step: AtifStep,
    index: int,
    ingested_at: datetime,
) -> IntakeSpan:
    raw_step = _model_dict(step)
    metrics = _step_metrics(step)
    model_name = _step_model_name(step)
    input_tokens = metrics.prompt_tokens if metrics is not None else None
    output_tokens = metrics.completion_tokens if metrics is not None else None
    external_span_id = stable_id(
        workspace,
        default_session_id,
        str(index),
        json_dumps(raw_step),
        prefix="span",
    )
    attribute_bags = _span_attributes(
        model=model_name or default_model_name,
        agent_name=default_agent_name,
        agent_version=default_agent_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=metrics.cached_tokens if metrics is not None else None,
        total_tokens=_sum_ints(input_tokens, output_tokens),
        cost_total_usd=_decimal(metrics.cost_usd) if metrics is not None else None,
        raw_attributes=raw_step,
    )
    return IntakeSpan(
        workspace=workspace,
        session_id=default_session_id,
        trace_id=default_session_id,
        source_format="atif",
        external_span_id=external_span_id,
        external_parent_span_id=external_parent_span_id,
        kind=_step_kind(step),
        name=f"{step.source}-{step.step_id}",
        status=SpanStatus.SUCCESS,
        start_time=_step_started_at(step, index, ingested_at),
        attributes_string=attribute_bags.string,
        attributes_number=attribute_bags.number,
        attributes_bool=attribute_bags.boolean,
        input=_step_input(step) or "",
        output=_step_output(step) or "",
        event_ts=ingested_at,
    )


def _tool_call_to_span(
    *,
    workspace: str,
    default_session_id: str,
    default_agent_name: str,
    default_agent_version: str | None,
    default_model_name: str | None,
    external_parent_span_id: str,
    step: AtifStep,
    step_index: int,
    tool_index: int,
    tool_call: AtifToolCall,
    ingested_at: datetime,
) -> IntakeSpan:
    raw_tool_call = _model_dict(tool_call)
    result = _observation_result_for_tool_call(step, tool_call.tool_call_id)
    error_message = _tool_result_error_message(step, result)
    external_span_id = stable_id(
        workspace,
        default_session_id,
        str(step_index),
        "tool",
        str(tool_index),
        json_dumps(raw_tool_call),
        prefix="span",
    )
    attribute_bags = _span_attributes(
        model=_step_model_name(step) or default_model_name,
        agent_name=default_agent_name,
        agent_version=default_agent_version,
        tool_name=tool_call.function_name,
        error_message=error_message,
        raw_attributes={
            "step_id": step.step_id,
            "tool_call": raw_tool_call,
            "observation_result": _model_dict(result) if result is not None else None,
        },
    )
    return IntakeSpan(
        workspace=workspace,
        session_id=default_session_id,
        trace_id=default_session_id,
        source_format="atif",
        external_span_id=external_span_id,
        external_parent_span_id=external_parent_span_id,
        kind=SpanKind.TOOL,
        name=tool_call.function_name,
        status=SpanStatus.ERROR if _tool_result_is_error(step, result) else SpanStatus.SUCCESS,
        start_time=_step_started_at(step, step_index, ingested_at),
        attributes_string=attribute_bags.string,
        attributes_number=attribute_bags.number,
        attributes_bool=attribute_bags.boolean,
        input=json_dumps_preserve(raw_tool_call),
        output=_string_or_json(result) or "",
        event_ts=ingested_at,
    )


def _subagent_ref_to_span(
    *,
    workspace: str,
    default_session_id: str,
    default_agent_name: str,
    default_agent_version: str | None,
    default_model_name: str | None,
    external_parent_span_id: str,
    step: AtifStep,
    step_index: int,
    result_index: int,
    ref_index: int,
    result: AtifObservationResult,
    subagent_ref: AtifSubagentTrajectoryRef,
    ingested_at: datetime,
) -> IntakeSpan:
    raw_result = _model_dict(result)
    raw_ref = _model_dict(subagent_ref)
    error_message = _tool_result_error_message(step, result)
    subagent_identity = _subagent_ref_identity(subagent_ref)
    external_span_id = stable_id(
        workspace,
        default_session_id,
        str(step_index),
        "subagent",
        str(result_index),
        str(ref_index),
        subagent_identity,
        prefix="span",
    )
    attribute_bags = _span_attributes(
        model=_step_model_name(step) or default_model_name,
        agent_name=default_agent_name,
        agent_version=default_agent_version,
        error_message=error_message,
        raw_attributes={
            "step_id": step.step_id,
            "observation_result": raw_result,
            "subagent_trajectory_ref": raw_ref,
        },
    )
    return IntakeSpan(
        workspace=workspace,
        session_id=default_session_id,
        trace_id=default_session_id,
        source_format="atif",
        external_span_id=external_span_id,
        external_parent_span_id=external_parent_span_id,
        kind=SpanKind.AGENT,
        name=f"subagent-{subagent_identity}",
        status=SpanStatus.ERROR if _tool_result_is_error(step, result) else SpanStatus.SUCCESS,
        start_time=_step_started_at(step, step_index, ingested_at),
        attributes_string=attribute_bags.string,
        attributes_number=attribute_bags.number,
        attributes_bool=attribute_bags.boolean,
        input=json_dumps_preserve(raw_ref),
        output=json_dumps_preserve(raw_result),
        event_ts=ingested_at,
    )


def _evaluator_result_to_span(
    *,
    workspace: str,
    trajectory: AtifTrajectory,
    parent_span: IntakeSpan,
    ingested_at: datetime,
) -> list[IntakeSpan]:
    extra = trajectory.extra or {}
    verifier_result = _dict_or_none(extra.get("verifier_result"))
    if verifier_result is None:
        return []
    verifier = _dict_or_none(extra.get("verifier"))
    score = _evaluator_score(verifier_result)
    input_value = {
        key: value
        for key, value in {
            "session_id": trajectory.session_id,
            "evaluated_span_id": parent_span.external_span_id,
            "task_id": extra.get("task_id"),
            "task_name": extra.get("task_name"),
            "trial_name": extra.get("trial_name"),
            "trial_uri": extra.get("trial_uri"),
        }.items()
        if value is not None
    }
    output_value = {
        "score": score,
        "verifier_result": verifier_result,
    }
    metadata = {
        key: value
        for key, value in {
            "source": "harbor",
            "event_type": "evaluator_result",
            "name": "harbor.verifier",
            "verifier": verifier,
        }.items()
        if value is not None
    }
    input_json = json_dumps_preserve(input_value)
    output_json = json_dumps_preserve(output_value)
    metadata_json = json_dumps_preserve(metadata)
    raw_attributes = {
        "openinference.span.kind": "EVALUATOR",
        "input.value": input_json,
        "input.mime_type": "application/json",
        "output.value": output_json,
        "output.mime_type": "application/json",
        "metadata": metadata_json,
        "event_type": "evaluator_result",
        "name": "harbor.verifier",
        "score": score,
        "verifier_result": verifier_result,
    }
    started_at = _evaluator_started_at(trajectory) or ingested_at
    ended_at = _evaluator_ended_at(trajectory)
    external_span_id = stable_id(
        workspace,
        trajectory.session_id,
        "evaluator",
        json_dumps(raw_attributes),
        prefix="span",
    )
    attribute_bags = _span_attributes(
        model=trajectory.agent.model_name,
        agent_name=trajectory.agent.name,
        agent_version=trajectory.agent.version,
        raw_attributes=raw_attributes,
    )
    return [
        IntakeSpan(
            workspace=workspace,
            session_id=trajectory.session_id,
            trace_id=trajectory.session_id,
            source_format="atif",
            external_span_id=external_span_id,
            external_parent_span_id=parent_span.external_span_id,
            kind=SpanKind.EVALUATOR,
            name="harbor.verifier",
            status=SpanStatus.SUCCESS,
            start_time=started_at,
            end_time=ended_at,
            attributes_string=attribute_bags.string,
            attributes_number=attribute_bags.number,
            attributes_bool=attribute_bags.boolean,
            input=input_json,
            output=output_json,
            event_ts=ingested_at,
        )
    ]


def _span_attributes(
    *,
    model: str | None = None,
    agent_name: str | None = None,
    agent_version: str | None = None,
    evaluation_context: EvaluationContext | None = None,
    tool_name: str | None = None,
    error_message: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_total_usd: Decimal | None = None,
    raw_attributes: dict[str, Any] | None = None,
) -> SpanAttributeBags:
    semantic_attributes = SpanSemanticAttributes(
        model=model,
        agent_name=agent_name,
        agent_version=agent_version,
        evaluation_id=evaluation_context.evaluation_id if evaluation_context is not None else None,
        evaluation_sha=evaluation_context.evaluation_sha if evaluation_context is not None else None,
        evaluation_run_id=evaluation_context.evaluation_run_id if evaluation_context is not None else None,
        test_case_id=evaluation_context.test_case_id if evaluation_context is not None else None,
        tool_name=tool_name,
        error_message=error_message,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        total_tokens=total_tokens,
        cost_total_usd=cost_total_usd,
    )
    attribute_bags = semantic_attributes.to_bags()
    if evaluation_context is not None and evaluation_context.metadata:
        attribute_bags.put_json("nemo.experiment.metadata", evaluation_context.metadata)
    if raw_attributes is not None:
        attribute_bags.put_json("atif.raw", raw_attributes)
    return attribute_bags


def trajectory_to_evaluator_results(
    *,
    workspace: str,
    trajectory: AtifTrajectory,
    spans: list[IntakeSpan],
    ingested_at: datetime,
) -> list[EvaluatorResult]:
    """Extract evaluator_results rows from an ATIF trajectory's verifier_result block.

    Returns one evaluator_result row targeting the EVALUATOR-kind span that
    ``trajectory_to_spans`` already produced for the verifier. The span preserves
    the original tree structure; this row makes the score queryable by name and
    value without parsing the span payload.
    """

    extra = trajectory.extra or {}
    verifier_result = _dict_or_none(extra.get("verifier_result"))
    if verifier_result is None:
        return []
    evaluator_span = next((span for span in spans if span.kind == SpanKind.EVALUATOR), None)
    if evaluator_span is None:
        return []
    score = _evaluator_score(verifier_result)
    if score is None:
        return []
    data_type, value, string_value = _coerce_evaluator_value(score)
    return [
        EvaluatorResult(
            evaluator_result_id=stable_id(
                evaluator_span.external_span_id,
                "harbor.verifier",
                prefix="eval",
            ),
            span_id=evaluator_span.external_span_id,
            session_id=trajectory.session_id,
            workspace=workspace,
            name="harbor.verifier",
            value=value,
            string_value=string_value,
            data_type=data_type,
            comment=None,
            created_by="intake:atif_importer",
            created_at=ingested_at,
            ingested_at=ingested_at,
        )
    ]


def _coerce_evaluator_value(
    score: bool | int | float | str,
) -> tuple[EvaluatorResultDataType, float | None, str | None]:
    if isinstance(score, bool):
        return EvaluatorResultDataType.BOOLEAN, 1.0 if score else 0.0, None
    if isinstance(score, (int, float)):
        return EvaluatorResultDataType.NUMERIC, float(score), None
    return EvaluatorResultDataType.TEXT, None, str(score)


def _subagent_ref_identity(subagent_ref: AtifSubagentTrajectoryRef) -> str:
    if subagent_ref.trajectory_id is not None:
        return subagent_ref.trajectory_id
    if subagent_ref.trajectory_path is not None:
        return subagent_ref.trajectory_path
    assert subagent_ref.session_id is not None
    return subagent_ref.session_id


def _step_kind(step: AtifStep) -> SpanKind:
    return SpanKind.LLM if isinstance(step, AtifStepAgent) else SpanKind.AGENT


def _step_input(step: AtifStep) -> str | None:
    if isinstance(step, AtifStepAgent):
        return None
    return _string_or_json(step.message)


def _step_output(step: AtifStep) -> str | None:
    if isinstance(step, AtifStepAgent):
        payload: dict[str, Any] = {}
        if step.message != "":
            payload["message"] = _json_value(step.message)
        if step.reasoning_content is not None:
            payload["reasoning_content"] = step.reasoning_content
        if step.tool_calls is not None:
            payload["tool_calls"] = [_model_dict(tool_call) for tool_call in step.tool_calls]
        return json_dumps_preserve(payload) if payload else None
    return None


def _step_model_name(step: AtifStep) -> str | None:
    return step.model_name if isinstance(step, AtifStepAgent) else None


def _step_metrics(step: AtifStep) -> AtifMetrics | None:
    return step.metrics if isinstance(step, AtifStepAgent) else None


def _trajectory_has_step_prompt_metrics(trajectory: AtifTrajectory) -> bool:
    return any(
        (metrics := _step_metrics(step)) is not None and metrics.prompt_tokens is not None for step in trajectory.steps
    )


def _trajectory_has_step_completion_metrics(trajectory: AtifTrajectory) -> bool:
    return any(
        (metrics := _step_metrics(step)) is not None and metrics.completion_tokens is not None
        for step in trajectory.steps
    )


def _trajectory_has_step_cached_metrics(trajectory: AtifTrajectory) -> bool:
    return any(
        (metrics := _step_metrics(step)) is not None and metrics.cached_tokens is not None for step in trajectory.steps
    )


def _trajectory_has_step_cost_metrics(trajectory: AtifTrajectory) -> bool:
    return any(
        (metrics := _step_metrics(step)) is not None and metrics.cost_usd is not None for step in trajectory.steps
    )


def _trajectory_input(trajectory: AtifTrajectory) -> str | None:
    for step in trajectory.steps:
        if step.source == "user":
            return _string_or_json(step.message)
    return None


def _trajectory_output(trajectory: AtifTrajectory) -> str | None:
    for step in reversed(trajectory.steps):
        if isinstance(step, AtifStepAgent):
            if step.message != "":
                return _string_or_json(step.message)
            return _step_output(step)
    return None


def _trajectory_has_error(trajectory: AtifTrajectory) -> bool:
    for step in trajectory.steps:
        if not isinstance(step, AtifStepAgent):
            continue
        observation = _step_observation(step)
        if observation is None:
            continue
        for result in observation.results:
            if _tool_result_is_error(step, result):
                return True
    return False


def _step_tool_calls(step: AtifStep) -> list[AtifToolCall]:
    if not isinstance(step, AtifStepAgent):
        return []
    return step.tool_calls or []


def _step_observation(step: AtifStep) -> AtifObservation | None:
    return step.observation if isinstance(step, AtifStepAgent) else None


def _observation_result_for_tool_call(step: AtifStep, tool_call_id: str) -> AtifObservationResult | None:
    observation = _step_observation(step)
    if observation is None:
        return None
    for result in observation.results:
        if result.source_call_id == tool_call_id:
            return result
    return None


def _observation_results_with_subagents(step: AtifStep) -> list[tuple[int, AtifObservationResult]]:
    observation = _step_observation(step)
    if observation is None:
        return []
    return [
        (result_index, result)
        for result_index, result in enumerate(observation.results)
        if result.subagent_trajectory_ref
    ]


def _trajectory_started_at(trajectory: AtifTrajectory, ingested_at: datetime) -> datetime:
    started_candidates = [_timestamp(step) for step in trajectory.steps]
    started_candidates.append(_evaluator_started_at(trajectory))
    return min((started_at for started_at in started_candidates if started_at is not None), default=ingested_at)


def _trajectory_ended_at(trajectory: AtifTrajectory) -> datetime | None:
    ended_candidates = [_timestamp(step) for step in trajectory.steps]
    ended_candidates.append(_evaluator_ended_at(trajectory))
    return max((ended_at for ended_at in ended_candidates if ended_at is not None), default=None)


def _evaluator_started_at(trajectory: AtifTrajectory) -> datetime | None:
    verifier = _dict_or_none((trajectory.extra or {}).get("verifier"))
    return _datetime_from_value(verifier.get("started_at") if verifier is not None else None)


def _evaluator_ended_at(trajectory: AtifTrajectory) -> datetime | None:
    verifier = _dict_or_none((trajectory.extra or {}).get("verifier"))
    return _datetime_from_value(verifier.get("finished_at") if verifier is not None else None)


def _step_started_at(step: AtifStep, index: int, ingested_at: datetime) -> datetime:
    return _timestamp(step) or (ingested_at + timedelta(milliseconds=index))


def _timestamp(step: AtifStep) -> datetime | None:
    if step.timestamp is None:
        return None
    return _datetime_from_value(step.timestamp)


def _datetime_from_value(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _tool_result_is_error(step: AtifStep, result: AtifObservationResult | None) -> bool:
    # These markers are emitted by the Claude-Code Harbor trajectories we ingest today.
    # ATIF itself does not define a normalized tool-result error field.
    metadata = _matched_tool_result_metadata(step, result)
    if metadata.get("is_error") is True:
        return True
    if _step_extra_bool(step, "tool_result_is_error") and _is_only_observation_result(step, result):
        return True
    content = _result_text(result)
    return content is not None and "[error]" in content.lower()


def _tool_result_error_message(step: AtifStep, result: AtifObservationResult | None) -> str | None:
    if not _tool_result_is_error(step, result):
        return None
    content = _result_text(result)
    if content is not None:
        return content
    raw_tool_result = _matched_tool_result_metadata(step, result).get("raw_tool_result")
    if isinstance(raw_tool_result, dict) and isinstance(raw_tool_result.get("content"), str):
        return raw_tool_result["content"]
    return None


def _matched_tool_result_metadata(step: AtifStep, result: AtifObservationResult | None) -> dict[str, Any]:
    metadata = _step_extra_dict(step, "tool_result_metadata")
    if not metadata or result is None:
        return {}
    raw_tool_result = metadata.get("raw_tool_result")
    if isinstance(raw_tool_result, dict):
        raw_tool_use_id = raw_tool_result.get("tool_use_id")
        if isinstance(raw_tool_use_id, str):
            return metadata if result.source_call_id == raw_tool_use_id else {}
    return metadata if _is_only_observation_result(step, result) else {}


def _is_only_observation_result(step: AtifStep, result: AtifObservationResult | None) -> bool:
    observation = _step_observation(step)
    return (
        result is not None
        and observation is not None
        and len(observation.results) == 1
        and observation.results[0] is result
    )


def _result_text(result: AtifObservationResult | None) -> str | None:
    if result is None or not isinstance(result.content, str):
        return None
    return result.content


def _step_extra_bool(step: AtifStep, key: str) -> bool:
    return step.extra is not None and step.extra.get(key) is True


def _step_extra_dict(step: AtifStep, key: str) -> dict[str, Any]:
    value = step.extra.get(key) if step.extra is not None else None
    return value if isinstance(value, dict) else {}


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _evaluator_score(verifier_result: dict[str, Any]) -> bool | int | float | str | None:
    score = verifier_result.get("score")
    if isinstance(score, (int, float, str)):
        return score
    rewards = verifier_result.get("rewards")
    if not isinstance(rewards, dict):
        return None
    reward = rewards.get("reward")
    if isinstance(reward, (int, float, str)):
        return reward
    if len(rewards) == 1:
        only_reward = next(iter(rewards.values()))
        if isinstance(only_reward, (int, float, str)):
            return only_reward
    return None


def _string_or_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json_dumps_preserve(_json_value(value))


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _model_dict(value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _model_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _sum_ints(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)
