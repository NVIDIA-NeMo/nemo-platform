# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""One-way, best-effort projection of the plugin's run/candidate entities onto the
platform's native ``ExperimentGroup``/``Experiment``.

This module is the *only* place that talks to ``client.experiments`` /
``client.evaluations``; the optimization loop never imports it. Mapping is
``ExperimentRun → ExperimentGroup`` (1:1) and ``Candidate → Experiment[]`` (one per
evaluated split). It mirrors **structure only** (identity/lineage/status/description);
eval results (reward/trials) are NOT copied into ``Experiment.metadata`` — those arrive
via the Intake rollup path later (spec §4.3).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_platform import AsyncNeMoPlatform, ConflictError, NotFoundError, omit

logger = logging.getLogger(__name__)

SPLITS: tuple[str, ...] = ("train", "validation", "insight")
_NAME_RE = re.compile(r"[^a-z0-9-]+")


def _slug(value: str) -> str:
    return _NAME_RE.sub("-", value.lower()).strip("-") or "run"


def group_name(run_id: str) -> str:
    """Deterministic, workspace-unique ExperimentGroup name from the run id."""
    return f"opt-{_slug(run_id)}"[:63].rstrip("-")


def experiment_name(gname: str, label: str, split: str) -> str:
    """Deterministic, workspace-unique Experiment name (one per candidate × split).

    ``label`` is sanitized with the same ``_slug`` as the group's run id. If the composed
    name would exceed the platform's 63-char limit, a short deterministic hash suffix
    preserves uniqueness — so distinct candidates/splits can never truncate onto the same
    name and silently overwrite each other via the create→conflict→update upsert path.
    """
    name = f"{gname}-{_slug(label)}-{split}"
    if len(name) <= 63:
        return name
    digest = hashlib.sha1(name.encode()).hexdigest()[:8]  # noqa: S324 - identity, not security
    return f"{name[:54].rstrip('-')}-{digest}"


def pseudo_source_link(gname: str, label: str) -> str:
    """Fallback grouping-key URI, stable per candidate across its splits (OQ-4)."""
    return f"opt://{gname}/candidate/{label}"


def experiment_status(candidate: Candidate) -> str:
    """Derive the producer status string from candidate lineage (spec §4.1)."""
    if candidate.killed_round is not None:
        return "killed"
    if candidate.round == 0:
        return "baseline"
    return "survived"


def group_metadata(run: ExperimentRun) -> dict[str, str]:
    """The ExperimentRun fields with no first-class ExperimentGroup home (spec §4.1).

    Platform ``metadata`` is ``dict[str, str]``: every value must be a string. Non-string
    fields are serialized (``config_snapshot`` as JSON, ``rounds_completed`` via ``str``);
    ``winner_candidate`` is omitted until a winner exists rather than sent as ``None``.
    """
    md = {
        "agent": run.agent,
        "config_snapshot": json.dumps(run.config_snapshot, sort_keys=True),
        "status": run.status,
        "rounds_completed": str(run.rounds_completed),
    }
    if run.winner_agent is not None:
        md["winner_candidate"] = run.winner_agent
    return md


def experiment_metadata(candidate: Candidate, split: str) -> dict[str, str]:
    """Identity/grouping metadata only. Eval results (reward/trials) are NOT copied this
    PR — scores/traces arrive via the Intake rollup path later (spec §4.3).

    Platform ``metadata`` is ``dict[str, str]``, so ``round`` is serialized via ``str``."""
    return {"round": str(candidate.round), "candidate_id": candidate.label, "split": split}


def _split_reward(candidate: Candidate, split: str) -> Any:
    """The candidate's reward object for *split* — an explicit lookup over the known
    split fields (``train_reward``/``validation_reward``/``insight_reward``) rather
    than a dynamic attribute read. Used only as a presence check: the reward value
    itself is never projected."""
    return {
        "train": candidate.train_reward,
        "validation": candidate.validation_reward,
        "insight": candidate.insight_reward,
    }[split]


