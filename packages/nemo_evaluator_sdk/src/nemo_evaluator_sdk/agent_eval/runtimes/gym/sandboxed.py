# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Collect Gym rollouts from a sandboxed Gym host instead of a local ``gym`` CLI.

:class:`~nemo_evaluator_sdk.agent_eval.runtimes.gym.runtime.GymAgentTaskRunner` runs Gym as a
subprocess tree in this process's own environment: it needs the ``gym`` executable on PATH and a
Gym checkout as its working directory, and whatever the environment's ``resources_server`` code
does, it does with this process's credentials. That is fine for a vetted environment on trusted
hardware and unacceptable once the environment arrives as a user-supplied FileSet, which is the
case the sandboxed-GRPO RFC exists for (§2.3).

This runner keeps everything about the evaluation the same and changes only where the rollouts are
produced. The dataset is materialized identically, the rollout records are read back through the
same parser, and the same coverage check runs -- so a run here and a run there are comparable, and
a scoring bug cannot hide in one path but not the other. What differs is one step: instead of
driving ``gym env start`` and ``gym eval run``, it POSTs the rows as ``examples`` to a sandboxed
host's ``/rollouts/run`` and writes the returned records where the parser expects them.

Attribution survives that hop because the host copies each example's ``_ng_task_index`` onto its
result. Nothing here joins by position.

