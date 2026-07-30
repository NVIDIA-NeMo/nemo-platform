# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trusted adapter and Harbor job-construction tests."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from harbor.job import JobConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator import harbor
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    EvaluationResult,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    ArchiveReference,
    EnvelopeTask,
    EvaluationEnvelope,
    EvaluationSubmission,
    RunProfile,
)
from nemo_experimentalist_plugin.harbor_bridge.runner import (
    HarborBridgeRunner,
    TrustedInferenceConfig,
)
from nemo_experimentalist_plugin.harbor_bridge.trusted_agent import (
    TrustedCandidateAgent,
    candidate_agent_import,
)


def _candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "main.py").write_text(
        "raise AssertionError('candidate was imported on the host')\n",
        encoding="utf-8",
    )
    (candidate / "pyproject.toml").write_text(
        '[project]\nname = "candidate"\nversion = "0.0.0"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    (candidate / "uv.lock").write_text('version = 1\nrevision = 3\nrequires-python = ">=3.12"\n')
    return candidate


def _dataset(tmp_path: Path) -> Path:
    dataset = tmp_path / "dataset"
    task = dataset / "generated-task"
    (task / "environment").mkdir(parents=True)
    (task / "task.toml").write_text(
        """
[task]
name = "fixture/generated-task"

[environment]
type = "docker"

[verifier]
""".lstrip(),
        encoding="utf-8",
    )
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return dataset


def _submission() -> EvaluationSubmission:
    digest = f"sha256:{'0' * 64}"
    return EvaluationSubmission(
        request_id="candidate-001",
        envelope=EvaluationEnvelope(
            id="fixture-envelope",
            digest=digest,
            tasks=[EnvelopeTask(task_id="generated-task", base_task_id="base-task")],
        ),
        candidate=ArchiveReference(digest=digest),
        run_profile="smoke",
    )


def _profile() -> RunProfile:
    return RunProfile(
        attempts=1,
        concurrency=1,
        retries=0,
        agent_timeout_multiplier=0.25,
        verifier_timeout_multiplier=0.25,
        setup_timeout_multiplier=0.5,
        build_timeout_multiplier=0.5,
    )


def test_candidate_adapter_import_never_executes_candidate_python(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    with candidate_agent_import(candidate) as import_path:
        module_name, attribute = import_path.split(":", 1)
        module = importlib.import_module(module_name)
        adapter = getattr(module, attribute)
        assert issubclass(adapter, TrustedCandidateAgent)
        assert adapter.candidate_dir == candidate


def test_candidate_adapter_rejects_links(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    (candidate / "link.py").symlink_to(candidate / "main.py")
    with pytest.raises(RuntimeError, match="symbolic link"):
        with candidate_agent_import(candidate):
            pass


class _FakeEvaluator:
    config: HarborEvaluatorConfig | None = None

    def __init__(self, options: HarborEvaluatorConfig, experiment_dir: Path) -> None:
        self.__class__.config = options
        self.experiment_dir = experiment_dir

    async def run(self, candidate_dir: Path, dataset: HarborDataset) -> EvaluationResult:
        assert candidate_dir.is_dir()
        assert dataset.get_task("generated-task")
        return EvaluationResult(id="result")


async def test_runner_uses_only_trusted_adapter_and_preserves_verifier_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate(tmp_path)
    dataset = _dataset(tmp_path)
    task_toml = dataset / "generated-task" / "task.toml"
    before = task_toml.read_text(encoding="utf-8")
    monkeypatch.setattr(
        "nemo_experimentalist_plugin.harbor_bridge.runner.HarborEvaluator",
        _FakeEvaluator,
    )
    runner = HarborBridgeRunner(
        TrustedInferenceConfig.model_validate(
            {
                "api_key": "dedicated-key",
                "api_base": "https://inference.example.test/v1",
                "model_name": "fixture-model",
            }
        )
    )
    result = await runner.run(
        submission=_submission(),
        profile=_profile(),
        candidate_dir=candidate,
        dataset_dir=dataset,
        work_dir=tmp_path / "work",
    )
    assert result.id == "result"
    assert task_toml.read_text(encoding="utf-8") == before
    config = _FakeEvaluator.config
    assert config is not None
    assert config.scope_import_path is False
    assert config.import_path.startswith("nemo_experimentalist_plugin.harbor_bridge._candidate_")
    assert config.agent_env == {
        "INFERENCE_API_KEY": "dedicated-key",
        "INFERENCE_API_BASE": "https://inference.example.test/v1",
        "AUT_MODEL_NAME": "fixture-model",
    }


class _FakeJob:
    def __init__(self, config: JobConfig, job_dir: Path) -> None:
        self.config = config
        self.job_dir = job_dir

    async def run(self) -> None:
        self.job_dir.mkdir(parents=True)


async def test_harbor_evaluator_does_not_scope_bridge_owned_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate(tmp_path)
    dataset_path = _dataset(tmp_path)
    dataset = HarborDataset.from_ref(DatasetRef(uri=dataset_path.as_uri()))
    captured: dict[str, Any] = {}

    async def create_job(config: JobConfig) -> _FakeJob:
        captured["config"] = config
        return _FakeJob(config, tmp_path / "results")

    def fail_scoping(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("bridge-owned import path must not be scoped through candidate files")

    monkeypatch.setattr(harbor.Job, "create", create_job)
    monkeypatch.setattr(harbor, "_scoped_import_path", fail_scoping)
    evaluator = HarborEvaluator(
        HarborEvaluatorConfig(
            import_path="trusted.module:Adapter",
            scope_import_path=False,
            agent_model_name="fixture-model",
            agent_env={"INFERENCE_API_KEY": "dedicated-key"},
            jobs_dir=Path("results"),
        ),
        experiment_dir=tmp_path,
    )
    result = await evaluator.run(candidate, dataset)
    assert result.trials == []
    config = captured["config"]
    assert isinstance(config, JobConfig)
    assert config.agents[0].import_path == "trusted.module:Adapter"
    assert config.agents[0].model_name == "fixture-model"
    assert config.agents[0].env == {"INFERENCE_API_KEY": "dedicated-key"}
    assert config.environment.env == {}
