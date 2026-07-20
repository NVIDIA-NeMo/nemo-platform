#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed one experiment group that stresses every evaluator column rendering.

Companion to ``seed_experiments_demo.py``. Where that script seeds realistic
multi-group data, this one seeds a single group — **"Experiment column test"** —
whose evaluators are chosen to exercise the full range of evaluator-column types
the Experiments surfaces can render.

Background — how an evaluator becomes a column:

* Evaluator results carry a ``data_type`` of ``NUMERIC``, ``BOOLEAN``,
  ``CATEGORICAL``, or ``TEXT``.
* The evaluation rollup only aggregates ``NUMERIC`` and ``BOOLEAN`` values
  (``avg(value)`` per evaluator), so only those become score columns.
  ``CATEGORICAL`` / ``TEXT`` results are ingested but never surface as columns.
* The Studio cell formatter (``formatEvaluatorScore``) renders a column's mean
  as a **percentage** when it falls in ``[0, 1]`` and as a **raw 3-decimal
  number** otherwise (i.e. a 1-5 or 1-10 rubric). A row missing an evaluator
  that other rows have renders an empty ``-``.

So the distinct column renderings are: percentage, boolean pass-rate (also a
percentage, but a different ``data_type``), raw rubric number, and empty. The
evaluators below are **named after the value their column should show** so the
table is self-verifying — e.g. ``pct_95`` should read ``95.0%``, ``rubric_1to5``
should read ``4.200``.

Values are seeded deterministically (no per-session jitter on scores) so each
column lands exactly on the value in its name. Cost / latency / tokens keep
realistic variance so the non-score columns still look natural.

Usage::

    uv run services/intake/scripts/spans/seed_experiment_column_types.py \\
        --base-url http://127.0.0.1:8080

    # Delete this script's group + evaluations, then re-seed:
    uv run services/intake/scripts/spans/seed_experiment_column_types.py \\
        --base-url http://127.0.0.1:8080 --reset

Re-running without ``--reset`` is a no-op if the group already exists (it is
left untouched). Note: ClickHouse session data is keyed by ``evaluation.id``
(the evaluation name) and is not deletable via the public API, so re-seeding
after ``--reset`` re-uses the same evaluation names and prior session telemetry
still feeds the rollup.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_WORKSPACE = "default"

GROUP_NAME = "Experiment column test"
GROUP_DESCRIPTION = "One group per evaluator column rendering: percentage, boolean pass-rate, rubric numbers, empty, and non-scored categorical/text."

SEEDED_BY = "services/intake/scripts/spans/seed_experiment_column_types.py"


# ---------------------------------------------------------------------------
# Spec definitions
# ---------------------------------------------------------------------------


@dataclass
class EvaluatorSpec:
    """A single evaluator attached to an evaluation's sessions.

    ``name`` is chosen to match the value the column should render, so the
    seeded table is self-documenting. ``data_type`` selects which column
    rendering this evaluator exercises.
    """

    name: str
    # NUMERIC | BOOLEAN | CATEGORICAL | TEXT
    data_type: str = "NUMERIC"
    # NUMERIC/BOOLEAN target mean. NUMERIC renders as a percentage when in [0, 1]
    # and as a raw number when > 1 (rubric). BOOLEAN is the pass probability.
    mean: float = 0.0
    # NUMERIC upper bound. > 1 puts the column on the raw-number path.
    scale_max: float = 1.0
    # Per-session score jitter. Default 0 so the column lands exactly on `mean`.
    stddev: float = 0.0
    # CATEGORICAL sample space (uniform choice). Ingested but not a score column.
    categories: tuple[str, ...] = ()
    # TEXT sample space (uniform choice). Ingested but not a score column.
    text_samples: tuple[str, ...] = ()


@dataclass
class EvaluationSpec:
    name: str
    description: str
    evaluators: list[EvaluatorSpec]
    agent_name: str = "column-test-agent"
    agent_version: str = "1.0.0"
    model_name: str = "provider/sample-model"
    dataset_name: str = "column-test-dataset"
    dataset_version: str = "v1"
    metadata: dict[str, Any] = field(default_factory=dict)
    n_sessions: int = 30
    cost_mean_usd: float = 0.02
    cost_stddev_pct: float = 0.4
    latency_mean_ms: int = 1500
    latency_stddev_ms: int = 400
    prompt_tokens_mean: int = 600
    completion_tokens_mean: int = 200


@dataclass
class GroupSpec:
    name: str
    description: str
    evaluations: list[EvaluationSpec]


