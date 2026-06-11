# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval import AgentEvalAttempt, AgentEvalTask, AgentEvaluator, AgentOutput
from nemo_evaluator_sdk.agent_eval.benchmarks import AgentEvalBenchmarkLoadConfig
from nemo_evaluator_sdk.values import Model

profbench = importlib.import_module("packages.nemo_evaluator_sdk.examples.profbench.profbench")
profbench_dashboard = importlib.import_module("packages.nemo_evaluator_sdk.examples.profbench.dashboard")
profbench_examples = importlib.import_module("packages.nemo_evaluator_sdk.examples.profbench.examples")


class _FakeUrlopenResponse:
    def __init__(self, body: str) -> None:
        self._body = body
        self.headers = {"ETag": "test-etag", "x-repo-commit": "test-commit"}

    def __enter__(self) -> "_FakeUrlopenResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


def _write_profbench_fixture(path: Path) -> Path:
    row = {
        "task_id": "pb-1",
        "domain": "Chemistry PhD",
        "prompt": "Explain the result.",
        "o3_response": "Response A",
        "r1-0528_response": "Response B",
        "grok4_response": "Response C",
        "rubrics": [
            {
                "criterion_description": "Includes the main mechanism.",
                "criterion_weight": "Critical",
                "criterion_type": ["Correctness", "Reasoning"],
                "o3_fulfilment": True,
                "r1-0528_fulfilment": False,
                "grok4_fulfilment": True,
            },
            {
                "criterion_description": "Mentions the limitation.",
                "criterion_weight": "Major",
                "criterion_type": "Completeness",
                "o3_fulfilment": False,
                "r1-0528_fulfilment": True,
                "grok4_fulfilment": True,
            },
        ],
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def _stub_remote_profbench_source(monkeypatch: pytest.MonkeyPatch, body: str) -> str:
    remote_source = "https://example.test/profbench/test.jsonl"

    def fake_urlopen(request: Any, timeout: int) -> _FakeUrlopenResponse:
        assert request.full_url == remote_source
        assert timeout == 60
        return _FakeUrlopenResponse(body)

    monkeypatch.setattr(profbench, "urlopen", fake_urlopen)
    return remote_source


class _FakeLiveTarget:
    async def run_tasks(self, tasks: list[AgentEvalTask], config: Any | None = None) -> list[AgentEvalAttempt]:
        del config
        return [
            AgentEvalAttempt(id=f"{task.id}:generated", task_id=task.id, output=AgentOutput(text="Generated answer."))
            for task in tasks
        ]


class _FakeProfBenchModelJudge:
    def __init__(self, *, model: Model) -> None:
        self.model = model

    async def judge(self, request: Any) -> Any:
        return profbench.ProfBenchJudgeDecision(
            fulfilled=request.criterion_id.endswith("criterion-1"),
            reason=f"judged {request.criterion_id}",
        )


def test_load_profbench_expands_tasks_attempts_and_line_index(tmp_path: Path) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")

    benchmark = profbench.load_profbench(fixture)

    assert benchmark.metadata["record_count"] == 1
    assert [attempt.metadata["model_id"] for attempt in benchmark.attempts] == ["o3", "r1-0528", "grok4"]

    metric = benchmark.tasks[0].metrics[0]
    assert isinstance(metric, profbench.ProfBenchRubricMetric)
    assert [criterion.points for criterion in metric.criteria] == [
        profbench.PROFBENCH_WEIGHT_POINTS["Critical"],
        profbench.PROFBENCH_WEIGHT_POINTS["Major"],
    ]
    assert [criterion.id for criterion in metric.criteria] == ["pb-1:criterion-1", "pb-1:criterion-2"]
    assert metric.criteria[0].line_number == 1
    assert metric.criteria[0].json_path == "$.rubrics[0]"


def test_profbench_benchmark_adapter_loads_recorded_attempts(tmp_path: Path) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    benchmark = profbench.ProfBenchAgentEvalBenchmark()

    bundle = benchmark.load(
        AgentEvalBenchmarkLoadConfig(
            source=fixture,
            limit=1,
            evidence_dir=tmp_path / "evidence",
        )
    )

    assert len(bundle.tasks) == 1
    assert bundle.attempts is not None
    assert [attempt.metadata["model_id"] for attempt in bundle.attempts] == ["o3", "r1-0528", "grok4"]
    assert bundle.metadata["benchmark"] == "ProfBench"


def test_profbench_benchmark_adapter_can_strip_cached_labels_for_live_scoring(tmp_path: Path) -> None:
    class FakeJudge:
        async def judge(self, request: Any) -> Any:
            return profbench.ProfBenchJudgeDecision(fulfilled=True, reason=f"judged {request.criterion_id}")

    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    benchmark = profbench.ProfBenchAgentEvalBenchmark(
        judge_factory=FakeJudge,
        include_cached_fulfilments=False,
        score_source="fresh_candidate_and_live_judge",
    )

    bundle = benchmark.load(
        AgentEvalBenchmarkLoadConfig(
            source=fixture,
            limit=1,
            evidence_dir=tmp_path / "evidence",
        )
    )

    assert len(bundle.tasks) == 1
    assert bundle.attempts is not None
    assert all("profbench_fulfilments" not in attempt.metadata for attempt in bundle.attempts)
    metric = bundle.tasks[0].metrics[0]
    assert isinstance(metric, profbench.ProfBenchRubricMetric)
    assert isinstance(metric.judge, FakeJudge)
    assert bundle.metadata["score_source"] == "fresh_candidate_and_live_judge"


def test_profbench_benchmark_adapter_writes_custom_reports(tmp_path: Path) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    benchmark = profbench.ProfBenchAgentEvalBenchmark()
    bundle = benchmark.load(
        AgentEvalBenchmarkLoadConfig(
            source=fixture,
        )
    )
    result = AgentEvaluator().run_sync(tasks=bundle.tasks, attempts=bundle.attempts)

    reports = benchmark.write_reports(result, tmp_path)

    assert [path.name for path in reports.paths] == ["sdk-report.html", "report.html"]
    assert (tmp_path / "sdk-report.html").is_file()
    assert (tmp_path / "report.html").is_file()


def test_profbench_baseline_scoring_creates_traceable_deductions(tmp_path: Path) -> None:
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)
    o3_result = next(row for row in result.results if row.attempt_id == "pb-1:o3")
    details_output = next(output for output in o3_result.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT)
    details = profbench.profbench_details(details_output)
    assert details is not None

    assert details.score == 4 / 7
    assert details.earned_points == 4
    assert details.max_points == 7
    assert len(details.deductions) == 1
    deduction = details.deductions[0]
    assert deduction.raw_points == 3
    assert deduction.normalized_impact == 3 / 7
    assert deduction.metadata["score_source"] == "dataset_label"
    assert deduction.evidence[0].line == 1
    assert deduction.evidence[0].json_path == "$.rubrics[1]"
    assert deduction.evidence[0].href().startswith("file://")
    assert "#L1" not in deduction.evidence[0].href()
    assert all(criterion.judge_reason is None for criterion in details.criterion_scores)
    assert {criterion.metadata["score_source"] for criterion in details.criterion_scores} == {"dataset_label"}


