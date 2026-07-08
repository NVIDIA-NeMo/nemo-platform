# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Boundary mapping: Evaluator vocabulary -> Intake/Experiments wire shapes.

This is the single place where Evaluator domain objects (``AgentEvalTrial``,
``AgentEvalTaskScore``, ``MetricOutput``) become the request bodies Intake and
the Experiments API expect. The Intake write-adapter tickets (D3/D4/D5) obtain
their request shapes and field names *only* from here, so a later rename is a
one-file change.

Design constraints (see AALGO-289):

* **Pure.** Every function reads domain values and returns Intake request models.
  No HTTP or platform client is used here.
* **Typed at the boundary.** The returned Pydantic models come from Intake's slim
  client contract package, so API changes surface here as type or validation errors
  without importing the service implementation.
* The well-known evidence-key constants (``initial_state``/``trace``/``logs``/
  ``final_state``/``verifier_logs``) belong with the SDK evidence work (D1,
  AALGO-281). Until D1 lands, this module references them as string literals so
  it stays unblocked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial
from nemo_intake_client.models import (
    AtifAgent,
    AtifFinalMetrics,
    AtifIngestRequest,
    AtifStep,
    AtifStepAgent,
    EvaluatorResultDataType,
    EvaluatorResultInput,
    ExperimentContext,
)

# --- Shared conventions -----------------------------------------------------

#: ATIF schema version the adapter emits.
ATIF_SCHEMA_VERSION: Literal["ATIF-v1.7"] = "ATIF-v1.7"

#: Default ``agent.version`` when the run target carries none. Neither Model nor
#: Agent has a version field today, and ATIF requires one (design doc §3.9 #6).
DEFAULT_AGENT_VERSION = "unknown"

# Evidence-descriptor keys. ATIF is carried as a ``format`` on ``kind="trace"``,
# *not* as a distinct ``kind``. These are string literals until D1 (AALGO-281)
# promotes them to shared descriptor-key constants on the SDK evidence types.
EVIDENCE_KIND_TRACE = "trace"
TRACE_FORMAT_ATIF = "atif"


def session_id_for(run_id: str, trial_id: str) -> str:
    """Return the stable, adapter-minted session id for a trial.

    One session id per Trial keeps ATIF ingest idempotent and lets per-metric
    scores be attached to the same trajectory afterward. This is the single
    source of the convention; callers must not hand-roll it.
    """
    return f"{run_id}:{trial_id}"


def run_task_to_experiment_context(trial: AgentEvalTrial, *, experiment_id: str) -> ExperimentContext:
    """Build the lean ingest ``experiment_context`` for a trial.

    Only ``experiment_id`` and ``test_case_id`` live here. Dataset, group, and
    free-form metadata belong on the Experiment entity (created separately via
    the platform Experiments SDK), not on the per-ingest context.
    """
    return ExperimentContext(experiment_id=experiment_id, test_case_id=trial.task_id)


def trial_to_atif_ingest(
    trial: AgentEvalTrial,
    *,
    run_id: str,
    experiment_id: str,
    agent_name: str,
    agent_version: str = DEFAULT_AGENT_VERSION,
    model_name: str | None = None,
    final_metrics: AtifFinalMetrics | None = None,
) -> AtifIngestRequest:
    """Build the ATIF ingest params for a single Trial.

    Until ATIF normalization of trace evidence lands (D2, AALGO-282), this emits
    a minimal single-step trajectory carrying the trial's final output text, so
    the session/score path works end to end. Real ``steps[]`` reconstructed from
    ``trial.evidence`` arrive with D2.
    """
    output_text = trial.output.output_text if trial.output is not None else None
    agent = (
        AtifAgent(name=agent_name, version=agent_version)
        if model_name is None
        else AtifAgent(name=agent_name, version=agent_version, model_name=model_name)
    )
    steps: list[AtifStep] = [AtifStepAgent(source="agent", step_id=1, message=output_text or "")]
    session_id = session_id_for(run_id, trial.id)
    experiment_context = run_task_to_experiment_context(trial, experiment_id=experiment_id)
    if final_metrics is None:
        return AtifIngestRequest(
            schema_version=ATIF_SCHEMA_VERSION,
            session_id=session_id,
            agent=agent,
            steps=steps,
            experiment_context=experiment_context,
        )
    return AtifIngestRequest(
        schema_version=ATIF_SCHEMA_VERSION,
        session_id=session_id,
        agent=agent,
        steps=steps,
        experiment_context=experiment_context,
        final_metrics=final_metrics,
    )


