# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.codex import runtime as codex_runtime
from nemo_evaluator_sdk.values import Model

profbench = importlib.import_module("packages.nemo_evaluator_sdk.examples.profbench.profbench")
profbench_runner = importlib.import_module("packages.nemo_evaluator_sdk.examples.profbench.runner")


class _FakeUrlopenResponse:
    def __init__(self, body: str) -> None:
        self._body = body
        self.headers = {"ETag": "test-etag", "x-repo-commit": "test-commit"}

    def __enter__(self) -> _FakeUrlopenResponse:
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


def test_load_profbench_expands_tasks_trials_and_line_index(tmp_path: Path) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")

    benchmark = profbench.load_profbench(fixture)

    assert benchmark.metadata["record_count"] == 1
    assert [trial.metadata["model_id"] for trial in benchmark.trials] == ["o3", "r1-0528", "grok4"]

    metric = benchmark.tasks[0].metrics[0]
    assert isinstance(metric, profbench.ProfBenchRubricMetric)
    assert [criterion.points for criterion in metric.criteria] == [
        profbench.PROFBENCH_WEIGHT_POINTS["Critical"],
        profbench.PROFBENCH_WEIGHT_POINTS["Major"],
    ]
    assert [criterion.id for criterion in metric.criteria] == ["pb-1:criterion-1", "pb-1:criterion-2"]
    assert metric.criteria[0].line_number == 1
    assert metric.criteria[0].json_path == "$.rubrics[0]"


def test_profbench_baseline_scoring_creates_traceable_criterion_scores(tmp_path: Path) -> None:
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, trials=benchmark.trials)
    o3_score = next(row for row in result.scores if row.trial_id == "pb-1:o3")
    details_output = next(output for output in o3_score.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT)
    details = profbench.profbench_details(details_output)
    assert details is not None

    assert details.score == 4 / 7
    assert details.earned_points == 4
    assert details.max_points == 7

    failed = [criterion for criterion in details.criterion_scores if not criterion.fulfilled]
    assert len(failed) == 1
    assert failed[0].points == 3
    assert failed[0].metadata["score_source"] == "dataset_label"
    assert failed[0].evidence[0].line == 1
    assert failed[0].evidence[0].json_path == "$.rubrics[1]"
    assert failed[0].evidence[0].href().startswith("file://")
    assert "#L1" not in failed[0].evidence[0].href()
    assert all(criterion.judge_reason is None for criterion in details.criterion_scores)
    assert {criterion.metadata["score_source"] for criterion in details.criterion_scores} == {"dataset_label"}


def test_evidence_locator_local_file_href_omits_dead_line_fragment(tmp_path: Path) -> None:
    evidence_file = tmp_path / "profbench-dataset.jsonl"
    evidence_file.write_text("{}\n", encoding="utf-8")

    locator = profbench.EvidenceLocator(kind="profbench", uri=str(evidence_file), line=1, json_path="$.rubrics[0]")

    assert locator.href() == evidence_file.as_uri()
    assert locator.href(base_dir=tmp_path) == "profbench-dataset.jsonl"


def test_profbench_live_judge_mode_scores_recorded_trials_without_cached_labels(tmp_path: Path) -> None:
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

    assert all("profbench_fulfilments" not in trial.metadata for trial in benchmark.trials)

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, trials=benchmark.trials)
    o3_score = next(row for row in result.scores if row.trial_id == "pb-1:o3")
    details_output = next(output for output in o3_score.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT)
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

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, trials=benchmark.trials)

    assert result.summary.task_count == 1
    assert result.summary.trial_count == 3
    profbench_score = next(
        score
        for score in result.summary.scores.scores
        if score.name == f"{profbench.PROFBENCH_METRIC_TYPE}.{profbench.PROFBENCH_METRIC_ID}"
    )
    assert profbench_score.mean == 2 / 3


def test_profbench_dashboard_renders_rubric_report(tmp_path: Path) -> None:
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))
    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, trials=benchmark.trials)

    html = profbench.render_profbench_dashboard(result, evidence_base_dir=tmp_path)

    assert "ProfBench Agent Eval Report" in html
    assert "Task Details" in html
    assert "criterion-2" in html
    assert "Chemistry PhD" in html
    assert "dataset_label" in html
    assert 'href="profbench.jsonl"' in html
    assert "profbench.jsonl#L1" not in html

    report_path = profbench.write_profbench_dashboard(result, tmp_path / "report.html")
    assert report_path.read_text(encoding="utf-8") == html


def test_profbench_example_writes_sdk_and_profbench_dashboards(tmp_path: Path) -> None:
    benchmark = profbench.load_profbench(_write_profbench_fixture(tmp_path / "profbench.jsonl"))
    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, trials=benchmark.trials)

    sdk_path, default_path = profbench.write_example_dashboards(result, tmp_path)

    assert "Agent Eval Report" in sdk_path.read_text(encoding="utf-8")
    assert "ProfBench Agent Eval Report" in default_path.read_text(encoding="utf-8")
    assert not (tmp_path / "profbench-report.html").exists()