def test_evidence_locator_local_file_href_omits_dead_line_fragment(tmp_path: Path) -> None:
    evidence_file = tmp_path / "profbench-dataset.jsonl"
    evidence_file.write_text("{}\n", encoding="utf-8")

    locator = profbench.EvidenceLocator(kind="profbench", uri=str(evidence_file), line=1, json_path="$.rubrics[0]")

    assert locator.href() == evidence_file.as_uri()
    assert locator.href(base_dir=tmp_path) == "profbench-dataset.jsonl"


def test_profbench_live_judge_mode_scores_recorded_attempts_without_cached_labels(tmp_path: Path) -> None:
    class FakeJudge:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        async def judge(self, request: Any) -> Any:
            self.requests.append(request)
            return profbench.ProfBenchJudgeDecision(
                fulfilled=request.criterion_id.endswith("criterion-1"),
                reason=f"judged {request.criterion_id}",
            )

    judge = FakeJudge()
    benchmark = profbench.load_profbench(
        _write_profbench_fixture(tmp_path / "profbench.jsonl"),
        judge=judge,
        include_cached_fulfilments=False,
    )

    assert all("profbench_fulfilments" not in attempt.metadata for attempt in benchmark.attempts)

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)
    o3_result = next(row for row in result.results if row.attempt_id == "pb-1:o3")
    details_output = next(output for output in o3_result.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT)
    details = profbench.profbench_details(details_output)
    assert details is not None

    assert details.score == 4 / 7
    assert len(judge.requests) == 6
    assert {criterion.metadata["score_source"] for criterion in details.criterion_scores} == {"judge"}
    assert [criterion.judge_reason for criterion in details.criterion_scores] == [
        "judged pb-1:criterion-1",
        "judged pb-1:criterion-2",
    ]


def test_agent_evaluator_scores_loaded_profbench_baselines(tmp_path: Path) -> None:
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)

    assert result.summary.task_count == 1
    assert result.summary.attempt_count == 3
    assert result.summary.metric_scores == {"profbench_rubric": {"profbench": 2 / 3}}