@dataclass(frozen=True)
class SkippedOutput:
    """A metric output omitted from publish, with the reason it was dropped (see cross-team ask X6)."""

    name: str
    reason: str


def score_to_evaluator_results(
    score: AgentEvalTaskScore,
    *,
    session_id: str,
    span_id: str,
) -> tuple[list[EvaluatorResultInput], list[SkippedOutput]]:
    """Map one ``AgentEvalTaskScore`` to ``(rows, skipped)`` for Intake.

    ``rows`` is one evaluator-result param per publishable output: ``name`` is
    ``"{metric_type}.{output}"`` (matching the SDK summary's aggregate naming) and the
    value is coerced into the matching ``data_type``, populating exactly one of ``value``
    / ``string_value``. ``session_id``/``span_id`` are supplied by the caller — the
    trajectory span id is resolved at publish time, not derivable from the pure score.

    ``skipped`` carries the outputs that can't be published, with the reason — so the
    publishable/omitted split has a single source of truth and callers can report the
    omissions instead of silently losing them. A FAILED score yields no rows (every output
    skipped); a completed score's non-finite (NaN/inf) outputs are dropped (NaN isn't
    JSON-representable — the platform client's encoder rejects it — so it can't be sent).

    TODO(X6): once Intake can represent a failed metric result, publish these as failures
    instead of dropping them.
    """
    if score.status == AgentEvalScoreStatus.FAILED:
        skipped = [
            SkippedOutput(name=f"{score.metric_type}.{output.name}", reason="scoring failed")
            for output in score.outputs
        ]
        return [], skipped

    comment = score.diagnostics[0].message if score.diagnostics else None
    rows: list[EvaluatorResultInput] = []
    skipped: list[SkippedOutput] = []
    for output in score.outputs:
        name = f"{score.metric_type}.{output.name}"
        data_type, value, string_value = _coerce_metric_value(output.value)
        if value is not None and not math.isfinite(value):
            skipped.append(SkippedOutput(name=name, reason="non-finite value"))
            continue
        rows.append(
            _evaluator_result_input(
                session_id=session_id,
                span_id=span_id,
                name=name,
                data_type=data_type,
                value=value,
                string_value=string_value,
                comment=comment,
            )
        )
    return rows, skipped


def _evaluator_result_input(
    *,
    session_id: str,
    span_id: str,
    name: str,
    data_type: EvaluatorResultDataType,
    value: float | None,
    string_value: str | None,
    comment: str | None,
) -> EvaluatorResultInput:
    if value is not None:
        if comment is None:
            return EvaluatorResultInput(
                session_id=session_id,
                span_id=span_id,
                name=name,
                data_type=data_type,
                value=value,
            )
        return EvaluatorResultInput(
            session_id=session_id,
            span_id=span_id,
            name=name,
            data_type=data_type,
            value=value,
            comment=comment,
        )
    if string_value is None:
        raise ValueError("Evaluator result must carry a numeric or string value")
    if comment is None:
        return EvaluatorResultInput(
            session_id=session_id,
            span_id=span_id,
            name=name,
            data_type=data_type,
            string_value=string_value,
        )
    return EvaluatorResultInput(
        session_id=session_id,
        span_id=span_id,
        name=name,
        data_type=data_type,
        string_value=string_value,
        comment=comment,
    )


def _coerce_metric_value(value: object) -> tuple[EvaluatorResultDataType, float | None, str | None]:
    """Classify a metric output value into ``(data_type, value, string_value)``.

    Unwraps a Pydantic ``RootModel`` (``.root``) first, then:

    * ``bool`` -> ``BOOLEAN`` with value 1.0/0.0 (checked before ``int``, since
      ``bool`` is a subclass of ``int``);
    * ``int``/``float`` -> ``NUMERIC``;
    * anything else (strings, labels) -> ``TEXT`` via ``str()``.

    CATEGORICAL is intentionally not emitted: a category and free text are
    indistinguishable at the value level today (both arrive as ``str``/``Label``),
    so everything string-valued maps to TEXT until a real signal exists.
    """
    unwrapped = getattr(value, "root", value)
    if isinstance(unwrapped, bool):
        return EvaluatorResultDataType.BOOLEAN, (1.0 if unwrapped else 0.0), None
    if isinstance(unwrapped, (int, float)):
        return EvaluatorResultDataType.NUMERIC, float(unwrapped), None
    return EvaluatorResultDataType.TEXT, None, str(unwrapped)