# ---------------------------------------------------------------------------
# The column-test evaluators
# ---------------------------------------------------------------------------
#
# Each evaluator name states the value its column should show. Reuse the same
# EvaluatorSpec object across evaluations so it forms one shared column.

# Percentage columns (NUMERIC in [0, 1] -> rendered as "N.N%").
PCT_95 = EvaluatorSpec(name="pct_95", data_type="NUMERIC", mean=0.95)
PCT_50 = EvaluatorSpec(name="pct_50", data_type="NUMERIC", mean=0.50)
PCT_08 = EvaluatorSpec(name="pct_08", data_type="NUMERIC", mean=0.08)

# Boolean pass-rate column (BOOLEAN 0/1 -> mean is the pass fraction -> "80.0%").
PASS_RATE_80 = EvaluatorSpec(name="pass_rate_80", data_type="BOOLEAN", mean=0.80)

# Raw rubric-number columns (NUMERIC on a >1 scale -> rendered as "N.NNN").
RUBRIC_1TO5 = EvaluatorSpec(name="rubric_1to5", data_type="NUMERIC", mean=4.2, scale_max=5.0)
RUBRIC_1TO10 = EvaluatorSpec(name="rubric_1to10", data_type="NUMERIC", mean=7.5, scale_max=10.0)

# Present on one evaluation only, so the other rows render an empty "-".
SPARSE_PCT_66 = EvaluatorSpec(name="sparse_pct_66", data_type="NUMERIC", mean=0.66)

# Non-scored types: ingested, but excluded from the rollup so they never become
# score columns. Included to prove the range and document the exclusion.
CATEGORICAL_VERDICT = EvaluatorSpec(
    name="categorical_verdict",
    data_type="CATEGORICAL",
    categories=("pass", "fail", "partial"),
)
TEXT_RATIONALE = EvaluatorSpec(
    name="text_rationale",
    data_type="TEXT",
    text_samples=(
        "Answer matched the reference.",
        "Missed a required citation.",
        "Partially correct; minor omission.",
    ),
)

# Every evaluator that produces a score column, minus the sparse one.
_DENSE_SCORE_EVALUATORS = [PCT_95, PCT_50, PCT_08, PASS_RATE_80, RUBRIC_1TO5, RUBRIC_1TO10]
_NON_SCORED = [CATEGORICAL_VERDICT, TEXT_RATIONALE]

