# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise the customer-facing Docker Codex evidence example."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput
from nemo_evaluator_sdk.execution.samples import build_metric_input
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

_MODULE_PATH = Path(__file__).resolve().parents[2] / "examples" / "codex_docker" / "example.py"
_spec = importlib.util.spec_from_file_location("codex_docker_example", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
codex_docker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(codex_docker)


class _FakeCodexRuntime:
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    async def run_tasks(
        self,
        tasks: list[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalTrial]:
        task = tasks[0]
        artifact = self._workspace / codex_docker.ARTIFACT_PATH
        artifact.parent.mkdir(parents=True)
        artifact.write_text(f"{codex_docker.EXPECTED_TEXT}\n", encoding="utf-8")
        return [
            AgentEvalTrial(
                id=f"{task.id}:fake-codex",
                task_id=task.id,
                status=AgentEvalTrialStatus.COMPLETED,
                output=AgentOutput(
                    output_text=codex_docker.EXPECTED_TEXT,
                    metadata={"runtime": "fake_codex_docker"},
                ),
                evidence=CandidateEvidence(
                    descriptors={
                        "workspace": EvidenceDescriptor(kind="filesystem", ref=str(self._workspace)),
                    }
                ),
                metadata={"runtime": "fake_codex_docker", "agent_ok": True},
            )
        ]


def test_default_output_dir_is_under_repo_temp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(codex_docker.OUTPUT_ROOT_ENV_NAME, raising=False)

    output_dir = codex_docker._new_output_dir()

    assert output_dir.parent == codex_docker.REPO_ROOT / "temp" / "codex-docker-eval-output"


@pytest.mark.asyncio
async def test_codex_docker_example_scores_workspace_artifact(tmp_path: Path) -> None:
    result = await codex_docker.evaluate(
        output_dir=tmp_path / "run",
        runtime=_FakeCodexRuntime(tmp_path / "workspace"),
        write_dashboard=False,
    )

    assert result.trials[0].status is AgentEvalTrialStatus.COMPLETED
    assert {
        f"{score.metric_type}.{output.name}": output.value for score in result.scores for output in score.outputs
    } == {
        "workspace_artifact.artifact_matches": True,
        "workspace_artifact.output_matches": True,
    }
    assert (tmp_path / "run" / "run.json").is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "artifact", "expected_outputs"),
    [
        (codex_docker.EXPECTED_TEXT, codex_docker.EXPECTED_TEXT, [True, True]),
        ("wrong output", codex_docker.EXPECTED_TEXT, [False, True]),
        (codex_docker.EXPECTED_TEXT, "wrong artifact", [True, False]),
    ],
)
async def test_workspace_artifact_metric(
    tmp_path: Path,
    answer: str,
    artifact: str,
    expected_outputs: list[bool],
) -> None:
    workspace = tmp_path / "workspace"
    artifact_path = workspace / codex_docker.ARTIFACT_PATH
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(artifact, encoding="utf-8")
    evidence = CandidateEvidence(descriptors={"workspace": EvidenceDescriptor(kind="filesystem", ref=str(workspace))})

    metric_result = await codex_docker.WorkspaceArtifactMetric().compute_scores(
        build_metric_input(
            {
                "reference": {
                    "artifact_path": codex_docker.ARTIFACT_PATH,
                    "expected": codex_docker.EXPECTED_TEXT,
                }
            },
            {"output_text": answer, "evidence": evidence},
            index=0,
        )
    )

    assert [output.value for output in metric_result.outputs] == expected_outputs
