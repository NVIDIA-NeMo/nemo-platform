# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Boundary mapping: Evaluator vocabulary -> Intake/Experiments wire shapes.

This is the single place where Evaluator domain objects (``AgentEvalTrial``,
``AgentEvalTaskScore``, ``MetricOutput``) become the request bodies Intake and
the Experiments API expect. The Intake write-adapter tickets (D3/D4/D5) obtain
their request shapes and field names *only* from here, so a later rename is a
one-file change.

Design constraints (see AALGO-289):

* **Pure.** Every function reads SDK types and returns request params. No HTTP,
  no platform client, no imports from the Intake *service* (``nmp.intake.*``).
* **Typed at the boundary.** The returned values are the generated platform
  SDK's ``TypedDict`` params (``AtifCreateParams`` / ``EvaluatorResultCreateParams``).
  At runtime they are plain dicts the adapter splats into the client
  (``client.intake.ingest.atif.create(**body)``); statically, ``ty`` checks our
  field names, literals, and nested shapes against the real generated schema, so
  an API change that regenerates the SDK surfaces here as a type error instead of
  drifting silently. We depend on the client SDK (already a plugin dependency),
  never on the Intake service package.
* The well-known evidence-key constants (``initial_state``/``trace``/``logs``/
  ``final_state``/``verifier_logs``) belong with the SDK evidence work (D1,
  AALGO-281). Until D1 lands, this module references them as string literals so
  it stays unblocked.
"""

from __future__ import annotations

from typing import Literal

from nemo_evaluator_sdk.agent_eval.scores import AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial
from nemo_platform.types.intake.evaluator_result_create_params import EvaluatorResultCreateParams
from nemo_platform.types.intake.evaluator_result_data_type import EvaluatorResultDataType
from nemo_platform.types.intake.experiment_context_param import ExperimentContextParam
from nemo_platform.types.intake.ingest.atif_agent_param import AtifAgentParam
from nemo_platform.types.intake.ingest.atif_create_params import AtifCreateParams
from nemo_platform.types.intake.ingest.atif_final_metrics_param import AtifFinalMetricsParam
from nemo_platform.types.intake.ingest.atif_step_agent_param import AtifStepAgentParam

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


def run_task_to_experiment_context(trial: AgentEvalTrial, *, experiment_id: str) -> ExperimentContextParam:
    """Build the lean ingest ``experiment_context`` for a trial.

    Only ``experiment_id`` and ``test_case_id`` live here. Dataset, group, and
    free-form metadata belong on the Experiment entity (created separately via
    the platform Experiments SDK), not on the per-ingest context.
    """
    return {"experiment_id": experiment_id, "test_case_id": trial.task_id}


def trial_to_atif_ingest(
    trial: AgentEvalTrial,
    *,
    run_id: str,
    experiment_id: str,
    agent_name: str,
    agent_version: str = DEFAULT_AGENT_VERSION,
    model_name: str | None = None,
    final_metrics: AtifFinalMetricsParam | None = None,
) -> AtifCreateParams:
    """Build the ATIF ingest params for a single Trial.

    Until ATIF normalization of trace evidence lands (D2, AALGO-282), this emits
    a minimal single-step trajectory carrying the trial's final output text, so
    the session/score path works end to end. Real ``steps[]`` reconstructed from
    ``trial.evidence`` arrive with D2.
    """
    output_text = trial.output.output_text if trial.output is not None else None
    agent: AtifAgentParam = {"name": agent_name, "version": agent_version}
    if model_name is not None:
        agent["model_name"] = model_name
    step: AtifStepAgentParam = {"source": "agent", "step_id": 1, "message": output_text or ""}

    body: AtifCreateParams = {
        "schema_version": ATIF_SCHEMA_VERSION,
        "session_id": session_id_for(run_id, trial.id),
        "agent": agent,
        "steps": [step],
        "experiment_context": run_task_to_experiment_context(trial, experiment_id=experiment_id),
    }
    if final_metrics is not None:
        body["final_metrics"] = final_metrics
    return body


def score_to_evaluator_results(
    score: AgentEvalTaskScore,
    *,
    session_id: str,
    span_id: str,
) -> list[EvaluatorResultCreateParams]:
    """Turn one ``AgentEvalTaskScore`` into one evaluator-result param per output.

    ``name`` is ``"{metric_type}.{output}"`` (matching the SDK summary's
    aggregate naming). The output's value is coerced into the matching
    ``data_type``, populating exactly one of ``value`` / ``string_value``.
    ``session_id`` and ``span_id`` are supplied by the caller: the trajectory
    span id is resolved at publish time (the adapter's concern), not derivable
    from the pure score.
    """
    comment = score.diagnostics[0].message if score.diagnostics else None
    rows: list[EvaluatorResultCreateParams] = []
    for output in score.outputs:
        data_type, value, string_value = _coerce_metric_value(output.value)
        row: EvaluatorResultCreateParams = {
            "session_id": session_id,
            "span_id": span_id,
            "name": f"{score.metric_type}.{output.name}",
            "data_type": data_type,
        }
        if value is not None:
            row["value"] = value
        if string_value is not None:
            row["string_value"] = string_value
        if comment is not None:
            row["comment"] = comment
        rows.append(row)
    return rows


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
        return "BOOLEAN", (1.0 if unwrapped else 0.0), None
    if isinstance(unwrapped, (int, float)):
        return "NUMERIC", float(unwrapped), None
    return "TEXT", None, str(unwrapped)