def test_profbench_dashboard_renders_rubric_report(tmp_path: Path) -> None:
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))
    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)

    html = profbench_dashboard.render_profbench_dashboard(result, evidence_base_dir=tmp_path)

    assert "ProfBench Agent Eval Report" in html
    assert "Highest-Impact Failures" in html
    assert "Task Details" in html
    assert "criterion-2" in html
    assert "Criterion was not fulfilled" in html
    assert "Chemistry PhD" in html
    assert "Dataset fulfilment label" not in html
    assert "dataset_label" in html
    assert 'href="profbench.jsonl"' in html
    assert "profbench.jsonl#L1" not in html

    report_path = profbench_dashboard.write_profbench_dashboard(result, tmp_path / "report.html")
    assert report_path.read_text(encoding="utf-8") == html


def test_profbench_example_writes_sdk_and_profbench_dashboards(tmp_path: Path) -> None:
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))
    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)

    sdk_path, default_path = profbench_dashboard.write_example_dashboards(result, tmp_path)

    assert "Agent Eval Report" in sdk_path.read_text(encoding="utf-8")
    assert "ProfBench Agent Eval Report" in default_path.read_text(encoding="utf-8")
    assert not (tmp_path / "profbench-report.html").exists()


def test_profbench_examples_run_instance_id_has_expected_format() -> None:
    assert re.fullmatch(r"\d{8}_\d{6}_\d{5}_[0-9a-f]{6}", profbench_examples._new_profbench_run_instance_id())


def test_profbench_examples_parser_uses_short_runtime_names_and_agent_model() -> None:
    docker_args = profbench_examples._parse_args(["docker", "--agent-model", "gpt-test"])
    local_args = profbench_examples._parse_args(["local", "--agent-model", "gpt-5.5"])

    assert docker_args.example == "docker"
    assert docker_args.agent_model == "gpt-test"
    assert not hasattr(docker_args, "target_model")
    assert local_args.example == "local"
    assert local_args.agent_model == "gpt-5.5"

    with pytest.raises(SystemExit):
        profbench_examples._parse_args(["docker-sandbox"])
    with pytest.raises(SystemExit):
        profbench_examples._parse_args(["local-codex"])
    with pytest.raises(SystemExit):
        profbench_examples._parse_args(["docker", "--target-model", "gpt-test"])


@pytest.mark.asyncio
async def test_profbench_offline_example_function_writes_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    run_instance_id = "20260608_162200_28290_40da8e"
    output_root = tmp_path / "offline"
    monkeypatch.setattr(profbench_examples, "_new_profbench_run_instance_id", lambda: run_instance_id)

    result, reports = await profbench_examples.run_offline_profbench_adapter_smoke(
        output_dir=output_root,
        run_id="offline-smoke",
        source=fixture,
        limit=1,
    )

    assert result.summary.task_count == 1
    assert result.summary.attempt_count == 3
    assert [path.name for path in reports.paths] == ["sdk-report.html", "report.html"]
    assert result.run_id == "offline-smoke"
    assert result.output_dir == output_root / run_instance_id
    assert (output_root / run_instance_id / "run.json").is_file()
    assert (output_root / run_instance_id / "report.html").is_file()


@pytest.mark.asyncio
async def test_profbench_docker_example_function_uses_codex_runtime_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    run_instance_id = "20260608_162200_28290_40da8e"
    output_root = tmp_path / "docker"

    def fake_resolve_codex_target(*, runtime: Any, model: str | None, output_dir: Path) -> tuple[Any, str, str]:
        assert runtime == profbench_examples.RuntimeChoice.DOCKER
        assert model == "gpt-test"
        assert output_dir == output_root / run_instance_id
        return _FakeLiveTarget(), "codex_docker_cli_candidate_and_live_judge", "docker_cli"

    monkeypatch.setattr(profbench_examples, "_new_profbench_run_instance_id", lambda: run_instance_id)
    monkeypatch.setattr(profbench_examples, "resolve_codex_target", fake_resolve_codex_target)
    monkeypatch.setattr(profbench_examples, "ProfBenchModelJudge", _FakeProfBenchModelJudge)

    result, reports = await profbench_examples.run_docker_sandbox_profbench_live_candidate_smoke(
        output_dir=output_root,
        run_id="docker-smoke",
        source=fixture,
        limit=1,
        agent_model="gpt-test",
    )

    assert result.summary.task_count == 1
    assert result.summary.attempt_count == 1
    assert result.output_dir == output_root / run_instance_id
    assert [path.name for path in reports.paths] == ["sdk-report.html", "report.html"]