class ExperimentMirror:
    """Best-effort, one-way projection to native Experiments. Callers wrap each method
    so failures don't propagate (spec F)."""

    def __init__(self, client: AsyncNeMoPlatform, workspace: str) -> None:
        self._client = client
        self._workspace = workspace
        self._group_ids: dict[str, str] = {}  # run_id -> ExperimentGroup id
        self._experiment_ids: dict[tuple[str, str], str] = {}  # (label, split) -> Experiment id

    # -- ExperimentGroup ----------------------------------------------------

    async def ensure_group(self, run: ExperimentRun) -> None:
        gname = group_name(run.id)
        try:
            grp = await self._client.experiments.create(
                workspace=self._workspace,
                name=gname,
                insight_id=run.insight or omit,
                summary=run.summary or "",
                metadata=group_metadata(run),
            )
        except ConflictError:
            grp = await self._client.experiments.retrieve(gname, workspace=self._workspace)
        self._group_ids[run.id] = grp.id

    async def update_group(self, run: ExperimentRun) -> None:
        gname = group_name(run.id)
        # experiments.update is a full-replace PUT: omitted fields reset to None
        # server-side, so re-supply the whole body (we have the run).
        await self._client.experiments.update(
            gname,
            workspace=self._workspace,
            body_name=gname,
            summary=run.summary or "",
            insight_id=run.insight or omit,
            metadata=group_metadata(run),
        )

    async def _group_id_for(self, run_id: str) -> str:
        gid = self._group_ids.get(run_id)
        if gid is None:  # resume path: group exists, look it up by deterministic name
            grp = await self._client.experiments.retrieve(group_name(run_id), workspace=self._workspace)
            gid = self._group_ids[run_id] = grp.id
        return gid

    # -- Experiment ---------------------------------------------------------

    async def ensure_experiment(self, candidate: Candidate, split: str) -> str:
        """Ensure the Experiment exists for candidate × split; return its deterministic
        name (``opt-<run>-<label>-<split>``).

        The name — not the server-assigned id (``experiment-…``) — is what tags the trace's
        ``nemo.experiment.id``: it is human-readable, greppable, and stable across resumes,
        and matches the Experiment's own ``name`` so the trace still joins back to it.
        """
        gname = group_name(candidate.run_id)
        gid = await self._group_id_for(candidate.run_id)
        await self._upsert_experiment(
            candidate=candidate,
            split=split,
            gname=gname,
            group_id=gid,
            agent_source=None,
        )
        return experiment_name(gname, candidate.label, split)

    async def project_candidate(
        self, candidate: Candidate, *, agent_source: Any = None, source_link: str | None = None
    ) -> None:
        gname = group_name(candidate.run_id)
        gid = await self._group_id_for(candidate.run_id)
        for split in SPLITS:
            if _split_reward(candidate, split) is None:
                continue  # split not evaluated yet (presence check only — reward is NOT copied)
            await self._upsert_experiment(
                candidate=candidate,
                split=split,
                gname=gname,
                group_id=gid,
                agent_source=agent_source,
                source_link=source_link,
            )

    async def _upsert_experiment(
        self,
        *,
        candidate: Candidate,
        split: str,
        gname: str,
        group_id: str,
        agent_source: Any,
        source_link: str | None = None,
        status: str | None = None,
    ) -> None:
        name = experiment_name(gname, candidate.label, split)
        link = source_link or self._source_link(gname, candidate, agent_source)
        parent = await self._parent_experiment_id(candidate, gname)
        parent_id = parent if parent is not None else omit
        st = status or experiment_status(candidate)
        md = experiment_metadata(candidate, split)  # identity only — no reward/trials (§4.3)
        try:
            exp = await self._client.evaluations.create(
                name=name,
                dataset_name=self._dataset_name(split),
                dataset_version="v1",
                workspace=self._workspace,
                experiment_ids=[group_id],
                source_link=link,
                description=candidate.optimization,
                parent_evaluation_id=parent_id,
                root_cause="",  # OQ-RC: left empty for now
                status=st,
                metadata=md,
            )
        except ConflictError:
            exp = await self._client.evaluations.update(
                name,
                workspace=self._workspace,
                dataset_name=self._dataset_name(split),
                dataset_version="v1",
                body_name=name,
                experiment_ids=[group_id],
                source_link=link,
                description=candidate.optimization,
                parent_evaluation_id=parent_id,
                root_cause="",  # OQ-RC: left empty for now
                status=st,
                metadata=md,
            )
        self._experiment_ids[(candidate.label, split)] = exp.id

    def _dataset_name(self, split: str) -> str:
        return split  # OQ-8: derive a real dataset name/version later

    def _source_link(self, gname: str, candidate: Candidate, agent_source: Any) -> str:
        if candidate.round == 0 and agent_source is not None:
            return f"{agent_source.repo_url}@{agent_source.ref}"
        return pseudo_source_link(gname, candidate.label)

    async def _existing_source_link(self, gname: str, label: str, split: str) -> str | None:
        """The source_link already stored for this candidate/split, or None.

        ``finalize`` re-upserts the winner via a full-replace update without the run's
        ``agent_source``; reusing the link written during the run keeps a round-0 seed's real
        ``{repo}@{ref}`` from being clobbered with a pseudo link when no PR was opened."""
        try:
            exp = await self._client.evaluations.retrieve(
                experiment_name(gname, label, split), workspace=self._workspace
            )
        except NotFoundError:
            return None
        return exp.source_link

    async def _parent_experiment_id(self, candidate: Candidate, gname: str) -> str | None:
        if not candidate.ancestor:
            return None
        cached = self._experiment_ids.get((candidate.ancestor, "train"))
        if cached is not None:
            return cached
        try:  # resume / ancestor created earlier this run
            exp = await self._client.evaluations.retrieve(
                experiment_name(gname, candidate.ancestor, "train"), workspace=self._workspace
            )
        except NotFoundError:
            logger.debug(
                "Ancestor experiment %r not found for candidate %r; lineage link omitted",
                experiment_name(gname, candidate.ancestor, "train"),
                candidate.label,
            )
            return None
        self._experiment_ids[(candidate.ancestor, "train")] = exp.id
        return exp.id

    # -- Finalize -----------------------------------------------------------

    async def finalize(self, *, run_id: str, summary: str, winner: Candidate | None, pr_url: str | None = None) -> None:
        gname = group_name(run_id)
        gid = await self._group_id_for(run_id)
        # experiments.update is a full-replace PUT: omitted fields reset to None
        # server-side. finalize has no `run`, so read-preserve-write the current
        # insight_id/metadata before writing the summary (stays within the mirror; no
        # data flows back into the loop).
        grp = await self._client.experiments.retrieve(gname, workspace=self._workspace)
        await self._client.experiments.update(
            gname,
            workspace=self._workspace,
            body_name=gname,
            summary=summary,
            insight_id=grp.insight_id if grp.insight_id is not None else omit,
            metadata=grp.metadata if grp.metadata is not None else omit,
        )
        if winner is None:
            return
        # The winner's Experiment is always status="winner"; whether a PR was opened is
        # captured in source_link (=pr_url), so a separate "deployed" status would be
        # redundant (and "deployed" overstates a draft PR). With no PR, preserve the
        # source_link stored during the run so a round-0 winner's real {repo}@{ref} isn't
        # clobbered by the full-replace update (agent_source isn't threaded into finalize).
        for split in SPLITS:
            if _split_reward(winner, split) is None:
                continue
            link = pr_url or await self._existing_source_link(gname, winner.label, split)
            await self._upsert_experiment(
                candidate=winner,
                split=split,
                gname=gname,
                group_id=gid,
                agent_source=None,
                source_link=link,
                status="winner",
            )
