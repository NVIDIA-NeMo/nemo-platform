# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend fetch/archive/publish tests.

Covers insight resolution, the git vs local dispatch in ``get_agent_code``, and the
``archive_candidate`` / ``publish_candidate`` verbs (which derive branch/base_ref/agent_path
from the captured ``AgentSource`` and delegate to ``PRPublisher``) — with the git/subprocess
boundary mocked.
"""

import asyncio
import json
import traceback
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from nemo_experimentalist_plugin.entities import Candidate
from nemo_experimentalist_plugin.experimentalist import experimentalist_backend as beim
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import EvaluationResult
from nemo_experimentalist_plugin.experimentalist.components.repository import AgentCloneError, AgentSource
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
    CandidateStorageConfig,
    LocalExperimentalistBackend,
    RemoteExperimentalistBackend,
)
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform


def _local_backend(tmp_path: Path) -> LocalExperimentalistBackend:
    return LocalExperimentalistBackend(path=tmp_path / "backend")


def _as_platform_client(value: object) -> AsyncNeMoPlatform:
    return cast(AsyncNeMoPlatform, value)


# ---------------------------------------------------------------------------
# get_insight — local file (offline) vs platform id fetch
# ---------------------------------------------------------------------------


class _StubInsightResource:
    def __init__(self, insight: Insight | None, error: Exception | None = None) -> None:
        self._insight = insight
        self._error = error
        self.calls: list[dict[str, str]] = []

    async def get(self, *, workspace: str, insight_id: str) -> Insight:
        self.calls.append({"workspace": workspace, "insight_id": insight_id})
        if self._error is not None:
            raise self._error
        assert self._insight is not None
        return self._insight


class _StubInsights:
    def __init__(self, insight: Insight) -> None:
        self.insights = _StubInsightResource(insight)


class _StubClient:
    def __init__(self, insight: Insight) -> None:
        self.insights = _StubInsights(insight)


class _ErrorStubClient:
    def __init__(self, error: Exception) -> None:
        self.insights = type("_StubInsights", (), {"insights": _StubInsightResource(None, error=error)})()


async def test_get_insight_reads_local_file(tmp_path: Path) -> None:
    insight_file = tmp_path / "insight.json"
    insight_file.write_text(
        json.dumps({"id": "insight-local", "workspace": "w", "title": "t", "description": "d", "agent": "a"})
    )
    backend = LocalExperimentalistBackend(path=tmp_path / "backend")

    insight = await backend.get_insight(workspace="w", insight_id=str(insight_file))

    assert insight.id == "insight-local"


async def test_get_insight_fetches_platform_id_via_client(tmp_path: Path) -> None:
    platform_insight = Insight(workspace="ws", title="platform", description="d", agent="a")
    client = _StubClient(platform_insight)
    backend = LocalExperimentalistBackend(client=_as_platform_client(client), path=tmp_path / "backend")

    insight = await backend.get_insight(workspace="ws", insight_id="insight-remote-123")

    assert insight is platform_insight
    assert client.insights.insights.calls == [{"workspace": "ws", "insight_id": "insight-remote-123"}]


async def test_get_insight_platform_id_without_client_raises(tmp_path: Path) -> None:
    backend = LocalExperimentalistBackend(path=tmp_path / "backend")
    with pytest.raises(ValueError, match="no platform client is available"):
        await backend.get_insight(workspace="w", insight_id="insight-remote-123")


async def test_get_insight_platform_404_raises_value_error(tmp_path: Path) -> None:
    request = httpx.Request("GET", "http://platform.test/insights/missing")
    response = httpx.Response(404, request=request)
    error = httpx.HTTPStatusError("not found", request=request, response=response)
    backend = LocalExperimentalistBackend(
        client=_as_platform_client(_ErrorStubClient(error)),
        path=tmp_path / "backend",
    )

    with pytest.raises(ValueError, match="Insight not found on the platform"):
        await backend.get_insight(workspace="w", insight_id="missing")


# ---------------------------------------------------------------------------
# get_agent_code — local path (unchanged behavior, returns None)
# ---------------------------------------------------------------------------


async def test_get_agent_code_local_copies_returns_none(tmp_path: Path) -> None:
    src = tmp_path / "agent"
    src.mkdir()
    (src / "main.py").write_text("print('x')\n")
    dest = tmp_path / "dest"
    source = await _local_backend(tmp_path).get_agent_code(workspace="w", agent=src, dest=dest)
    assert source is None
    assert (dest / "main.py").read_text() == "print('x')\n"


# ---------------------------------------------------------------------------
# get_agent_code — git source (dispatches to clone_agent_repo, returns AgentSource)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_factory", ["local", "remote"])
def test_get_agent_code_git_dispatches_to_clone(backend_factory, tmp_path, monkeypatch):  # noqa: ANN001
    calls: list[tuple[str, Path]] = []

    def fake_clone(spec: str, dest: Path, *, clone_depth: int | None = None) -> AgentSource:
        calls.append((spec, Path(dest)))
        Path(dest).mkdir(parents=True, exist_ok=True)
        return AgentSource(repo_url="ssh://git@h/g/r.git", ref="main")

    monkeypatch.setattr(beim, "clone_agent_repo", fake_clone)

    backend = (
        _local_backend(tmp_path)
        if backend_factory == "local"
        else RemoteExperimentalistBackend(client=_as_platform_client(None), path=tmp_path / "backend")
    )
    spec = "ssh://git@h/g/r.git@main"
    dest = tmp_path / "agent-src"

    source = asyncio.run(backend.get_agent_code(workspace="w", agent=spec, dest=dest))
    assert source == AgentSource(repo_url="ssh://git@h/g/r.git", ref="main")
    assert calls == [(spec, dest)]


async def test_get_agent_code_git_preserves_owned_clone_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = "git clone failed for https://***@gitlab.com/org/repo.git (exit status 128)"
    failure = AgentCloneError(message)

    def fail_clone(spec: str, *_args, **_kwargs) -> AgentSource:  # noqa: ANN002, ANN003
        raise failure

    monkeypatch.setattr(beim, "clone_agent_repo", fail_clone)

    with pytest.raises(AgentCloneError) as exc_info:
        await _local_backend(tmp_path).get_agent_code(
            workspace="w",
            agent="https://gitlab.com/org/repo.git",
            dest=tmp_path / "dest",
        )

    assert exc_info.value is failure
    assert str(exc_info.value) == message
    assert exc_info.value.__cause__ is None


async def test_get_agent_code_git_suppresses_legacy_called_process_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = beim.subprocess.CalledProcessError(
        128,
        ["git", "clone", "command-secret"],
        output="stdout-secret",
        stderr="stderr-secret",
    )

    def fail_clone(spec: str, *_args, **_kwargs) -> AgentSource:  # noqa: ANN002, ANN003
        raise failure

    monkeypatch.setattr(beim, "clone_agent_repo", fail_clone)
    secrets = ("token-user", "secret-token")
    source = f"https://{secrets[0]}:{secrets[1]}@gitlab.com/org/repo.git@main"

    with pytest.raises(ValueError) as exc_info:
        await _local_backend(tmp_path).get_agent_code(workspace="w", agent=source, dest=tmp_path / "dest")

    formatted = "".join(traceback.format_exception(exc_info.value))
    assert str(exc_info.value) == "failed to fetch --agent 'https://***@gitlab.com/org/repo.git'"
    assert not any(secret in formatted for secret in (*secrets, "command-secret", "stdout-secret", "stderr-secret"))
    assert exc_info.value.__cause__ is None


async def test_get_agent_code_remote_nongit_raises(tmp_path: Path) -> None:
    backend = RemoteExperimentalistBackend(client=_as_platform_client(None), path=tmp_path / "backend")
    with pytest.raises(NotImplementedError):
        await backend.get_agent_code(workspace="w", agent="some-live-agent-name", dest=tmp_path / "d")


# ---------------------------------------------------------------------------
# get_agent_spec — local path copies to dest and returns dest
# ---------------------------------------------------------------------------


async def test_get_agent_spec_local_copies_to_dest_and_returns_dest(tmp_path: Path) -> None:
    spec_file = tmp_path / "AGENT-SPEC.md"
    spec_file.write_text("# My Agent\nDoes things.\n")
    dest = tmp_path / "workspace" / "AGENT-SPEC.md"

    result = await _local_backend(tmp_path).get_agent_spec(workspace="w", spec=str(spec_file), dest=dest)

    assert result == dest
    assert dest.read_text() == "# My Agent\nDoes things.\n"


async def test_get_agent_spec_local_missing_raises(tmp_path: Path) -> None:
    dest = tmp_path / "workspace" / "AGENT-SPEC.md"
    with pytest.raises(FileNotFoundError, match="Agent spec not found"):
        await _local_backend(tmp_path).get_agent_spec(workspace="w", spec=str(tmp_path / "nonexistent.md"), dest=dest)


async def test_get_agent_spec_directory_raises(tmp_path: Path) -> None:
    dest = tmp_path / "workspace" / "AGENT-SPEC.md"
    with pytest.raises(FileNotFoundError, match="Agent spec not found"):
        await _local_backend(tmp_path).get_agent_spec(workspace="w", spec=str(tmp_path), dest=dest)


async def test_get_agent_spec_remote_delegates_to_files(tmp_path: Path) -> None:
    spec_file = tmp_path / "AGENT-SPEC.md"
    spec_file.write_text("# Remote Agent\n")
    dest = tmp_path / "workspace" / "AGENT-SPEC.md"
    backend = RemoteExperimentalistBackend(client=_as_platform_client(None), path=tmp_path / "backend")

    result = await backend.get_agent_spec(workspace="w", spec=str(spec_file), dest=dest)

    assert result == dest
    assert dest.read_text() == "# Remote Agent\n"


# ---------------------------------------------------------------------------
# archive_candidate / publish_candidate — clean (workspace, candidate) verbs.
# The backend derives branch/base_ref/agent_path/title/body from the captured git
# provenance + storage config; the git/subprocess boundary (PRPublisher) is stubbed.
# ---------------------------------------------------------------------------


def _cand(label: str = "agent-2", run_id: str = "run-1") -> Candidate:
    return Candidate(name=label, label=label, run_id=run_id, round=1, optimization="edit")


def _git_backend(tmp_path: Path, storage: CandidateStorageConfig | None = None) -> LocalExperimentalistBackend:
    backend = LocalExperimentalistBackend(path=tmp_path / "backend", storage=storage)
    backend._agent_source = AgentSource(repo_url="ssh://git@h/g/r.git", ref="main", agent_path="pkg/agent")
    backend._agent_checkout = tmp_path / "clone"
    return backend


async def test_archive_candidate_git_pushes_and_records_source_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class _StubPublisher:
        def __init__(self, *, agent_dir: Path) -> None:
            captured["agent_dir"] = agent_dir

        def push_branch(self, *, src_dir, branch, base_ref, message, agent_path="."):  # noqa: ANN001, ANN202
            captured.update(branch=branch, base_ref=base_ref, agent_path=agent_path)
            return True

    monkeypatch.setattr(beim, "PRPublisher", _StubPublisher)
    backend = _git_backend(tmp_path, CandidateStorageConfig(candidate_branch_prefix="optimizer"))

    # Clean verb: only (workspace, candidate); branch/base_ref/agent_path are derived internally.
    link = await backend.archive_candidate(workspace="w", candidate=_cand())
    assert captured == {
        "agent_dir": tmp_path / "clone",
        "branch": "optimizer/run-1/agent-2",
        "base_ref": "main",
        "agent_path": "pkg/agent",
    }
    assert link == "ssh://git@h/g/r.git@optimizer/run-1/agent-2"
    # The link is recorded so re-projection surfaces the real branch, not the pseudo placeholder.
    assert backend._candidate_source_links["agent-2"] == link


async def test_publish_candidate_git_delegates_and_stashes_pr_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class _StubPublisher:
        def __init__(self, *, agent_dir: Path) -> None:
            captured["agent_dir"] = agent_dir

        def publish(
            self, *, winner_dir, branch, base_ref, title, body, draft, agent_path, base_branch_override, labels
        ):  # noqa: ANN001, ANN202
            captured.update(branch=branch, base_ref=base_ref, agent_path=agent_path, draft=draft, labels=labels)
            return "https://gitlab.example.com/g/r/-/merge_requests/7"

    monkeypatch.setattr(beim, "PRPublisher", _StubPublisher)
    storage = CandidateStorageConfig(candidate_branch_prefix="optimizer", pr_draft=False, pr_labels=["opt"])
    backend = _git_backend(tmp_path, storage)

    url = await backend.publish_candidate(workspace="w", candidate=_cand(label="agent-1"))
    assert url == "https://gitlab.example.com/g/r/-/merge_requests/7"
    assert captured["branch"] == "optimizer/run-1/agent-1" and captured["base_ref"] == "main"
    assert captured["agent_path"] == "pkg/agent" and captured["draft"] is False and captured["labels"] == ["opt"]
    # PR URL stashed so the mirror's finalize() records it on the winner's Experiment source_link.
    assert backend._pr_url == url


async def test_archive_and_publish_noop_for_non_git_source(tmp_path: Path) -> None:
    # No captured git source (local agent) -> both verbs no-op returning None.
    backend = _local_backend(tmp_path)
    assert await backend.archive_candidate(workspace="w", candidate=_cand()) is None
    assert await backend.publish_candidate(workspace="w", candidate=_cand()) is None


async def test_persist_result_writes_run_summary(tmp_path: Path) -> None:
    # persist_result must write result.summary into run.json, else publish_candidate's
    # _compose_pr_body falls back to "Experimentalist run complete." instead of the real summary.
    from nemo_experimentalist_plugin.entities import ExperimentRun
    from nemo_experimentalist_plugin.experimentalist.result import ExperimentalistResult

    backend = _local_backend(tmp_path)
    run = ExperimentRun(workspace="w", agent="a")
    run._id = "run-1"  # type: ignore[attr-defined]
    (backend._eo / "run.json").write_text(run.model_dump_json(indent=2))

    result = ExperimentalistResult(summary="the real run summary", run_id="run-1", rounds_completed=2, winner=None)
    await backend.persist_result(workspace="w", result=result)

    saved = json.loads((backend._eo / "run.json").read_text())
    assert saved["summary"] == "the real run summary"
    assert (backend._eo / "OPTIMIZATION.md").read_text() == "the real run summary"


async def test_persist_result_preserves_generated_optimization_report(tmp_path: Path) -> None:
    from nemo_experimentalist_plugin.experimentalist.result import ExperimentalistResult

    backend = _local_backend(tmp_path)
    report_path = backend._eo / "OPTIMIZATION.md"
    report_path.write_text("# Full optimization report\n\nInsight Suite Metrics")

    result = ExperimentalistResult(summary="compact run summary", run_id="run-1", rounds_completed=2, winner=None)
    await backend.persist_result(workspace="w", result=result)

    assert report_path.read_text() == "# Full optimization report\n\nInsight Suite Metrics"


# ---------------------------------------------------------------------------
# persist_evaluation
# ---------------------------------------------------------------------------


async def test_remote_forwards_to_local(tmp_path: Path) -> None:
    """Remote delegates persist_evaluation verbatim to its local file backend."""
    backend = RemoteExperimentalistBackend(client=_as_platform_client(None), path=tmp_path / "backend")
    delegate = AsyncMock()
    backend._files.persist_evaluation = delegate
    result = EvaluationResult(id="r1")
    candidate = _cand()

    await backend.persist_evaluation(workspace="w", result=result, candidate=candidate, split="train")

    delegate.assert_called_once_with(workspace="w", result=result, candidate=candidate, split="train")