def test_profbench_run_instance_id_has_expected_format() -> None:
    run_instance_id = profbench_runner._new_profbench_run_instance_id()

    assert re.fullmatch(r"\d{8}_\d{6}_\d{5}_[0-9a-f]{6}", run_instance_id)


def test_profbench_output_root_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_root = tmp_path / "env-root"
    cli_root = tmp_path / "cli-root"

    monkeypatch.setenv("NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR", str(env_root))

    assert profbench_runner._resolve_profbench_output_root(cli_root) == cli_root
    assert profbench_runner._resolve_profbench_output_root() == env_root

    monkeypatch.delenv("NEMO_EVALUATOR_PROFBENCH_OUTPUT_DIR")
    assert profbench_runner._resolve_profbench_output_root() == profbench_runner.DEFAULT_OUTPUT_DIR


def test_profbench_output_dir_uses_run_then_mode_tree(tmp_path: Path) -> None:
    run_instance_id = "20260604_154749_70985_82f7dd"

    assert profbench_runner._profbench_output_dir(tmp_path, run_instance_id, "baseline") == (
        tmp_path / run_instance_id / "baseline"
    )
    assert profbench_runner._profbench_output_dir(tmp_path, run_instance_id, "live-candidate") == (
        tmp_path / run_instance_id / "live-candidate"
    )
    assert profbench_runner._profbench_output_dir(tmp_path, run_instance_id, "live-judge") == (
        tmp_path / run_instance_id / "live-judge"
    )


def test_remote_profbench_source_is_saved_as_local_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert benchmark.trials[0].evidence is not None
    assert benchmark.trials[0].evidence.descriptors["source"].ref == str(dataset_path.resolve())

    result = AgentEvaluator().run_sync(tasks=benchmark.tasks, trials=benchmark.trials)
    failed_score = next(row for row in result.scores if row.trial_id == "pb-1:o3")
    details_output = next(
        output for output in failed_score.outputs if output.name == profbench.PROFBENCH_DETAILS_OUTPUT
    )
    details = profbench.profbench_details(details_output)
    assert details is not None
    failed = next(criterion for criterion in details.criterion_scores if not criterion.fulfilled)
    assert failed.evidence[0].href().startswith("file://")
    assert not failed.evidence[0].href().startswith("https://")


def test_profbench_model_helpers_use_shared_defaults_with_optional_name_override() -> None:
    evaluated_model = profbench_runner._evaluated_model()
    overridden_model = profbench_runner._evaluated_model("custom-model")
    judge_model = profbench_runner._judge_model()

    assert evaluated_model.url == profbench_runner.DEFAULT_MODEL_URL
    assert evaluated_model.name == profbench_runner.DEFAULT_MODEL_NAME
    assert overridden_model.name == "custom-model"
    assert judge_model.url == profbench_runner.DEFAULT_MODEL_URL
    assert judge_model.name == profbench_runner.DEFAULT_MODEL_NAME


def test_profbench_live_candidate_target_selects_codex_runtime(tmp_path: Path) -> None:
    target, params, score_source, effective_runtime = profbench_runner._live_candidate_target(
        agent=profbench_runner.AgentChoice.CODEX,
        agent_model="gpt-5",
        runtime=codex_runtime.RuntimeChoice.LOCAL,
        output_dir=tmp_path / "live-candidate",
        env={"OPENAI_API_KEY": "sk-test-key"},
    )

    assert isinstance(target, codex_runtime.CodexCliAgentRuntime)
    assert target._model == "gpt-5"
    assert target._work_root == tmp_path / "live-candidate" / "evidence" / "codex"
    assert params is None
    assert score_source == "codex_cli_candidate_and_live_judge"
    assert effective_runtime == codex_runtime.EffectiveCodexRuntime.LOCAL_CLI


@pytest.mark.asyncio
async def test_profbench_run_examples_reuses_one_run_folder_for_enabled_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_instance_id = "20260604_154749_70985_82f7dd"
    calls: list[tuple[str, int | None, Path, str]] = []

    async def fake_run_mode(
        mode: profbench_runner.ProfBenchMode,
        *,
        limit: int | None,
        output_root: str | Path | None,
        run_instance_id: str | None,
        agent: profbench_runner.AgentChoice = profbench_runner.AgentChoice.MODEL,
        agent_model: str | None = None,
        runtime: codex_runtime.RuntimeChoice = codex_runtime.RuntimeChoice.DOCKER,
    ) -> None:
        assert output_root is not None
        assert run_instance_id is not None
        if mode is profbench_runner.ProfBenchMode.LIVE_CANDIDATE:
            assert agent == profbench_runner.AgentChoice.CODEX
            assert agent_model == "gpt-5"
            assert runtime == codex_runtime.RuntimeChoice.LOCAL
        calls.append((mode.value, limit, Path(output_root), run_instance_id))

    monkeypatch.setattr(profbench_runner, "run_profbench_mode", fake_run_mode)

    await profbench_runner.run_examples(
        limit=1,
        run_live_judge=True,
        run_live_candidate=True,
        output_root=tmp_path,
        run_instance_id=run_instance_id,
        agent=profbench_runner.AgentChoice.CODEX,
        agent_model="gpt-5",
        runtime=codex_runtime.RuntimeChoice.LOCAL,
    )

    assert calls == [
        ("baseline", 1, tmp_path, run_instance_id),
        ("live-judge", 1, tmp_path, run_instance_id),
        ("live-candidate", 1, tmp_path, run_instance_id),
    ]
    assert (tmp_path / run_instance_id).is_dir()
    assert not (tmp_path / run_instance_id / "baseline").exists()
    assert not (tmp_path / run_instance_id / "live-judge").exists()
    assert not (tmp_path / run_instance_id / "live-candidate").exists()


