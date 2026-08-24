# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the reusable agent-eval metrics and the TrialMeasurements contract."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric, unbundle_metric
from nemo_evaluator.shared.metric_bundles.inline import InlineMetricBundlePackager
from nemo_evaluator_sdk.agent_eval.metrics import (
    AgentPhaseSuccessMetric,
    EvidencePresenceMetric,
    SkillUsedMetric,
    TrialMeasurements,
)
from nemo_evaluator_sdk.agent_eval.trials import standard_evidence_descriptors
from nemo_evaluator_sdk.metrics.protocol import CandidateOutput, DatasetRow, MetricInput
from nemo_evaluator_sdk.metrics.runner_rewards import GymRewardMetric, HarborRewardMetric
from nemo_evaluator_sdk.values.evidence import CandidateEvidence
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_agent_phase_success_metric_reads_metadata_and_bundles_inline() -> None:
    """``type`` is a fixed discriminator now, which is what makes the metric inline-bundleable.

    It used to be overridable per subclass so callers could namespace it. That is incompatible with
    ``MetricsUnion``'s ``Field(discriminator="type")``, and the override bought less than the
    cloudpickle opt-in it cost: storing this metric on a task previously required shipping custom
    code.
    """
    metric = AgentPhaseSuccessMetric()
    assert metric.type == "agent_phase_success"
    ok = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(metadata={"agent_ok": True}))
    )
    assert ok.outputs[0].value is True

    bundle = bundle_metric(metric, InlineMetricBundlePackager())
    assert bundle.payload.kind == "inline", "a built-in metric must not need the cloudpickle opt-in"
    assert type(unbundle_metric(bundle)) is AgentPhaseSuccessMetric


@pytest.mark.asyncio
async def test_evidence_presence_metric_scores_over_evidence(tmp_path: Path) -> None:
    final_state = tmp_path / "workspace"
    final_state.mkdir()
    (final_state / "result.txt").write_text("done", encoding="utf-8")
    evidence = CandidateEvidence(
        descriptors=standard_evidence_descriptors(logs_dir=tmp_path / "agent", final_state_dir=final_state)
    )

    metric = EvidencePresenceMetric()
    present = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(evidence=evidence))
    )
    assert present.outputs[0].value is True

    # Empty workspace -> non-empty requirement fails; no evidence -> False.
    (final_state / "result.txt").unlink()
    empty = await metric.compute_scores(
        MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput(evidence=evidence))
    )
    assert empty.outputs[0].value is False
    missing = await metric.compute_scores(MetricInput(row=DatasetRow(data={}), candidate=CandidateOutput()))
    assert missing.outputs[0].value is False


def test_from_metadata_reads_tokens_runtime_reward() -> None:
    measurements = TrialMeasurements.from_metadata(
        {
            "total_tokens": 120,
            "prompt_tokens": 80,
            "completion_tokens": 40,
            "runtime_sec": 4.5,
            "cost_usd": 0.134,
            "reward": 1,
            "passed": True,
        }
    )
    assert measurements.total_tokens == 120
    assert measurements.runtime_sec == 4.5
    assert measurements.cost_usd == 0.134
    assert measurements.reward == 1.0
    assert measurements.passed is True


def test_from_metadata_applies_fallbacks_and_ignores_bad_types() -> None:
    # duration_ms -> runtime_sec, passed -> reward, bool is not a token count.
    measurements = TrialMeasurements.from_metadata({"duration_ms": 2500, "passed": False, "total_tokens": True})
    assert measurements.runtime_sec == 2.5
    assert measurements.reward == 0.0
    assert measurements.total_tokens is None

    empty = TrialMeasurements.from_metadata(None)
    assert empty.reward is None and empty.runtime_sec is None and empty.cost_usd is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, 10**1000])
def test_from_metadata_rejects_unserialisable_cost(bad: object) -> None:
    # A cost the wire cannot carry would fail the publish of an otherwise good trial. 10**1000 is
    # an int no float can represent, which reaches here from any harness that reports JSON numbers.
    assert TrialMeasurements.from_metadata({"cost_usd": bad}).cost_usd is None


@pytest.mark.parametrize(
    "bad",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        10**1000,
        # These reach a float only through coercion, so they slip past any check made before it.
        "nan",
        "inf",
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_direct_construction_rejects_unserialisable_cost(bad: object) -> None:
    # from_metadata is not the only way in, so the model itself has to hold the invariant.
    with pytest.raises(ValidationError):
        TrialMeasurements(cost_usd=bad)


@pytest.mark.parametrize("good", [0.134, 0, "0.5", Decimal("1.25")])
def test_direct_construction_still_accepts_a_finite_cost(good: object) -> None:
    # Rejecting non-finite values must not cost the ordinary coercion of a finite one.
    assert TrialMeasurements(cost_usd=good).cost_usd == float(good)


@pytest.mark.parametrize(
    ("factory", "expected_type"),
    [
        (lambda: GymRewardMetric(output_name="score"), "gym_reward"),
        (lambda: HarborRewardMetric(output_name="score"), "harbor_reward"),
        (AgentPhaseSuccessMetric, "agent_phase_success"),
        (lambda: EvidencePresenceMetric(evidence_name="workspace", require_non_empty=False), "evidence_presence"),
        (lambda: SkillUsedMetric(trace_evidence="atif"), "skill_used"),
    ],
)
def test_runner_and_agent_eval_metrics_are_built_in(factory, expected_type: str) -> None:
    """Each of these can be stored on a task without the cloudpickle opt-in.

    Non-default configuration is used deliberately: a metric that survives bundling only with its
    defaults would still lose the caller's settings on the way to a stored task.
    """
    metric = factory()
    assert metric.type == expected_type

    bundle = bundle_metric(metric, InlineMetricBundlePackager())
    assert bundle.payload.kind == "inline"

    restored = unbundle_metric(bundle)
    assert type(restored) is type(metric)
    assert restored.model_dump() == metric.model_dump()


def test_built_in_metrics_reject_a_caller_supplied_type() -> None:
    """The discriminator is fixed. Callers used to namespace it, which the union cannot express."""
    with pytest.raises(ValidationError):
        GymRewardMetric(type="my_namespaced_reward")
