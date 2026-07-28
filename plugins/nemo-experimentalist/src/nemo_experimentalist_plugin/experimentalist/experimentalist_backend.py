# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data-access backend abstractions for the Experimentalist.

One :class:`ExperimentalistBackend` is built per run and shared through
:class:`ExperimentalistDeps`. The backend interface covers entity CRUD, dataset
and agent-code materialization, Intake reads, agent metadata reads, and terminal
result persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal, TypeVar, cast
from urllib.parse import urlparse

import httpx
from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    EvaluationResult,
    ResourceRef,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.components.repository import (
    AgentSource,
    PRPublisher,
    _redact_url,
    clone_agent_repo,
    looks_like_git,
    split_agent_spec,
    split_git_ref,
)
from nemo_experimentalist_plugin.experimentalist.experiment_mirror import ExperimentMirror
from nemo_experimentalist_plugin.experimentalist.otlp import jsonl_to_protobuf, read_trace_id, spans_to_protobuf
from nemo_experimentalist_plugin.experimentalist.result import ExperimentalistResult
from nemo_experimentalist_plugin.resolve import (
    AgentSourceConfig as AgentSourceConfig,
)
from nemo_experimentalist_plugin.resolve import (
    CandidateStorageConfig as CandidateStorageConfig,
)
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform
from pydantic import BaseModel

logger = logging.getLogger(__name__)
_ModelT = TypeVar("_ModelT", bound=BaseModel)


async def _upload_trace_otlp(
    client: AsyncNeMoPlatform,
    workspace: str,
    ref: ResourceRef,
    *,
    experiment_id: str,
    trial_id: str,
    task_id: str,
    extra_attrs: dict[str, str] | None = None,
) -> None:
    """Upload an experimentalist trace file to Intake as protobuf."""

    path = Path(urlparse(ref.uri).path)
    attrs: dict[str, str] = {
        "nemo.experiment.id": experiment_id,
        "nemo.test_case.id": task_id,
        "nemo.trial.id": trial_id,
        **(extra_attrs or {}),
    }
    url = f"/apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces"
    for payload in jsonl_to_protobuf(path, extra_resource_attrs=attrs):
        await client.post(
            url,
            cast_to=object,
            content=payload,
            options={"headers": {"Content-Type": "application/x-protobuf"}},
        )


_BASELINE_AGENT_LABEL = "agent-0"

_AGENT_COPY_EXCLUDE_NAMES = {
    "__pycache__",
    ".git",
    ".claude",
    ".uv",
    ".venv",
    "artifacts",
    "dataset",
    "eval-and-optimize",
    "scratch",
}


def _ignore_agent_copy(directory: str, contents: list[str]) -> set[str]:
    del directory
    return {name for name in contents if name in _AGENT_COPY_EXCLUDE_NAMES}