@pytest.mark.asyncio
async def test_profbench_local_codex_example_function_uses_local_codex_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    run_instance_id = "20260608_162200_28290_40da8e"
    output_root = tmp_path / "local"

    def fake_resolve_codex_target(*, runtime: Any, model: str | None, output_dir: Path) -> tuple[Any, str, str]:
        assert runtime == profbench_examples.RuntimeChoice.LOCAL
        assert model == "gpt-5.5"
        assert output_dir == output_root / run_instance_id
        return _FakeLiveTarget(), "codex_cli_candidate_and_live_judge", "local_cli"

    monkeypatch.setattr(profbench_examples, "_new_profbench_run_instance_id", lambda: run_instance_id)
    monkeypatch.setattr(profbench_examples, "resolve_codex_target", fake_resolve_codex_target)
    monkeypatch.setattr(profbench_examples, "ProfBenchModelJudge", _FakeProfBenchModelJudge)

    result, reports = await profbench_examples.run_local_codex_profbench_live_candidate_smoke(
        output_dir=output_root,
        run_id="local-smoke",
        source=fixture,
        limit=1,
        agent_model="gpt-5.5",
    )

    assert result.summary.task_count == 1
    assert result.summary.attempt_count == 1
    assert result.output_dir == output_root / run_instance_id
    assert [path.name for path in reports.paths] == ["sdk-report.html", "report.html"]


def test_remote_profbench_source_is_saved_as_local_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    remote_source = _stub_remote_profbench_source(monkeypatch, fixture.read_text(encoding="utf-8"))
    evidence_dir = tmp_path / "run" / "evidence"

    benchmark = profbench.load_profbench(remote_source, limit=1, evidence_dir=evidence_dir)

    dataset_path = evidence_dir / "profbench-dataset.jsonl"
    assert dataset_path.read_text(encoding="utf-8") == fixture.read_text(encoding="utf-8")
    assert benchmark.metadata["source"] == str(dataset_path.resolve())
    assert benchmark.metadata["source_file"] == str(dataset_path.resolve())
    assert benchmark.metadata["remote_source"] == remote_source
    assert benchmark.metadata["etag"] == "test-etag"
    assert benchmark.metadata["resolved_commit"] == "test-commit"
    assert benchmark.tasks[0].metadata["source_uri"] == str(dataset_path.resolve())
    assert benchmark.attempts[0].evidence is not None
    assert benchmark.attempts[0].evidence.descriptors["source"].ref == str(dataset_path.resolve())

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, attempts=benchmark.attempts)
    failed_result = next(row for row in result.results if row.attempt_id == "pb-1:o3")
    details_output = next(output for output in failed_result.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT)
    details = profbench.profbench_details(details_output)
    assert details is not None
    assert details.deductions[0].evidence[0].href().startswith("file://")
    assert not details.deductions[0].evidence[0].href().startswith("https://")

def test_profbench_judge_parser_accepts_embedded_json_and_yes_no_fallback() -> None:
    embedded = profbench._parse_yes_no_decision('```json\n{"fulfilled": true, "reason": "matched"}\n```')
    assert embedded.fulfilled is True
    assert embedded.reason == "matched"

    loose = profbench._parse_yes_no_decision("The criterion is satisfied. {'fulfilled': false, 'reason': 'missing'}")
    assert loose.fulfilled is False

    boxed = profbench._parse_yes_no_decision(r"\boxed{fulfilled: true, reason: matches the criterion}")
    assert boxed.fulfilled is True
    assert boxed.reason == "matches the criterion"

    yes = profbench._parse_yes_no_decision("Yes - the answer includes the required definition.")
    assert yes.fulfilled is True


def test_profbench_judge_parser_conservatively_scores_unparseable_output() -> None:
    decision = profbench._parse_yes_no_decision(
        r"\boxed{\begin{aligned}&\text{Liouville equation instead of judge JSON}\end{aligned}}"
    )

    assert decision.fulfilled is False
    assert "not parseable" in decision.reason
    assert "treating criterion as unfulfilled" in decision.reason

    missing_field = profbench._parse_yes_no_decision('{"reason": "missing explicit boolean"}')
    assert missing_field.fulfilled is False
    assert "boolean 'fulfilled'" in missing_field.reason


@pytest.mark.asyncio
async def test_profbench_model_judge_uses_short_structured_params() -> None:
    captured: dict[str, Any] = {}

    async def fake_inference(
        model: Model,
        request: dict[str, Any],
        max_retries: int | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del model, max_retries, kwargs
        captured.update(request)
        return {"choices": [{"message": {"role": "assistant", "content": '{"fulfilled": true, "reason": "ok"}'}}]}

    judge = profbench.ProfBenchModelJudge(
        model=Model(url="https://model.test/v1/chat/completions", name="judge-model"),
        inference_fn=fake_inference,
    )

    decision = await judge.judge(
        profbench.ProfBenchJudgeRequest(
            task_id="pb-1",
            prompt="Task prompt",
            response="Candidate response",
            criterion_id="pb-1:criterion-1",
            criterion_description="Criterion text",
            weight_name="Minor",
        )
    )

    assert decision.fulfilled is True
    assert captured["temperature"] == 0.0
    assert captured["max_tokens"] == 256
    guided_json = captured["extra_body"]["nvext"]["guided_json"]
    assert guided_json["required"] == ["fulfilled", "reason"]
