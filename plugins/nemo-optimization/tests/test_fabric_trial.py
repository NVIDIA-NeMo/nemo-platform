# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalScoreStatus, AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus
from nemo_evaluator_sdk.metrics.protocol import MetricOutput
from nemo_evaluator_sdk.metrics.tunable_rag_evaluator import TunableRagEvaluatorMetric
from nemo_evaluator_sdk.values.evidence import EVIDENCE_FORMAT_ATIF, EVIDENCE_TRACE, CandidateEvidence, EvidenceDescriptor
from nemo_optimization.backends.optuna.fabric_trial import (
    FabricTrialEvaluator,
    build_agent_eval_tasks,
    reduce_agent_eval_scores,
)
from nemo_optimization.backends.optuna.study_driver import StudyDriverError


def _payload(dataset: Path) -> dict[str, Any]:
    return {
        "schema_version": "fabric.agent/v1alpha1",
        "metadata": {"name": "demo"},
        "harness": {"adapter_id": "nvidia.fabric.langchain.react"},
        "models": {
            "default": {"provider": "openai", "model": "agent", "base_url": "http://agent/v1"},
            "judge": {"provider": "openai", "model": "judge", "base_url": "http://judge/v1"},
        },
        "eval": {
            "general": {
                "dataset": {"file_path": str(dataset)},
                "max_concurrency": 1,
            },
            "fabric": {
                "profiles": [{"schema_version": "fabric.profile/v1alpha1", "metadata": {"name": "base"}}],
                "capture_trajectory": True,
                "timeout_s": 30,
            },
            "evaluators": {
                "accuracy": {
                    "_type": "tunable_rag_evaluator",
                    "llm_name": "judge",
                    "default_scoring": True,
                    "judge_llm_prompt": "",
                }
            },
        },
    }


def test_build_agent_eval_tasks_from_json_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "rows.json"
    dataset.write_text('[{"id": "1", "question": "q?", "answer": "a"}]\n', encoding="utf-8")

    tasks = build_agent_eval_tasks(_payload(dataset))

    assert len(tasks) == 1
    assert tasks[0].id == "1"
    assert tasks[0].inputs == {"question": "q?"}
    assert tasks[0].reference == {"answer": "a"}
    assert isinstance(tasks[0].metrics[0], TunableRagEvaluatorMetric)


def test_build_agent_eval_tasks_preserves_judge_api_key_env(tmp_path: Path) -> None:
    dataset = tmp_path / "rows.json"
    dataset.write_text('[{"id": "1", "question": "q?", "answer": "a"}]\n', encoding="utf-8")
    payload = _payload(dataset)
    payload["models"]["judge"]["api_key_env"] = "NVIDIA_API_KEY"

    tasks = build_agent_eval_tasks(payload)

    metric = tasks[0].metrics[0]
    assert isinstance(metric, TunableRagEvaluatorMetric)
    assert metric.model.api_key_secret is not None
    assert metric.model.api_key_secret.root == "NVIDIA_API_KEY"


def test_reduce_agent_eval_scores_averages_requested_output() -> None:
    scores = [
        AgentEvalTaskScore(
            id="s1",
            run_id="r",
            task_id="1",
            trial_id="t1",
            metric_type="tunable-rag-evaluator",
            status=AgentEvalScoreStatus.COMPLETED,
            outputs=[MetricOutput(name="average_score", value=0.25)],
        ),
        AgentEvalTaskScore(
            id="s2",
            run_id="r",
            task_id="2",
            trial_id="t2",
            metric_type="tunable-rag-evaluator",
            status=AgentEvalScoreStatus.COMPLETED,
            outputs=[MetricOutput(name="average_score", value=0.75)],
        ),
    ]

    assert reduce_agent_eval_scores(scores, ["average_score"]) == {"average_score": 0.5}


def test_reduce_agent_eval_scores_rejects_missing_metric() -> None:
    with pytest.raises(StudyDriverError, match="did not produce"):
        reduce_agent_eval_scores([], ["average_score"])


def test_fabric_trial_evaluator_invokes_agent_evaluator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dataset = tmp_path / "rows.json"
    dataset.write_text('[{"id": "1", "question": "q?", "answer": "a"}]\n', encoding="utf-8")
    captured: dict[str, Any] = {}

    class FakeRuntime:
        def __init__(self, **kwargs: Any) -> None:
            captured["runtime"] = kwargs

    class FakeAgentEvaluator:
        def run_sync(self, *, tasks, target, config):  # noqa: ANN001
            captured["tasks"] = tasks
            captured["target"] = target
            captured["config"] = config
            trial = AgentEvalTrial(
                id="1:fabric",
                task_id="1",
                status=AgentEvalTrialStatus.COMPLETED,
                evidence=CandidateEvidence(
                    descriptors={
                        EVIDENCE_TRACE: EvidenceDescriptor(
                            kind=EVIDENCE_TRACE,
                            format=EVIDENCE_FORMAT_ATIF,
                            ref="/tmp/trace.atif.json",
                        )
                    }
                ),
                output={"output_text": "answer"},
            )
            score = AgentEvalTaskScore(
                id="s",
                run_id="r",
                task_id="1",
                trial_id="1:fabric",
                metric_type="tunable-rag-evaluator",
                status=AgentEvalScoreStatus.COMPLETED,
                outputs=[MetricOutput(name="average_score", value=0.9)],
            )
            return AgentEvalResult(
                run_id="r",
                tasks=list(tasks),
                trials=[trial],
                scores=[score],
                summary=AgentEvalSummary.from_scores([score], tasks=tasks),
                benchmark={},
            )

    monkeypatch.setattr("nemo_optimization.backends.optuna.fabric_trial.FabricAgentRuntime", FakeRuntime)
    monkeypatch.setattr("nemo_optimization.backends.optuna.fabric_trial.AgentEvaluator", FakeAgentEvaluator)

    evaluator = FabricTrialEvaluator(
        payload=_payload(dataset),
        metric_names=["average_score"],
        output_dir=tmp_path / "out",
        experiment_id="exp-test",
    )

    scores = evaluator.evaluate(
        trial_number=7,
        suggestions={"models.default.temperature": 0.2},
        trial_overlay={"metadata": {"name": "trial-007"}},
        rep=0,
    )

    assert scores == {"average_score": 0.9}
    assert captured["runtime"]["trajectory_extra"] == {
        "nemo.optimizer.experiment_id": "exp-test",
        "nemo.optimizer.trial_number": 7,
        "nemo.optimizer.rep": 0,
    }
    assert captured["runtime"]["profiles"][-1] == {"name": "trial-007"}
    assert captured["runtime"]["config"]["models"]["default"]["temperature"] == 0.2
    assert "optimizer" not in captured["runtime"]["config"]
    assert "eval" not in captured["runtime"]["config"]
    assert (tmp_path / "out" / "trial_trace_map.json").is_file()
    trace_map = json.loads((tmp_path / "out" / "trial_trace_map.json").read_text(encoding="utf-8"))
    assert trace_map[0]["experiment_id"] == "exp-test"
    assert trace_map[0]["row_id"] == "1"