class ExperimentalistBackend(ABC):
    """Pluggable data-access interface for the Experimentalist."""

    def __init__(
        self,
        client: AsyncNeMoPlatform | None = None,
        path: Path | None = None,
        storage: CandidateStorageConfig | None = None,
    ) -> None:
        self.client = client
        self.path = path
        # Candidate-archival / winner-PR settings (the config slice), so the archive/publish
        # verbs take only (workspace, candidate) and derive branch/title/body/options from here.
        self.storage = storage or CandidateStorageConfig()

    # -- Insight read --------------------------------------------------------

    @abstractmethod
    async def get_insight(self, *, workspace: str, insight_id: str) -> Insight:
        """Fetch or load the Insight identified by *insight_id*."""
        ...

    # -- ExperimentRun CRUD --------------------------------------------------

    @abstractmethod
    async def create_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        """Persist a new ExperimentRun and return it with its durable id."""
        ...

    @abstractmethod
    async def update_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        """Persist changes to an existing ExperimentRun."""
        ...

    # -- Candidate CRUD ------------------------------------------------------

    @abstractmethod
    async def create_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        """Persist a new Candidate and return it with its durable id."""
        ...

    @abstractmethod
    async def update_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        """Persist changes to an existing Candidate."""
        ...

    @abstractmethod
    async def get_candidate(self, *, workspace: str, candidate_id: str) -> Candidate:
        """Fetch a single Candidate by its durable id."""
        ...

    @abstractmethod
    async def list_candidates(self, *, workspace: str, run_id: str) -> list[Candidate]:
        """Return all Candidates that belong to a given ExperimentRun."""
        ...

    # -- Result persistence --------------------------------------------------

    @abstractmethod
    async def persist_result(self, *, workspace: str, result: ExperimentalistResult) -> None:
        """Persist the terminal result for an Experimentalist run.

        The result identifies the run and carries the terminal summary,
        completed round count, and optional winning Candidate.
        """
        ...

    @abstractmethod
    async def persist_evaluation(
        self,
        *,
        workspace: str,
        result: EvaluationResult,
        candidate: Candidate,
        split: str,
    ) -> None:
        """Persist traces and metrics for a completed evaluation.

        Derives experiment_id internally from candidate × split, ensuring the
        Experiment entity exists before stamping traces.
        """
        ...

    @abstractmethod
    async def get_experiment_id(self, *, workspace: str, candidate: Candidate, split: str) -> str:
        """Best-effort native Experiment id for *candidate* × *split* in *workspace*.

        Returns "" when there is no projection (offline) or it fails — the id only
        tags Intake resource attributes, so a run must not break on it.
        """
        ...

    # -- Agent code access ---------------------------------------------------

    @abstractmethod
    async def get_agent_code(
        self, *, workspace: str, agent: str | Path, dest: Path, clone_depth: int | None = None
    ) -> AgentSource | None:
        """Materialize the agent's code files into *dest*.

        Returns the git :class:`AgentSource` provenance when *agent* is a git
        ``url@ref[#agent_path]`` (the clone retains ``.git`` so *dest* can serve as a PR/MR push
        target); returns ``None`` for a local path or non-git source. *clone_depth* optionally
        makes a shallow clone.
        """
        ...

    async def _clone_git_agent(self, agent: str, dest: Path, *, clone_depth: int | None = None) -> AgentSource:
        """Clone a git ``url@ref`` agent into *dest*, surfacing failures as ``ValueError``.

        Shared by every backend: git-sourced agents fetch identically regardless of
        backend. Safe :class:`AgentCloneError` details pass through; a legacy raw
        ``CalledProcessError`` is replaced so both reach the CLI's clean error path.
        """
        try:
            return await asyncio.to_thread(clone_agent_repo, agent, dest, clone_depth=clone_depth)
        except subprocess.CalledProcessError:
            remote, _ = split_git_ref(split_agent_spec(agent)[0])
            raise ValueError(f"failed to fetch --agent {_redact_url(remote)!r}") from None

    @abstractmethod
    async def archive_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        """Persist a produced candidate's code to durable storage; return a locator for it, or None.

        Records the returned locator as the candidate's ``source_link``. Returns ``None`` when this
        backend cannot archive the candidate (e.g. no code source to store from) or there is nothing
        new to persist. How and where the code is stored is backend-specific. Best-effort: callers
        gate on :attr:`storage`.archive_candidates and never let a failure fail the run.
        """
        ...

    @abstractmethod
    async def publish_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        """Surface a candidate (the winner) as a reviewable change; return its URL, or None.

        Records the returned URL as the candidate's ``source_link``. Returns ``None`` when this
        backend cannot publish (e.g. no code source) or there is nothing to publish. How the change
        is surfaced is backend-specific. Callers gate on :attr:`storage`.publish_winner.
        """
        ...

    # -- Intake reads --------------------------------------------------------

    @abstractmethod
    async def list_traces(
        self,
        *,
        workspace: str,
        filter: dict[str, Any] | None,
        sort: str,
        mode: str,
        limit: int,
    ) -> dict[str, Any]:
        """Return up to *limit* traces matching the requested query."""
        ...

    @abstractmethod
    async def get_trace(self, *, workspace: str, trace_id: str, mode: str) -> dict[str, Any]:
        """Fetch a single trace by id."""
        ...

    @abstractmethod
    async def list_scores(self, *, workspace: str, span_id: str) -> dict[str, Any]:
        """Fetch evaluator results for a span."""
        ...

    # -- Agent reads ---------------------------------------------------------

    @abstractmethod
    async def get_agent(self, *, workspace: str, agent: str) -> Any:
        """Return metadata for the registered agent."""
        ...

    @abstractmethod
    async def get_agent_spec(self, *, workspace: str, spec: str, dest: Path) -> Path:
        """Materialize the agent-spec URI *spec* into *dest*; return *dest*."""
        ...


