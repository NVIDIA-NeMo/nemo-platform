# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise the example's reference metrics-over-evidence."""

import importlib.util
import json
from pathlib import Path

import pytest
from nemo_evaluator_sdk.execution.samples import build_metric_input
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

_MODULE_PATH = Path(__file__).resolve().parents[2] / "examples" / "run_agent_eval" / "example_metrics.py"
_spec = importlib.util.spec_from_file_location("example_metrics", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
example_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(example_metrics)


def _input_with_evidence(evidence: CandidateEvidence):
    return build_metric_input({"prompt": "q"}, {"evidence": evidence}, index=0)


@pytest.mark.asyncio
async def test_tests_pass_and_no_test_cheating(tmp_path: Path) -> None:
    initial = tmp_path / "initial"
    final = tmp_path / "final"
    for root in (initial, final):
        (root / "tests").mkdir(parents=True)
        (root / "tests" / "test_x.py").write_text("def test(): assert True", encoding="utf-8")
    (final / "solution.py").write_text("print('done')", encoding="utf-8")

    evidence = CandidateEvidence(
        descriptors={
            "initial_state": EvidenceDescriptor(kind="filesystem", ref=str(initial)),
            "final_state": EvidenceDescriptor(kind="filesystem", ref=str(final)),
        }
    )

    tests_pass = await example_metrics.TestsPassMetric(["test", "-f", "solution.py"]).compute_scores(
        _input_with_evidence(evidence)
    )
    assert tests_pass.outputs[0].value is True

    no_cheat = await example_metrics.NoTestCheatingMetric().compute_scores(_input_with_evidence(evidence))
    assert no_cheat.outputs[0].value is True

    # Mutating a protected test file flips no_test_cheating to False.
    (final / "tests" / "test_x.py").write_text("def test(): assert False", encoding="utf-8")
    evidence_cheated = CandidateEvidence(
        descriptors={
            "initial_state": EvidenceDescriptor(kind="filesystem", ref=str(initial)),
            "final_state": EvidenceDescriptor(kind="filesystem", ref=str(final)),
        }
    )
    cheated = await example_metrics.NoTestCheatingMetric().compute_scores(_input_with_evidence(evidence_cheated))
    assert cheated.outputs[0].value is False


@pytest.mark.asyncio
async def test_inefficient_retry_loop(tmp_path: Path) -> None:
    def trajectory(repeats: int) -> dict:
        calls = [
            {"tool_call_id": f"c{i}", "function_name": "search", "arguments": {"q": "same"}} for i in range(repeats)
        ]
        return {
            "schema_version": "ATIF-v1.7",
            "agent": {"name": "demo", "version": "1.0"},
            "steps": [{"step_id": 1, "source": "agent", "message": "", "tool_calls": calls}],
        }

    looping = tmp_path / "loop.json"
    looping.write_text(json.dumps(trajectory(5)), encoding="utf-8")
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps(trajectory(1)), encoding="utf-8")

    metric = example_metrics.InefficientRetryLoopMetric(threshold=2)

    loop_result = await metric.compute_scores(
        _input_with_evidence(
            CandidateEvidence(descriptors={"trace": EvidenceDescriptor(kind="trace", ref=str(looping))})
        )
    )
    assert loop_result.outputs[0].value is False
    assert loop_result.outputs[1].value == 5

    clean_result = await metric.compute_scores(
        _input_with_evidence(CandidateEvidence(descriptors={"trace": EvidenceDescriptor(kind="trace", ref=str(clean))}))
    )
    assert clean_result.outputs[0].value is True