The host itself is provisioned by ``sandboxed-gym``: start a session, take its rollout URL and
token off the descriptor, and hand them to this runner.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from nemo_evaluator_sdk.agent_eval.runtimes.gym.config import DEFAULT_REWARD_KEY
from nemo_evaluator_sdk.agent_eval.runtimes.gym.dataset import _materialize_dataset, _source_datasets
from nemo_evaluator_sdk.agent_eval.runtimes.gym.results import (
    _aggregate_scores_from_gym,
    _ensure_fresh_output,
    _read_run_aggregations,
    _require_full_coverage,
    _trials_from_rollouts,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial, RunnerInfo
from nemo_evaluator_sdk.values.results import AggregateScore
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

#: Auth header the orchestrator proxy expects. Mirrors ``sandboxed_gym.wire.PROXY_AUTH_HEADER``,
#: duplicated rather than imported so this module carries no dependency on that package: a caller
#: who has a session descriptor already has the token, and the header name is part of the contract.
PROXY_AUTH_HEADER = "X-Sandboxed-Gym-Token"


class SandboxedGymRuntimeConfig(BaseModel):
    """Where to reach a running sandboxed Gym host, and how to read its rollouts."""

    model_config = ConfigDict(extra="forbid")

    rollout_url: str = Field(description="The session's `/rollouts/run` URL, from its descriptor.")
    auth_token: str | None = Field(
        default=None,
        description="Bearer token for the orchestrator proxy (`rollout_auth_token` on the descriptor).",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Extra headers the host requires, e.g. the OpenSandbox proxy headers on its endpoint.",
    )
    timeout_s: float = Field(
        default=3600.0,
        gt=0,
        description="Ceiling on one rollout collection. Covers every example in the run, not each one.",
    )
    agent_ref_name: str | None = Field(
        default=None,
        description="Gym agent instance each example is routed to, stamped as `agent_ref` on rows that do "
        "not already carry one. Required by the host path: `RolloutCollectionHelper.run_examples` reads "
        "`row['agent_ref']['name']` with no fallback, while the `gym eval run` CLI resolves the agent from "
        "config instead -- so a dataset that runs under the CLI can arrive here unroutable. This is the "
        "instance an environment's config defines (`mcqa_simple_agent`), not the agent component "
        "(`simple_agent`).",
    )
    reward_key: str = Field(default=DEFAULT_REWARD_KEY, description="Key read from each rollout record.")


class SandboxedGymAgentTaskRunner:
    """An ``AgentTaskRunner`` that collects rollouts from a sandboxed Gym host over HTTP."""

    def __init__(self, *, config: SandboxedGymRuntimeConfig) -> None:
        self._config = config
        self._run_aggregations: dict[str, Any] | None = None

    def run_aggregate_scores(self) -> Sequence[AggregateScore]:
        """Gym's ``agent_metrics`` as typed aggregate scores, namespaced ``runner.gym.<metric>``.

        Empty in practice today: those numbers come from a sidecar the CLI writes, and a host that
        returns rollout records writes no such file. Implemented anyway so this runner satisfies the
        same protocol as the CLI one and starts reporting if the host grows the sidecar.
        """
        return _aggregate_scores_from_gym(self._run_aggregations)

    def runner_info(self) -> RunnerInfo:
        """Identify the runner and the host it collected from.

        The token is omitted rather than redacted: unlike Gym's free-form ``hydra_params``, there is
        exactly one credential here and nothing about it is worth recording.
        """
        cfg = self._config
        return RunnerInfo(
            name="gym",
            kind="runner",
            config={
                "mode": "sandboxed",
                "rollout_url": cfg.rollout_url,
                "agent_ref_name": cfg.agent_ref_name,
                "reward_key": cfg.reward_key,
                "timeout_s": cfg.timeout_s,
            },
        )

    def _request_headers(self) -> dict[str, str]:
        headers = dict(self._config.headers)
        if self._config.auth_token is not None:
            headers[PROXY_AUTH_HEADER] = self._config.auth_token
        return headers

    async def _collect(self, examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """POST the examples and return the host's rollout records."""
        async with httpx.AsyncClient(timeout=self._config.timeout_s) as client:
            response = await client.post(
                self._config.rollout_url,
                json={"examples": examples},
                headers=self._request_headers(),
            )
        if response.status_code >= 400:
            # The body is the host's own error envelope; it names which example or server failed,
            # which the status code alone does not.
            raise RuntimeError(
                f"sandboxed Gym host returned {response.status_code} from {self._config.rollout_url}: "
                f"{response.text[:2000]}"
            )
        body = response.json()
        error = body.get("error") if isinstance(body, Mapping) else None
        if error is not None:
            # The host commits its 200 before the batch finishes, so that it can hold the
            # connection open past the sandbox proxy's first-byte cap. A failure after that point
            # has only the body left to travel in, and carries the code and traceback that say
            # which of Gym's layers raised.
            raise RuntimeError(
                f"sandboxed Gym host reported an error from {self._config.rollout_url}: "
                f"{error if isinstance(error, str) else json.dumps(error)[:2000]}"
            )
        results = body.get("results") if isinstance(body, Mapping) else None
        if not isinstance(results, list):
            raise RuntimeError(
                f"sandboxed Gym host returned no `results` list from {self._config.rollout_url}; "
                f"got {type(results).__name__}"
            )
        return [record for record in results if isinstance(record, dict)]

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalTrial]:
        self._run_aggregations = None  # reset per run so a reused runner never leaks prior numbers
        cfg = self._config

        if config is not None and config.work_dir is not None:
            work_dir = Path(config.work_dir) / "gym_run"
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="gym_sandboxed_run_"))
        work_dir.mkdir(parents=True, exist_ok=True)

        rollouts_path = work_dir / "rollouts.jsonl"
        _ensure_fresh_output(rollouts_path)

        # Same materialization the CLI runner uses, so the rows the host sees are the rows Gym
        # would have read, and `_ng_task_index` is stamped by the same code.
        input_path = work_dir / "gym_input.jsonl"
        index_to_task_id = _materialize_dataset(tasks, input_path)
        examples = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if cfg.agent_ref_name:
            # Only where the row is silent: a dataset that names its own agent per row keeps doing so,
            # which is how multi-agent Gym datasets are meant to work.
            for example in examples:
                example.setdefault("agent_ref", {"name": cfg.agent_ref_name})
        logger.info(
            "Collecting %d example(s) from %s via sandboxed Gym host %s.",
            len(examples),
            _source_datasets(tasks),
            cfg.rollout_url,
        )

        records = await self._collect(examples)

        # Written where the parser expects it, so the records are read by exactly the code that
        # reads the CLI runner's output -- including its handling of records with no usable index.
        rollouts_path.write_text(
            "".join(f"{json.dumps(record)}\n" for record in records),
            encoding="utf-8",
        )

        self._run_aggregations = _read_run_aggregations(rollouts_path)
        trials = _trials_from_rollouts(rollouts_path, tasks, index_to_task_id, reward_key=cfg.reward_key)
        _require_full_coverage(tasks, covered_task_ids={trial.task_id for trial in trials}, rollouts_path=rollouts_path)
        return trials