@pytest.mark.asyncio
async def test_profbench_baseline_example_writes_run_then_mode_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    remote_source = _stub_remote_profbench_source(monkeypatch, fixture.read_text(encoding="utf-8"))
    run_instance_id = "20260601_175657_75909_573ed6"
    monkeypatch.setattr(profbench_runner, "_profbench_source", lambda: remote_source)

    await profbench_runner.run_profbench_mode(
        profbench_runner.ProfBenchMode.BASELINE,
        limit=1,
        output_root=tmp_path,
        run_instance_id=run_instance_id,
    )

    output_dir = tmp_path / run_instance_id / "baseline"
    evidence_dir = output_dir / "evidence"
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "report.html").is_file()
    assert (evidence_dir / "profbench-dataset.jsonl").is_file()
    assert not (output_dir / "profbench-report.html").exists()
    assert not (tmp_path / run_instance_id / "evidence" / "profbench-dataset.jsonl").exists()

    run_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["run_id"] == f"{run_instance_id}-baseline"
    assert run_payload["output_dir"] == str(output_dir)
    assert run_payload["artifacts"]["scores"] == "scores.jsonl"


@pytest.mark.asyncio
async def test_profbench_live_judge_example_writes_mode_evidence_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _write_profbench_fixture(tmp_path / "profbench.jsonl")
    remote_source = _stub_remote_profbench_source(monkeypatch, fixture.read_text(encoding="utf-8"))
    run_instance_id = "20260601_175657_75909_573ed6"

    class FakeProfBenchModelJudge:
        def __init__(self, model: Model) -> None:
            self.model = model

        async def judge(self, request: Any) -> Any:
            return profbench.ProfBenchJudgeDecision(
                fulfilled=request.criterion_id.endswith("criterion-1"),
                reason=f"judged {request.criterion_id}",
            )

    monkeypatch.setattr(profbench_runner, "_profbench_source", lambda: remote_source)
    monkeypatch.setattr(profbench_runner, "ProfBenchModelJudge", FakeProfBenchModelJudge)

    await profbench_runner.run_profbench_mode(
        profbench_runner.ProfBenchMode.LIVE_JUDGE,
        limit=1,
        output_root=tmp_path,
        run_instance_id=run_instance_id,
    )

    output_dir = tmp_path / run_instance_id / "live-judge"
    evidence_dir = output_dir / "evidence"
    judge_artifacts = sorted(evidence_dir.glob("judge-*.json"))
    assert (evidence_dir / "profbench-dataset.jsonl").is_file()
    assert judge_artifacts
    assert not list((tmp_path / run_instance_id / "evidence").glob("judge-*.json"))

    score_payloads = [
        json.loads(line) for line in (output_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    first_judge_uri = next(
        locator["uri"]
        for score in score_payloads
        for output in score["outputs"]
        if output["name"] == profbench.PROFBENCH_DETAILS_OUTPUT
        for criterion in output["value"]["criterion_scores"]
        for locator in criterion["evidence"]
        if locator["kind"] == "judge"
    )
    assert first_judge_uri.startswith(str(evidence_dir.resolve()))
    assert Path(first_judge_uri).is_file()
    assert profbench.EvidenceLocator(kind="judge", uri=first_judge_uri, line=1).href().startswith("file://")


def test_profbench_judge_parser_accepts_clean_and_embedded_structured_json() -> None:
    clean = profbench._parse_judge_decision('{"fulfilled": true, "reason": "matched"}')
    assert clean.fulfilled is True
    assert clean.reason == "matched"

    embedded = profbench._parse_judge_decision('```json\n{"fulfilled": false, "reason": "missing"}\n```')
    assert embedded.fulfilled is False
    assert embedded.reason == "missing"


def test_profbench_judge_parser_conservatively_scores_unparseable_output() -> None:
    decision = profbench._parse_judge_decision(
        r"\boxed{\begin{aligned}&\text{Liouville equation instead of judge JSON}\end{aligned}}"
    )
    assert decision.fulfilled is False
    assert "treating criterion as unfulfilled" in decision.reason

    missing_field = profbench._parse_judge_decision('{"reason": "missing explicit boolean"}')
    assert missing_field.fulfilled is False
    assert "treating criterion as unfulfilled" in missing_field.reason


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