COLUMN_TEST_GROUP = GroupSpec(
    name=GROUP_NAME,
    description=GROUP_DESCRIPTION,
    evaluations=[
        # Row 1: runs every evaluator, including the sparse one and the two
        # non-scored types. This is the only row where `sparse_pct_66` resolves.
        EvaluationSpec(
            name="col-test-full-coverage",
            description="Runs every evaluator: all score columns populated, plus categorical/text.",
            evaluators=[*_DENSE_SCORE_EVALUATORS, SPARSE_PCT_66, *_NON_SCORED],
            n_sessions=30,
            cost_mean_usd=0.03,
            latency_mean_ms=2600,
        ),
        # Row 2: same score evaluators but WITHOUT the sparse one -> the
        # `sparse_pct_66` column renders "-" for this row.
        EvaluationSpec(
            name="col-test-numeric-boolean",
            description="Percentage + pass-rate + rubric columns; omits sparse_pct_66 to show an empty cell.",
            evaluators=[*_DENSE_SCORE_EVALUATORS, *_NON_SCORED],
            n_sessions=30,
            cost_mean_usd=0.02,
            latency_mean_ms=1800,
        ),
        # Row 3: only the rubric evaluators -> every percentage / pass-rate /
        # sparse column renders "-" here, isolating the raw-number rendering.
        EvaluationSpec(
            name="col-test-rubrics-only",
            description="Only the 1-5 and 1-10 rubric columns; all percentage/boolean cells render empty.",
            evaluators=[RUBRIC_1TO5, RUBRIC_1TO10],
            n_sessions=30,
            cost_mean_usd=0.05,
            latency_mean_ms=3400,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete this script's group ('Experiment column test') and its evaluations, then "
            "re-seed. Scoped to this script only — other groups are left alone."
        ),
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    _preflight(base_url)

    with httpx.Client(timeout=10.0) as client:
        if args.reset:
            _reset_group(client, base_url, args.workspace)
        seed(client, base_url, args.workspace)


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


def seed(client: httpx.Client, base_url: str, workspace: str) -> None:
    """Seed the single column-test group. No-op if the group already exists."""
    print("=== Seeding evaluator column-type showcase ===")
    base_started_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=6)

    group_id, created = _create_group_if_missing(client, base_url, workspace, COLUMN_TEST_GROUP)
    if not created or group_id is None:
        print(f"[skip] group '{COLUMN_TEST_GROUP.name}' already exists; leaving it alone. Use --reset to rebuild it.")
        return

    evaluations_created = 0
    sessions_seeded = 0
    print(f"\n[group] {COLUMN_TEST_GROUP.name}  ({len(COLUMN_TEST_GROUP.evaluations)} evaluations)")
    for exp_spec in COLUMN_TEST_GROUP.evaluations:
        cols = ", ".join(e.name for e in exp_spec.evaluators)
        print(f"  [evaluation] {exp_spec.name}  n_sessions={exp_spec.n_sessions}")
        print(f"      evaluators: {cols}")
        _create_evaluation(client, base_url, workspace, exp_spec, group_id=group_id)
        _seed_sessions(client, base_url, workspace, exp_spec, base_started_at)
        evaluations_created += 1
        sessions_seeded += exp_spec.n_sessions

    print(
        f"\n=== Done. group: '{COLUMN_TEST_GROUP.name}'. "
        f"evaluations: {evaluations_created} created. sessions: {sessions_seeded} ingested. ==="
    )


def _create_group_if_missing(
    client: httpx.Client, base_url: str, workspace: str, spec: GroupSpec
) -> tuple[str | None, bool]:
    """Returns (group_id, created). On 409, returns (None, False) and leaves the existing group alone."""
    url = _intake_url(base_url, workspace, "/experiment-groups")
    body = {"name": spec.name, "description": spec.description}
    response = client.post(url, json=body)
    if response.status_code == 409:
        return None, False
    response.raise_for_status()
    return response.json()["id"], True


def _create_evaluation(
    client: httpx.Client,
    base_url: str,
    workspace: str,
    spec: EvaluationSpec,
    *,
    group_id: str,
) -> None:
    """POST an evaluation. Errors on conflict — callers must guarantee the evaluation doesn't exist."""
    body: dict[str, Any] = {
        "name": spec.name,
        "dataset_name": spec.dataset_name,
        "dataset_version": spec.dataset_version,
        "experiment_group_id": group_id,
        "description": spec.description,
        "metadata": {
            "seeded_by": SEEDED_BY,
            "model_name": spec.model_name,
            **spec.metadata,
        },
    }
    response = client.post(_intake_url(base_url, workspace, "/evaluations"), json=body)
    response.raise_for_status()


def _seed_sessions(
    client: httpx.Client,
    base_url: str,
    workspace: str,
    spec: EvaluationSpec,
    base_started_at: datetime,
) -> None:
    """Ingest N sessions via ATIF, then attach each evaluator's per-session result."""
    # Deterministic per-evaluation so re-runs produce the same values.
    rng = random.Random(f"col-test:{spec.name}")

    atif_url = _intake_url(base_url, workspace, "/ingest/atif")
    eval_url = _intake_url(base_url, workspace, "/evaluator-results")

    for i in range(spec.n_sessions):
        cost_usd = max(0.0005, rng.gauss(spec.cost_mean_usd, spec.cost_mean_usd * spec.cost_stddev_pct))
        latency_ms = max(100, int(rng.gauss(spec.latency_mean_ms, spec.latency_stddev_ms)))
        prompt_tokens = max(10, int(rng.gauss(spec.prompt_tokens_mean, spec.prompt_tokens_mean * 0.25)))
        completion_tokens = max(5, int(rng.gauss(spec.completion_tokens_mean, spec.completion_tokens_mean * 0.3)))

        test_case_id = f"case-{i:04d}"
        run_id = f"run-{i // 25:02d}"
        offset_seconds = (i / max(1, spec.n_sessions)) * 5.5 * 3600

        atif_body = _demo_atif_body(
            base_started_at=base_started_at,
            evaluation_id=spec.name,
            run_id=run_id,
            test_case_id=test_case_id,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            offset_seconds=offset_seconds,
            agent_name=spec.agent_name,
            agent_version=spec.agent_version,
            model_name=spec.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        response = client.post(atif_url, json=atif_body)
        response.raise_for_status()

        session_id = atif_body["session_id"]
        # Loose-target span_id: evaluator_results joins by session_id; span_id isn't validated.
        synthetic_span_id = f"{session_id}-root"

        for evaluator in spec.evaluators:
            body = _evaluator_result_body(evaluator, i, spec.n_sessions, synthetic_span_id, session_id, rng)
            eval_response = client.post(eval_url, json=body)
            eval_response.raise_for_status()

        if (i + 1) % 25 == 0 or i + 1 == spec.n_sessions:
            print(f"      {i + 1}/{spec.n_sessions} sessions")


def _evaluator_result_body(
    evaluator: EvaluatorSpec,
    session_index: int,
    n_sessions: int,
    span_id: str,
    session_id: str,
    rng: random.Random,
) -> dict[str, Any]:
    """Build a POST /evaluator-results body for one evaluator on one session.

    Score values are deterministic so each column lands exactly on the value in
    the evaluator's name: NUMERIC uses the target mean directly; BOOLEAN emits
    exactly ``round(mean * n)`` passing sessions.
    """
    base: dict[str, Any] = {
        "span_id": span_id,
        "session_id": session_id,
        "name": evaluator.name,
        "data_type": evaluator.data_type,
    }

    if evaluator.data_type == "NUMERIC":
        value = evaluator.mean if evaluator.stddev == 0 else rng.gauss(evaluator.mean, evaluator.stddev)
        base["value"] = round(_clip(value, evaluator.scale_max), 6)
        return base

    if evaluator.data_type == "BOOLEAN":
        # Emit exactly round(mean * n) passing sessions so the pass-rate is exact.
        n_pass = round(evaluator.mean * n_sessions)
        base["value"] = 1.0 if session_index < n_pass else 0.0
        return base

    if evaluator.data_type == "CATEGORICAL":
        base["string_value"] = evaluator.categories[session_index % len(evaluator.categories)]
        return base

    if evaluator.data_type == "TEXT":
        base["string_value"] = evaluator.text_samples[session_index % len(evaluator.text_samples)]
        return base

    raise ValueError(f"Unknown data_type: {evaluator.data_type}")


def _demo_atif_body(
    *,
    base_started_at: datetime,
    evaluation_id: str,
    run_id: str,
    test_case_id: str,
    cost_usd: float,
    latency_ms: int,
    offset_seconds: float,
    agent_name: str,
    agent_version: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    session_started_at = base_started_at + timedelta(seconds=offset_seconds)
    finished_at = session_started_at + timedelta(milliseconds=latency_ms)
    session_id = f"{evaluation_id}-{run_id}-{test_case_id}"
    # `extra.verifier` carries the timing block (used by the rollup for session latency).
    # We omit `extra.verifier_result` so ATIF ingest doesn't auto-create a `harbor.verifier`
    # evaluator alongside our cleanly-named ones from POST /evaluator-results.
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": session_id,
        "evaluation_context": {
            "evaluation_id": evaluation_id,
            "test_case_id": test_case_id,
        },
        "extra": {
            "task_id": test_case_id,
            "task_name": test_case_id,
            "verifier": {
                "started_at": _iso(session_started_at),
                "finished_at": _iso(finished_at),
            },
        },
        "agent": {
            "name": agent_name,
            "version": agent_version,
            "model_name": model_name,
        },
        "steps": [
            {
                "step_id": 1,
                "timestamp": _iso(session_started_at),
                "source": "user",
                "message": f"test case: {test_case_id}",
            },
            {
                "step_id": 2,
                "timestamp": _iso(finished_at),
                "source": "agent",
                "model_name": model_name,
                "message": f"solved {test_case_id}",
                "metrics": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost_usd,
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Reset (--reset): scoped to this script's group only
# ---------------------------------------------------------------------------


def _reset_group(client: httpx.Client, base_url: str, workspace: str) -> None:
    """Delete this script's evaluations and group. Leaves all other groups intact."""
    print(f"=== --reset: deleting '{GROUP_NAME}' and its evaluations in workspace '{workspace}' ===")
    deleted_evaluations = 0
    for exp_spec in COLUMN_TEST_GROUP.evaluations:
        if _delete(client, base_url, workspace, f"/evaluations/{exp_spec.name}"):
            deleted_evaluations += 1
    deleted_group = _delete(client, base_url, workspace, f"/experiment-groups/{GROUP_NAME}")
    print(f"deleted {deleted_evaluations} evaluation(s) and {1 if deleted_group else 0} group(s)\n")


def _delete(client: httpx.Client, base_url: str, workspace: str, suffix: str) -> bool:
    response = client.delete(_intake_url(base_url, workspace, suffix))
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _clip(value: float, scale_max: float) -> float:
    return max(0.0, min(scale_max, value))


def _preflight(base_url: str) -> None:
    try:
        response = httpx.get(_replace_path(base_url, "/openapi.json"), timeout=2.0)
        response.raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Cannot reach NeMo Platform at {base_url}: {exc}") from exc


def _intake_url(base_url: str, workspace: str, suffix: str) -> str:
    return f"{base_url}/apis/intake/v2/workspaces/{workspace}{suffix}"


def _replace_path(base_url: str, path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