class RemoteExperimentalistBackend(ExperimentalistBackend):
    """Backend selected for platform-backed Experimentalist runs."""

    def __init__(self, *, client: AsyncNeMoPlatform, path: Path, storage: CandidateStorageConfig | None = None) -> None:
        super().__init__(client, path, storage)
        # Reuse local-mode file persistence for the plugin entities (spec §3 decision 5).
        # LocalExperimentalistBackend also performs the best-effort projection to native
        # Experiments whenever it has a platform client — which this backend always passes —
        # so delegation here covers both persistence and projection.
        self.client = client
        self._files = LocalExperimentalistBackend(client=client, path=path, storage=self.storage)

    async def get_insight(self, *, workspace: str, insight_id: str) -> Insight:
        return await self._files.get_insight(workspace=workspace, insight_id=insight_id)

    async def create_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        return await self._files.create_run(workspace=workspace, run=run)

    async def update_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        return await self._files.update_run(workspace=workspace, run=run)

    async def create_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        return await self._files.create_candidate(workspace=workspace, candidate=candidate)

    async def update_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        return await self._files.update_candidate(workspace=workspace, candidate=candidate)

    async def get_candidate(self, *, workspace: str, candidate_id: str) -> Candidate:
        return await self._files.get_candidate(workspace=workspace, candidate_id=candidate_id)

    async def list_candidates(self, *, workspace: str, run_id: str) -> list[Candidate]:
        return await self._files.list_candidates(workspace=workspace, run_id=run_id)

    async def persist_result(self, *, workspace: str, result: ExperimentalistResult) -> None:
        await self._files.persist_result(workspace=workspace, result=result)

    async def persist_evaluation(
        self, *, workspace: str, result: EvaluationResult, candidate: Candidate, split: str
    ) -> None:
        await self._files.persist_evaluation(workspace=workspace, result=result, candidate=candidate, split=split)

    async def get_experiment_id(self, *, workspace: str, candidate: Candidate, split: str) -> str:
        return await self._files.get_experiment_id(workspace=workspace, candidate=candidate, split=split)

    async def get_agent_code(
        self, *, workspace: str, agent: str | Path, dest: Path, clone_depth: int | None = None
    ) -> AgentSource | None:
        # Git-sourced agents fetch identically regardless of backend (git transport).
        # A non-git "live" platform agent (fetched via the platform) is not supported yet.
        # Delegate to the local file backend so its captured _agent_source powers archival.
        if looks_like_git(str(agent)):
            return await self._files.get_agent_code(
                workspace=workspace, agent=agent, dest=dest, clone_depth=clone_depth
            )
        raise NotImplementedError

    async def archive_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        return await self._files.archive_candidate(workspace=workspace, candidate=candidate)

    async def publish_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        return await self._files.publish_candidate(workspace=workspace, candidate=candidate)

    async def list_traces(
        self,
        *,
        workspace: str,
        filter: dict[str, Any] | None,
        sort: str,
        mode: str,
        limit: int,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_trace(self, *, workspace: str, trace_id: str, mode: str) -> dict[str, Any]:
        raise NotImplementedError

    async def list_scores(self, *, workspace: str, span_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def get_agent(self, *, workspace: str, agent: str) -> Any:
        raise NotImplementedError

    async def get_agent_spec(self, *, workspace: str, spec: str, dest: Path) -> Path:
        return await self._files.get_agent_spec(workspace=workspace, spec=spec, dest=dest)


def _load_entity(cls: type[_ModelT], path: Path) -> _ModelT:
    """Deserialize *path* as JSON into *cls*, restoring the private ``_id`` field."""
    data = json.loads(path.read_text())
    entity_id = data.get("id", "")
    obj = cls.model_validate(data)
    if entity_id:
        cast(Any, obj)._id = entity_id  # PrivateAttr set the same way as the real entity client
    return obj


class LocalExperimentalistBackend(ExperimentalistBackend):
    """Persist entities under the optimizer's working directory (offline mode).

    Entity CRUD and result persistence land in local files under the same
    ``eval-and-optimize/`` tree that AAD created::

        {path}/
          eval-and-optimize/
            insight.json          ← loaded via get_insight(insight_id=path)
            run.json              ← ExperimentRun state
            agents/
              agent-0/
                metadata.json     ← Candidate fields
              agent-1/
                metadata.json
              ...
            analysis/
              round-0.md
              round-0-goal.json
              ...
            results/
            OPTIMIZATION.md       ← final report (same as AAD)

    Insight references may be local filesystem paths or Platform IDs. Dataset
    and agent-code references must be local filesystem paths.
    """

    def __init__(
        self,
        *,
        client: AsyncNeMoPlatform | None = None,
        path: Path,
        storage: CandidateStorageConfig | None = None,
    ) -> None:
        super().__init__(client, path, storage)
        self.path = path
        self._eo = path / "eval-and-optimize"
        for subdir in ("agents", "analysis", "results"):
            (self._eo / subdir).mkdir(parents=True, exist_ok=True)
        # Best-effort, one-way projection onto native platform Experiments. Active only when
        # a platform client is present (offline/local-only runs leave it a no-op); mirrors are
        # built lazily by ``_project_best_effort`` and cached per workspace so reusing this
        # backend across workspaces never projects into the wrong one.
        self._mirrors: dict[str, ExperimentMirror] = {}
        # Run-level git provenance captured by get_agent_code: the fetched AgentSource (repo,
        # ref, sub-path) and the local .git clone that is the push target. archive_candidate /
        # publish_candidate derive everything from these, so their signatures stay (workspace, candidate).
        self._agent_source: AgentSource | None = None
        self._agent_checkout: Path | None = None
        self._pr_url: str | None = None
        # label -> archived branch source_link, so re-projection keeps the real git link
        # (set by archive_candidate) instead of falling back to the pseudo placeholder.
        self._candidate_source_links: dict[str, str] = {}

    async def _project_best_effort(self, workspace: str, call: Callable[[ExperimentMirror], Awaitable[None]]) -> None:
        """Run a mirror projection best-effort (spec §3 / F).

        No-op when the backend has no platform client (pure-offline runs). Otherwise builds
        the workspace's mirror lazily (cached per workspace), runs *call* against it, and
        logs+swallows any failure so a projection problem can never fail the run or the
        local-file persistence. One-way: nothing read back into the loop.
        """
        if self.client is None:
            return
        mirror = self._mirrors.get(workspace)
        if mirror is None:
            mirror = self._mirrors[workspace] = ExperimentMirror(self.client, workspace)
        try:
            await call(mirror)
        except Exception as exc:  # noqa: BLE001 - projection must never fail the run
            logger.warning("[MIRROR] projection failed (run continues): %s", exc)

    # -- Insight read --------------------------------------------------------

    async def get_insight(self, *, workspace: str, insight_id: str) -> Insight:
        # A local insight file preserves offline behavior; otherwise treat
        # ``insight_id`` as a platform insight id and fetch it from the Insights
        # API. The dispatch is heuristic: an id that happens to match a path in
        # the cwd is read as a file, so callers wanting the platform must use an id
        # that isn't also a local path.
        p = Path(insight_id)
        if p.exists():
            return _load_entity(Insight, p)
        if self.client is None:
            raise ValueError(
                f"Insight {insight_id!r} is not an existing local file and no platform "
                "client is available to fetch it from the platform."
            )
        try:
            return await self.client.insights.insights.get(workspace=workspace, insight_id=insight_id)
        except httpx.HTTPStatusError as exc:
            # Surface as ValueError so the CLI's clean-error path reports it instead
            # of dumping a raw traceback (mirrors the local-file FileNotFoundError).
            if exc.response.status_code == 404:
                raise ValueError(f"Insight not found on the platform: {insight_id!r}") from exc
            raise ValueError(f"Failed to fetch insight {insight_id!r} from the platform: {exc}") from exc

    # -- Agent code access ---------------------------------------------------

    async def get_agent_code(
        self, *, workspace: str, agent: str | Path, dest: Path, clone_depth: int | None = None
    ) -> AgentSource | None:
        # Git source: clone (keeps .git for the PR push target) and return provenance.
        # Stash it so the mirror can use the real repo@ref as the baseline's source_link.
        if looks_like_git(str(agent)):
            self._agent_source = await self._clone_git_agent(str(agent), dest, clone_depth=clone_depth)
            self._agent_checkout = dest  # the .git clone is the archive/PR push target
            return self._agent_source
        # Local path: copy the agent into dest, replacing it (mirror clone_agent_repo)
        # so files removed from the local agent don't linger and get optimized/published
        # as stale code.
        src = Path(agent)
        if not src.exists():
            raise FileNotFoundError(f"Local agent path not found: {src}")
        if dest.resolve() != src.resolve():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=_ignore_agent_copy)
        return None

    def _candidate_branch(self, candidate: Candidate) -> str:
        """Deterministic archive branch for a candidate: ``<prefix>/<run-id>/<label>``."""
        return f"{self.storage.candidate_branch_prefix}/{candidate.run_id}/{candidate.label}"

    def _candidate_code_dir(self, candidate: Candidate) -> Path:
        """Local directory holding *candidate*'s code (the per-candidate agent dir)."""
        return self._eo / "agents" / candidate.label

    async def archive_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        """Git implementation: push ``<prefix>/<run-id>/<label>`` (subtree at the agent's
        ``agent_path``) cut from the source ref, and record ``{repo}@{branch}`` as the candidate's
        Experiment source_link. No-op (None) for a non-git source, or a skipped/empty-diff branch."""
        # Non-git source (local agent) or no checkout: nothing to push, so archival is a no-op.
        src = self._agent_source
        if src is None or self._agent_checkout is None:
            return None
        checkout, branch = self._agent_checkout, self._candidate_branch(candidate)
        code_dir = self._candidate_code_dir(candidate)
        message = (
            f"Experimentalist candidate {candidate.label} (round {candidate.round}): {candidate.optimization}\n\n"
            f"Candidate-Id: {candidate.id}"
        )
        pushed = await asyncio.to_thread(
            lambda: PRPublisher(agent_dir=checkout).push_branch(
                src_dir=code_dir, branch=branch, base_ref=src.ref, agent_path=src.agent_path, message=message
            )
        )
        if not pushed:
            return None
        # Record the branch as the candidate's real source_link and re-project its Experiment
        # so the mirror surfaces the git branch instead of the pseudo placeholder.
        link = f"{src.repo_url}@{branch}"
        self._candidate_source_links[candidate.label] = link
        await self._project_best_effort(
            workspace, lambda m: m.project_candidate(candidate, agent_source=src, source_link=link)
        )
        return link

    async def publish_candidate(self, *, workspace: str, candidate: Candidate) -> str | None:
        """Git implementation: open a draft PR/MR from the candidate's ``<prefix>/<run-id>/<label>``
        branch (title/body derived from the candidate + run summary + archived-branch links, per the
        ``storage`` PR options) and stash the URL for the winner's source_link. No-op (None) for a
        non-git source or empty diff."""
        # Non-git source or no checkout: cannot open a PR, so this is a no-op.
        src = self._agent_source
        if src is None or self._agent_checkout is None:
            return None
        checkout, branch = self._agent_checkout, self._candidate_branch(candidate)
        title = (
            self.storage.pr_title
            or f"Experimentalist: candidate {candidate.label} ({candidate.optimization_type or 'improvement'})"
        )
        body = self.storage.pr_body or await self._compose_pr_body(workspace=workspace, candidate=candidate)
        code_dir = self._candidate_code_dir(candidate)
        url = await asyncio.to_thread(
            lambda: PRPublisher(agent_dir=checkout).publish(
                winner_dir=code_dir,
                branch=branch,
                base_ref=src.ref,
                agent_path=src.agent_path,
                title=title,
                body=body,
                draft=self.storage.pr_draft,
                base_branch_override=self.storage.pr_base_branch,
                labels=self.storage.pr_labels,
            )
        )
        # Stash the PR URL so the mirror's finalize() records it on the winner's source_link.
        self._pr_url = url or None
        return url or None

    async def _compose_pr_body(self, *, workspace: str, candidate: Candidate) -> str:
        """Compose the winner PR body: run summary + links to every archived candidate branch."""
        run_path = self._eo / "run.json"
        run = _load_entity(ExperimentRun, run_path) if run_path.exists() else None
        summary = (run.summary if run is not None else None) or "Experimentalist run complete."
        if not self.storage.archive_candidates:
            return summary  # only the winner's branch exists; nothing else to link
        siblings = await self.list_candidates(workspace=workspace, run_id=candidate.run_id)
        lines = ["", "## Candidate branches", ""]
        for sib in siblings:
            if sib.label == _BASELINE_AGENT_LABEL:
                continue
            marker = " (winner)" if sib.label == candidate.label else ""
            reward = sib.validation_reward or sib.train_reward or {}
            lines.append(f"- `{sib.label}`{marker}: `{self._candidate_branch(sib)}` — reward={reward}")
        return summary + "\n" + "\n".join(lines) + "\n"

    # -- Intake reads and agent reads (PR #3) --------------------------------

    async def list_traces(
        self,
        *,
        workspace: str,
        filter: dict[str, Any] | None,
        sort: str,
        mode: str,
        limit: int,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get_trace(self, *, workspace: str, trace_id: str, mode: str) -> dict[str, Any]:
        raise NotImplementedError

    async def list_scores(self, *, workspace: str, span_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def get_agent(self, *, workspace: str, agent: str) -> Any:
        raise NotImplementedError

    async def get_agent_spec(self, *, workspace: str, spec: str, dest: Path) -> Path:
        src = Path(spec)
        if not src.is_file():
            raise FileNotFoundError(f"Agent spec not found: {src}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return dest

    # ------------------------------------------------------------------
    # ExperimentRun CRUD  (eval-and-optimize/run.json)
    # ------------------------------------------------------------------

    async def create_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        if not run.id:
            run._id = str(uuid.uuid4())  # type: ignore[attr-defined]
        (self._eo / "run.json").write_text(run.model_dump_json(indent=2))
        await self._project_best_effort(workspace, lambda m: m.ensure_group(run))
        return run

    async def update_run(self, *, workspace: str, run: ExperimentRun) -> ExperimentRun:
        (self._eo / "run.json").write_text(run.model_dump_json(indent=2))
        await self._project_best_effort(workspace, lambda m: m.update_group(run))
        return run

    # ------------------------------------------------------------------
    # Candidate CRUD  (eval-and-optimize/agents/{label}/metadata.json)
    #
    # The candidate ``label`` is the agent directory name (e.g. "agent-0").
    # Locally we use it as the entity id so lookup is O(1); remotely the store
    # assigns the id and auto-slugs ``name`` (identity is the id, as for every
    # entity in this plugin).
    # ------------------------------------------------------------------

    def _candidate_path(self, label: str) -> Path:
        if not label:
            raise ValueError("Label is required")
        return self._eo / "agents" / label / "metadata.json"

    def _load_candidate(self, path: Path) -> Candidate:
        """Deserialize a current-schema ``metadata.json`` file into a Candidate."""
        data = json.loads(path.read_text())
        candidate = Candidate.model_validate(data)
        # Restore private _id if present in the serialized form.
        entity_id = data.get("id", "")
        if entity_id:
            candidate._id = entity_id  # type: ignore[attr-defined]
        return candidate

    async def create_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        if not candidate.id:
            candidate._id = candidate.label or str(uuid.uuid4())  # type: ignore[attr-defined]
        p = self._candidate_path(candidate.label)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {**candidate.model_dump(exclude={"artifacts"}), "id": candidate.id},
                indent=2,
            )
        )
        await self._project_best_effort(
            workspace,
            lambda m: m.project_candidate(
                candidate,
                agent_source=self._agent_source,
                source_link=self._candidate_source_links.get(candidate.label),
            ),
        )
        return candidate

    async def update_candidate(self, *, workspace: str, candidate: Candidate) -> Candidate:
        p = self._candidate_path(candidate.label)
        p.write_text(
            json.dumps(
                {**candidate.model_dump(exclude={"artifacts"}), "id": candidate.id},
                indent=2,
            )
        )
        await self._project_best_effort(
            workspace,
            lambda m: m.project_candidate(
                candidate,
                agent_source=self._agent_source,
                source_link=self._candidate_source_links.get(candidate.label),
            ),
        )
        return candidate

    async def get_candidate(self, *, workspace: str, candidate_id: str) -> Candidate:
        # In local mode the store id equals the candidate label (e.g. "agent-0"),
        # which is also the agent directory name.
        p = self._candidate_path(candidate_id)
        return self._load_candidate(p)

    async def list_candidates(self, *, workspace: str, run_id: str) -> list[Candidate]:
        results: list[Candidate] = []
        agents_dir = self._eo / "agents"
        for meta in sorted(agents_dir.glob("*/metadata.json")):
            c: Candidate = self._load_candidate(meta)
            if c.run_id == run_id:
                results.append(c)
        return results

    # ------------------------------------------------------------------
    # Result persistence  (eval-and-optimize/OPTIMIZATION.md)
    # ------------------------------------------------------------------

    async def persist_evaluation(
        self, *, workspace: str, result: EvaluationResult, candidate: Candidate, split: str
    ) -> None:
        """Persist traces and metrics for a completed evaluation.

        Side effect: For trials with local file:// traces, uploads to Intake and rewrites
        trial.trace.uri to intake://traces/{id}. Original URI preserved in metadata.

        TODO(future): Uploading traces can be slow (large payloads, many trials). Consider
        moving this to a background task so the optimization loop can continue without
        blocking on Intake I/O. The loop would need to either: (a) await the background
        task before _reward_trajectories (which reads intake:// URIs), or (b) fall back
        to reading local file:// traces if upload is still in progress.
        """
        if self.client is None:
            return  # pure-offline run: traces stay on local disk

        # Derive experiment_id internally (ensures entity exists, returns deterministic name)
        experiment_id = await self.get_experiment_id(workspace=workspace, candidate=candidate, split=split)
        if not experiment_id:
            return  # projection failed (shouldn't happen, but defensive)

        agent_attrs = {
            k: str(result.metadata[k])
            for k in ("gen_ai.agent.name", "agent.version", "gen_ai.request.model")
            if k in result.metadata
        }
        for trial in result.trials:
            if trial.trace is None:
                continue
            try:
                await self._persist_trial(
                    trial, workspace=workspace, experiment_id=experiment_id, agent_attrs=agent_attrs
                )
            except Exception as exc:  # noqa: BLE001 - Intake persistence is best-effort
                logger.warning(f"[INTAKE] persist_evaluation failed for trial {trial.id}: {exc}")

    async def _persist_trial(
        self, trial: TrialResult, *, workspace: str, experiment_id: str, agent_attrs: dict[str, str]
    ) -> None:
        assert trial.trace is not None
        assert self.client is not None
        uri = trial.trace.uri
        if uri.startswith("intake://"):
            trace_id = uri.removeprefix("intake://traces/")
            trace = await self._retrieve_trace_with_retry(trace_id, workspace=workspace)
            ctx = getattr(trace, "evaluation_context", None)
            if ctx is None or getattr(ctx, "evaluation_id", None) != experiment_id:
                rows: list[dict] = []
                async for span in self.client.intake.spans.list(
                    workspace=workspace,
                    filter=cast(Any, {"trace_id": trace_id}),
                    mode="detailed",
                    page_size=1000,
                ):
                    rows.append(span.model_dump(mode="json", exclude_none=True))
                attrs = {
                    "nemo.experiment.id": experiment_id,
                    "nemo.test_case.id": trial.task_id,
                    "nemo.trial.id": trial.id,
                    **agent_attrs,
                }
                url = f"/apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces"
                for payload in spans_to_protobuf(rows, attrs):
                    await self.client.post(
                        url,
                        cast_to=object,
                        content=payload,
                        options={"headers": {"Content-Type": "application/x-protobuf"}},
                    )
                trace = await self._retrieve_trace_with_retry(trace_id, workspace=workspace)
        else:
            try:
                trace_id = read_trace_id(trial.trace)
            except (ValueError, json.JSONDecodeError, FileNotFoundError) as exc:
                # Empty, invalid, or missing trace file (e.g., cancelled trial) — skip upload
                logger.debug(f"[INTAKE] No valid trace found for trial {trial.id}: {exc}; skipping upload")
                return
            original_uri = uri
            await _upload_trace_otlp(
                self.client,
                workspace,
                trial.trace,
                experiment_id=experiment_id,
                trial_id=trial.id,
                task_id=trial.task_id,
                extra_attrs=agent_attrs,
            )
            trial.trace = ResourceRef(
                uri=f"intake://traces/{trace_id}",
                description=trial.trace.description,
                metadata={**trial.trace.metadata, "local_uri": original_uri},
            )
            trace = await self._retrieve_trace_with_retry(trace_id, workspace=workspace)
        for name, metric in trial.metrics.items():
            await self.client.intake.evaluator_results.create(
                workspace=workspace,
                span_id=trace.root_span_id,
                session_id=trace.session_id,
                name=name,
                value=float(metric.value),
                data_type="NUMERIC",
            )

    async def _retrieve_trace_with_retry(
        self, trace_id: str, *, workspace: str, retries: int = 5, initial_delay: float = 1.0
    ) -> Any:
        """Retrieve trace with exponential backoff.

        Intake indexing after OTLP upload can take several seconds. Uses exponential
        backoff: 1s, 2s, 4s, 8s, 16s (up to 31s total) by default.
        """
        from nemo_platform import NotFoundError

        assert self.client is not None
        last_exc: Exception = RuntimeError(f"trace {trace_id!r} not found after {retries} retries")
        delay = initial_delay
        for attempt in range(retries):
            try:
                return await self.client.intake.traces.retrieve(trace_id, workspace=workspace)
            except NotFoundError as exc:
                last_exc = exc
                if attempt < retries - 1:  # Don't sleep after the last attempt
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
        raise last_exc

    async def get_experiment_id(self, *, workspace: str, candidate: Candidate, split: str) -> str:
        if self.client is None:
            return ""
        mirror = self._mirrors.get(workspace)
        if mirror is None:
            mirror = self._mirrors[workspace] = ExperimentMirror(self.client, workspace)
        try:
            return await mirror.ensure_experiment(candidate, split=split)
        except Exception as exc:  # noqa: BLE001 - projection is best-effort
            logger.warning("[MIRROR] ensure_experiment failed: %s", exc)
            return ""

    async def persist_result(self, *, workspace: str, result: ExperimentalistResult) -> None:
        report_path = self._eo / "OPTIMIZATION.md"
        # The optimizer's report writer creates the full document before this call.
        # Use the compact result summary only as a fallback when no report was produced.
        if not report_path.exists() or not report_path.read_text().strip():
            report_path.write_text(result.summary)
        run_path = self._eo / "run.json"
        if run_path.exists():
            run: ExperimentRun = _load_entity(ExperimentRun, run_path)
            run.status = "completed"
            run.rounds_completed = result.rounds_completed
            run.summary = result.summary  # so publish_candidate's _compose_pr_body reads the real summary
            if result.winner is not None:
                run.winner_agent = result.winner.id
            run_path.write_text(run.model_dump_json(indent=2))
        await self._project_best_effort(
            workspace,
            lambda m: m.finalize(
                run_id=result.run_id, summary=result.summary, winner=result.winner, pr_url=self._pr_url
            ),
        )


def make_experimentalist_backend(
    *,
    client: AsyncNeMoPlatform | None,
    experiments_output: str,
    mode: Literal["local", "remote"],
    storage: CandidateStorageConfig | None = None,
) -> ExperimentalistBackend:
    """Select the experimentalist backend based on *mode*.

    When *mode* is "local", entity state is written to that local directory using the
    ``eval-and-optimize/`` tree layout. Otherwise, the platform-backed backend is selected.

    Args:
        client(AsyncNeMoPlatform | None): Optional platform API client for local
            runs. Remote mode requires a client.
        experiments_output(str): Optional local output directory.
        mode(Literal["local", "remote"]): The backend mode.
        storage(CandidateStorageConfig | None): Candidate-archival / winner-PR settings.
    Returns:
        ExperimentalistBackend: The experimentalist backend.
    """
    if mode == "local":
        return LocalExperimentalistBackend(client=client, path=Path(experiments_output), storage=storage)
    if client is None:
        raise ValueError("remote Experimentalist backend requires a platform client")
    return RemoteExperimentalistBackend(client=client, path=Path(experiments_output), storage=storage)
