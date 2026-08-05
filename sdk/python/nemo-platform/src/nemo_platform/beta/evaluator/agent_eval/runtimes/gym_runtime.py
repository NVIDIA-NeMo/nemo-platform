# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo Gym-backed :class:`AgentTaskRunner` for the agent-eval pipeline.

Runs an *existing* NeMo Gym environment through its ``gym`` CLI and adapts the
rollout bundle into SDK :class:`AgentEvalTrial` objects, so an
:class:`AgentEvaluator` can score and report Gym runs through the same seam as
Harbor/Fabric/Model. Gym owns execution *and* scoring; this runtime imports an
existing Gym environment as-is — Gym is treated as a self-scoring engine and the
runtime only adapts its rollout bundle, it does not re-derive rewards.

**Mapping** (Gym → Evaluator): one Gym dataset → one run; each distinct row →
one :class:`AgentEvalTask` (id = content hash of the row); each attempt
(``_ng_rollout_index``) → one :class:`AgentEvalTrial`; the per-attempt verifier
``reward`` → a :class:`GymRewardMetric` score. ``num_repeats=R`` therefore yields
up to R trials per task. Row duplication is *not* a way to ask for repeated
attempts — ``num_repeats`` is (see :func:`discover_gym_tasks`).

**Attribution** is by ``_ng_task_index``, which this runtime *assigns* rather
than infers. Gym only auto-assigns an index when a row doesn't already carry one
(``rollout_collection._preprocess_rows_from_config``), and its own fallback
dedup keys off the **raw jsonl line text** — a rule we cannot reproduce from
parsed rows. So instead of guessing, :meth:`GymAgentTaskRunner.run_tasks`
materializes a normalized dataset (one line per requested task, ``_ng_task_index``
stamped explicitly) and feeds *that* to Gym. Gym echoes the index back on every
rollout record, giving a total, order-independent ``index → task`` map. This also
means a caller can run a **subset** of tasks without Gym rolling out the rest.

**Execution** is the two-step Gym flow (the one that reads a dataset directly
without triggering Gym's split-driven data-prep): ``gym env start`` brings up the
resources-server + agent + model servers, then ``gym eval run --no-serve --input
<materialized dataset>`` collects rollouts against them. The runtime shells out
to the ``gym`` executable in the caller-provided ``gym_root`` checkout — Gym
resolves its environments from that repo and reads credentials from its
(gitignored) ``env.yaml`` — so this SDK never imports ``nemo_gym`` and never
handles secrets. Subprocess output is streamed to log files under the run's work
dir *and* mirrored to this module's logger at ``DEBUG``, so callers choose
terminal visibility through ordinary ``logging`` configuration.

**Boundaries**: the caller is responsible for a
Gym runtime whose deps are installed (each Gym env ships its own
``requirements.txt``), and for handing a *ready-to-run* dataset file (``--no-serve
--input`` bypasses Gym's prompt-templating/materialization). Service-side
provisioning (docker/k8s, Ray) is out of scope here — that is the plugin's job.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import tempfile
from collections import deque
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.tasks import AgentEvalRunConfig, AgentEvalTask
from nemo_platform.beta.evaluator.agent_eval.trials import AgentEvalTrial, AgentEvalTrialStatus, AgentOutput, RunnerInfo
from nemo_platform.beta.evaluator.metrics.protocol import MetricInput, MetricOutput, MetricOutputSpec, MetricResult
from nemo_platform.beta.evaluator.values.evidence import CandidateEvidence, EvidenceDescriptor
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

#: Reward key read from each Gym rollout record.
DEFAULT_REWARD_KEY = "reward"
#: Gym's index fields on each rollout record. ``_ng_task_index`` is the only join back to the input
#: rows that survives a round-trip: Gym mutates ``responses_create_params`` (even the prompt) and
#: copies only a fixed allowlist of row keys onto the result, so no field we invent comes back. Gym
#: *honors* a caller-supplied ``_ng_task_index``, which is what makes the join here deterministic.
NG_TASK_INDEX = "_ng_task_index"
NG_ROLLOUT_INDEX = "_ng_rollout_index"
#: Fields excluded from a row's content hash (runtime-injected, not task-defining).
_RUNTIME_KEYS = frozenset({NG_TASK_INDEX, NG_ROLLOUT_INDEX})
#: Lines of subprocess output retained in memory for inclusion in a failure message.
_LOG_TAIL_LINES = 40


#: Substrings that mark a Hydra override key as carrying a credential. Matched case-insensitively
#: against the key half of ``+key=value``.
_SECRET_KEY_MARKERS = ("api_key", "apikey", "token", "secret", "password", "passwd", "credential")
#: Stand-in written in place of a redacted override value.
_REDACTED = "<redacted>"


def _redact_env_overrides(overrides: Sequence[str]) -> list[str]:
    """Redact credential-looking values from Hydra overrides before they are recorded as provenance.

    ``env_overrides`` is a free-form escape hatch forwarded verbatim to ``gym env start``, so nothing
    stops a caller passing ``+model.api_key=sk-...``. ``RunnerInfo.config`` is persisted into the run
    bundle, so a value that looks like a credential must not be written there.

    The *key* is always kept — knowing that a run overrode ``model.api_key`` is useful provenance;
    knowing the value is a leak. Overrides that don't parse as ``key=value`` are kept verbatim: they
    carry no value to leak.
    """
    redacted: list[str] = []
    for override in overrides:
        key, sep, _ = override.partition("=")
        if sep and any(marker in key.casefold() for marker in _SECRET_KEY_MARKERS):
            redacted.append(f"{key}={_REDACTED}")
        else:
            redacted.append(override)
    return redacted


def _canonical_row_hash(row: Mapping[str, Any]) -> str:
    """Stable ``sha256`` of a Gym dataset row, excluding runtime-injected fields.

    A given row keeps its id across dataset revisions/reorderings (so Intake
    rollups stay consistent), and a changed row becomes a new task. No
    dataset-revision component — identity is the row content alone.
    """
    payload = {key: value for key, value in row.items() if key not in _RUNTIME_KEYS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _content_text(content: Any) -> str:
    """Flatten a message ``content`` (a string, or a list of ``{type,text}`` parts) to text.

    Anything else contributes nothing. A missing ``content`` is unremarkable, but a *populated* value
    in some other shape means we're silently dropping prompt text, so warn — :func:`_render_instruction`
    only fails loudly when the whole row renders empty, which a single skipped message wouldn't trigger.
    """
    if isinstance(content, str):
        return content
    # `str` is itself a Sequence, so this branch only ever sees non-str sequences (handled above).
    if isinstance(content, Sequence):
        parts = [part["text"] for part in content if isinstance(part, Mapping) and isinstance(part.get("text"), str)]
        return "\n".join(parts)
    if content is not None:
        logger.warning(
            "Ignoring message content of unsupported type %s (expected a string or a list of {type,text} parts); "
            "any prompt text it carries will be missing from the task instruction.",
            type(content).__name__,
        )
    return ""


def _render_instruction(responses_create_params: Any) -> str:
    """Derive a non-empty instruction from a row's ``responses_create_params``.

    Uses ``instructions`` (system prompt, when present) + ``input`` (a plain string
    or an OpenAI message list). ``instruction`` is required on every task, so a row
    that cannot produce one fails loudly rather than yielding a task with no prompt.
    """
    if not isinstance(responses_create_params, Mapping):
        raise ValueError("row has no 'responses_create_params' mapping to render an instruction from")
    parts: list[str] = []
    instructions = responses_create_params.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        parts.append(instructions.strip())
    raw_input = responses_create_params.get("input")
    if isinstance(raw_input, str):
        parts.append(raw_input)
    elif isinstance(raw_input, Sequence):
        for item in raw_input:
            if isinstance(item, Mapping):
                text = _content_text(item.get("content"))
                if text:
                    parts.append(text)
    instruction = "\n\n".join(part for part in parts if part).strip()
    if not instruction:
        raise ValueError("could not derive a non-empty instruction from responses_create_params.input")
    return instruction


def _read_jsonl(path: str | Path, *, tolerant: bool = False) -> list[dict[str, Any]]:
    """Read a jsonl file. With ``tolerant=True``, skip (and log) malformed lines instead of raising —

    used for Gym's ``*_failures.jsonl`` sidecar, which is written during abnormal termination and can
    end in a truncated line; a corrupt failure record must not sink the successfully-collected trials.
    """
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError:
                if not tolerant:
                    raise
                logger.warning("Skipping malformed JSON at %s:%d", path, line_no)
    return rows


class GymRuntimeConfig(BaseModel):
    """Declarative config for running an existing Gym environment via the ``gym`` CLI.

    Holds only plain fields; the two-step invocation is built from them at run
    time. The dataset itself is recovered from the tasks (stamped by
    :func:`discover_gym_tasks`), mirroring the Harbor runner.
    """

    model_config = ConfigDict(extra="forbid")

    gym_root: Path = Field(
        description="NeMo Gym checkout directory; the CLI resolves envs/agents/models from here and "
        "reads credentials from its gitignored env.yaml.",
    )
    gym_bin: Path | None = Field(
        default=None, description="Path to the `gym` executable; defaults to <gym_root>/.venv/bin/gym."
    )
    agent: str = Field(description="Agent name to collect rollouts with, e.g. 'simple_agent'.")
    agent_config: str = Field(description="Repo-relative agent config passed to `gym env start` (--config).")
    resources_server: str = Field(description="Resources-server (environment) name, e.g. 'mcqa' (--resources-server).")
    model_type: str = Field(
        default="inference_provider",
        description="Model-type config (--model-type). `inference_provider` speaks OpenAI-compatible chat; "
        "`openai_model` uses the OpenAI Responses API (500s against chat-only endpoints).",
    )
    bind_resources_server: bool = Field(
        default=True,
        description="Auto-bind the agent's `resources_server.name` to `resources_server` via a Hydra override "
        "(the composable/Pattern-A agent case, e.g. simple_agent whose config leaves it '???'). Set False for "
        "self-contained agents that already bind their own resources-server.",
    )
    env_overrides: list[str] = Field(
        default_factory=list,
        description="Extra Hydra '+key=value' overrides for `gym env start` (escape hatch; applied after the "
        "auto-derived resources-server binding).",
    )
    num_repeats: int = Field(default=1, ge=1, description="Attempts per row; each attempt becomes one trial.")
    concurrency: int = Field(
        default=4,
        ge=1,
        description="Concurrent rollouts for `gym eval run` (the collection-phase knob, tuned to the model "
        "endpoint's limits). Distinct from AgentEvalRunConfig.parallelism, which bounds concurrent scoring.",
    )
    startup_timeout_s: float = Field(default=240.0, gt=0, description="Max wait for `gym env start` readiness.")
    collection_timeout_s: float | None = Field(
        default=None,
        gt=0,
        description="Max wait for `gym eval run` collection; None = unbounded (scales with dataset x num_repeats x "
        "model latency, so no safe fixed default). Set it to bound a hung/slow model endpoint.",
    )
    shutdown_grace_s: float = Field(
        default=30.0,
        gt=0,
        description="Grace period for a Gym subprocess *group* to exit on SIGTERM (letting Ray shut down cleanly) "
        "before escalating to SIGKILL.",
    )
    reward_key: str = Field(default=DEFAULT_REWARD_KEY, description="Key read from each rollout record.")

    def gym_executable(self) -> Path:
        return self.gym_bin if self.gym_bin is not None else self.gym_root / ".venv" / "bin" / "gym"


class GymRewardMetric:
    """Score the Gym verifier reward stamped onto trial metadata.

    The Gym analogue of :class:`HarborRewardMetric`: reads the per-trial ``reward``
    off the candidate metadata (populated by :class:`GymAgentTaskRunner`); a trial
    with no reward is left **unscored** (``None`` → ``nan``), excluded from the mean
    and surfaced as ``nan_count`` rather than counted as a spurious ``0.0``. Gym owns
    the scoring — this metric only surfaces it (Evaluator does not re-derive the reward).
    """

    def __init__(self, *, output_name: str = "reward", metric_type: str = "gym_reward") -> None:
        self._output_name = output_name
        self._metric_type = metric_type

    @property
    def type(self) -> str:
        return self._metric_type

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score(self._output_name)]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        reward = input.candidate.metadata.get("reward")
        value = float(reward) if reward is not None else None
        return MetricResult(outputs=[MetricOutput(name=self._output_name, value=value)])


def discover_gym_tasks(dataset: str | Path, *, metrics: Sequence[Any] | None = None) -> list[AgentEvalTask]:
    """Build one :class:`AgentEvalTask` per distinct row in a Gym dataset (jsonl).

    Each task's id is the content hash of the row; its ``instruction`` is rendered
    from ``responses_create_params.input``; the raw params are stashed under
    ``inputs['gym_row']`` for provenance; and it is scored by a
    :class:`GymRewardMetric`. The dataset path is stamped on
    ``metadata['gym_dataset_path']``, and every *other* row key (the verifier's
    ground-truth fields, ``agent_ref``, and so on) on ``metadata['gym_row_extras']``.
    Together with ``inputs['gym_row']`` those reconstruct the complete source row,
    which :class:`GymAgentTaskRunner` re-materializes into the dataset it hands to Gym.
    They are kept disjoint deliberately: the task record is persisted to the run
    bundle's ``tasks.jsonl``, and ``responses_create_params`` is usually the bulk of a
    row, so storing it in both places would write every dataset twice per run.

    **One distinct row is one task.** Duplicate rows collapse (identity is row content,
    so they are by definition the same task) and are reported as a warning: repeated
    attempts are a run-level concern — ``GymRuntimeConfig.num_repeats`` — not something
    a dataset expresses by repeating a row, so duplicates almost always mean bad data.
    """
    dataset = Path(dataset)
    tasks: list[AgentEvalTask] = []
    seen: set[str] = set()
    duplicates = 0
    for row in _read_jsonl(dataset):
        task_id = _canonical_row_hash(row)
        if task_id in seen:
            duplicates += 1
            continue
        seen.add(task_id)
        tasks.append(
            AgentEvalTask(
                id=task_id,
                intent=f"Gym row from {dataset.name}",
                inputs={
                    "instruction": _render_instruction(row.get("responses_create_params")),
                    "gym_row": row.get("responses_create_params"),
                },
                metrics=list(metrics) if metrics is not None else [GymRewardMetric()],
                metadata={
                    "gym_dataset_path": str(dataset),
                    # Everything except responses_create_params, which already lives in inputs['gym_row'].
                    "gym_row_extras": {
                        key: value
                        for key, value in row.items()
                        if key != "responses_create_params" and key not in _RUNTIME_KEYS
                    },
                },
            )
        )
    if duplicates:
        logger.warning(
            "Collapsed %d duplicate row(s) in %s into %d distinct task(s): task identity is row content, so "
            "repeating a row cannot request repeated attempts — set GymRuntimeConfig.num_repeats for that. "
            "Duplicate rows usually indicate a data problem.",
            duplicates,
            dataset,
            len(tasks),
        )
    if not tasks:
        raise ValueError(f"no rows found in Gym dataset {dataset}")
    return tasks


class GymAgentTaskRunner:
    """An :class:`AgentTaskRunner` that runs an existing Gym env, then adapts its rollouts.

    :meth:`run_tasks` materializes the requested tasks into a normalized dataset with
    ``_ng_task_index`` stamped per row, runs the two-step Gym flow (``env start`` +
    ``eval run --no-serve --input``) against it via subprocess, and fans the rollout
    records out into one trial per ``_ng_rollout_index``. Because we assign the index,
    attribution is a dict lookup rather than a positional guess, and Gym only rolls out
    the tasks we asked for. The durable task **identity** stays our content hash.
    """

    def __init__(self, *, config: GymRuntimeConfig) -> None:
        self._config = config

    def runner_info(self) -> RunnerInfo:
        """Identify this runner and the Gym settings that shape its results.

        Credentials normally live in the Gym checkout's gitignored ``env.yaml`` and never reach this
        object — but ``env_overrides`` is a free-form escape hatch, so its values are redacted by key
        (see :func:`_redact_env_overrides`) rather than trusted.
        """
        cfg = self._config
        return RunnerInfo(
            name="gym",
            kind="runner",
            config={
                "resources_server": cfg.resources_server,
                "agent": cfg.agent,
                "agent_config": cfg.agent_config,
                "model_type": cfg.model_type,
                "num_repeats": cfg.num_repeats,
                "concurrency": cfg.concurrency,
                "bind_resources_server": cfg.bind_resources_server,
                "env_overrides": _redact_env_overrides(cfg.env_overrides),
                "reward_key": cfg.reward_key,
            },
        )

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalTrial]:
        cfg = self._config
        # Provenance for the log line only — the file Gym actually reads is the normalized one we
        # materialize below from the tasks themselves.
        source_dataset = _source_datasets(tasks)

        # config.parallelism still governs how the evaluator *scores* the trials we return (its scoring
        # semaphore). It is deliberately not mapped onto Gym's rollout `--concurrency`: those are different
        # phases — parallelism bounds concurrent scoring (SDK-side, cheap), while Gym's `--concurrency`
        # bounds concurrent rollouts against the model endpoint during collection (tuned to that endpoint's
        # limits via GymRuntimeConfig.concurrency).
        if config is not None and config.output_dir is not None:
            work_dir = Path(config.output_dir) / "gym_run"
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="gym_run_"))
        work_dir.mkdir(parents=True, exist_ok=True)

        rollouts_path = work_dir / "rollouts.jsonl"
        _ensure_fresh_output(rollouts_path)

        # Hand Gym a dataset we control: one row per requested task, each carrying the _ng_task_index
        # we assign. Gym honors a pre-stamped index, so the rollout->task join becomes a total map
        # instead of a positional guess about Gym's raw-line dedup (see the module docstring).
        input_path = work_dir / "gym_input.jsonl"
        index_to_task_id = _materialize_dataset(tasks, input_path)
        logger.info(
            "Materialized %d task(s) from %s into %s for Gym collection.",
            len(index_to_task_id),
            source_dataset,
            input_path,
        )

        await self._run_two_step(input_path, rollouts_path, work_dir)
        trials = _trials_from_rollouts(rollouts_path, tasks, index_to_task_id, reward_key=cfg.reward_key)
        _require_full_coverage(tasks, covered_task_ids={trial.task_id for trial in trials}, rollouts_path=rollouts_path)
        return trials

    async def _run_two_step(self, input_path: Path, output_path: Path, work_dir: Path) -> None:
        """Start the Gym servers, collect against them with ``--no-serve``, then tear them down."""
        cfg = self._config
        gym = str(cfg.gym_executable())
        env_log = work_dir / "gym_env.log"

        # Gym launches each server from its own subdir with its own .venv. Ray (>=2.56) otherwise
        # detects a `uv run` ancestor and tries to replicate that uv project onto its workers,
        # asserting the project pyproject.toml lives in the driver's cwd — which aborts startup. That
        # hook is wrong for Gym (servers manage their own deps), so disable it for the subprocesses.
        subprocess_env = {**os.environ, "RAY_ENABLE_UV_RUN_RUNTIME_ENV": "0"}

        env_cmd = [
            gym,
            "env",
            "start",
            "--config",
            cfg.agent_config,
            "--model-type",
            cfg.model_type,
            "--resources-server",
            cfg.resources_server,
        ]
        if cfg.bind_resources_server:
            # Composable (Pattern-A) agents leave resources_server.name unbound ('???'); bind it to the
            # env we're running. Assumes the agent config's top-level key equals the agent name (the
            # simple_agent convention). Self-contained agents set bind_resources_server=False.
            env_cmd.append(
                f"+{cfg.agent}.responses_api_agents.{cfg.agent}.resources_server.name={cfg.resources_server}"
            )
        env_cmd.extend(cfg.env_overrides)
        # start_new_session=True puts `gym env start` in its own process group so teardown can signal
        # the *whole* Ray-cluster + uvicorn tree, not just the direct child (else they orphan).
        # stderr is merged into stdout here (unlike `eval run`, which splits them) because readiness
        # detection scans a single chronological transcript and Gym's readiness line is not guaranteed
        # to land on a particular stream.
        env_proc = await asyncio.create_subprocess_exec(
            *env_cmd,
            cwd=str(cfg.gym_root),
            env=subprocess_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        env_pump = asyncio.create_task(_pump_stream(env_proc.stdout, env_log, label="gym env start"))
        try:
            await self._wait_for_servers(env_log, env_proc)
            await self._collect_rollouts(gym, input_path, output_path, work_dir, subprocess_env)
        finally:
            await _terminate(env_proc, grace_s=cfg.shutdown_grace_s)
            # Bounded: a leaked grandchild holding the inherited pipe must not wedge teardown.
            await _drain_pumps([env_pump], grace_s=cfg.shutdown_grace_s, what="gym env start")

    async def _collect_rollouts(
        self, gym: str, input_path: Path, output_path: Path, work_dir: Path, subprocess_env: dict[str, str]
    ) -> None:
        """Run ``gym eval run --no-serve`` against the live servers, bounded and self-cleaning.

        Spawned in its own process group and always torn down (even on timeout/cancellation), so a hung
        collection can't wedge the run or leak Ray workers.

        Output is *streamed* to ``gym_eval.stdout.log`` / ``gym_eval.stderr.log`` in ``work_dir`` rather
        than buffered in memory (a long collection's transcript can be large), and mirrored to this
        module's logger at ``DEBUG`` so callers can surface it in their own terminal through ordinary
        ``logging`` configuration. Failures point at both files and inline the last few lines.
        """
        cfg = self._config
        eval_cmd = [
            gym,
            "eval",
            "run",
            "--no-serve",
            "--agent",
            cfg.agent,
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--num-repeats",
            str(cfg.num_repeats),
            "--concurrency",
            str(cfg.concurrency),
        ]
        stdout_log = work_dir / "gym_eval.stdout.log"
        stderr_log = work_dir / "gym_eval.stderr.log"
        eval_proc = await asyncio.create_subprocess_exec(
            *eval_cmd,
            cwd=str(cfg.gym_root),
            env=subprocess_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        tails: dict[str, deque[str]] = {}
        pumps = [
            asyncio.create_task(
                _pump_stream(eval_proc.stdout, stdout_log, label="gym eval", tails=tails, key="stdout")
            ),
            asyncio.create_task(
                _pump_stream(eval_proc.stderr, stderr_log, label="gym eval", tails=tails, key="stderr")
            ),
        ]
        try:
            await asyncio.wait_for(eval_proc.wait(), timeout=cfg.collection_timeout_s)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"`gym eval run` exceeded collection_timeout_s={cfg.collection_timeout_s}s; collection aborted. "
                f"See {stdout_log} and {stderr_log}."
            ) from exc
        finally:
            # Terminate first so the pipes close, then drain (bounded) to flush whatever was buffered.
            await _terminate(eval_proc, grace_s=cfg.shutdown_grace_s)
            await _drain_pumps(pumps, grace_s=cfg.shutdown_grace_s, what="gym eval run")
        if eval_proc.returncode != 0:
            tail = "\n".join(tails.get("stderr") or tails.get("stdout") or [])
            raise RuntimeError(
                f"`gym eval run` failed (rc={eval_proc.returncode}). Full output: {stdout_log} and {stderr_log}\n"
                f"--- last {_LOG_TAIL_LINES} line(s) ---\n{tail}"
            )

    async def _wait_for_servers(self, env_log: Path, env_proc: asyncio.subprocess.Process) -> None:
        """Wait until ``gym env start`` reports every composed server ready.

        Keys off Gym's own readiness line (``All N / N servers ready!``), which it prints only after
        HTTP-health-checking each server it composed. So the caller never has to know or guess the
        server count — Gym derives it from the config and health-checks for us.
        """
        cfg = self._config
        loop = asyncio.get_running_loop()
        ready = re.compile(r"All \d+ / \d+ servers ready")
        deadline = loop.time() + cfg.startup_timeout_s
        while loop.time() < deadline:
            if env_proc.returncode is not None:
                raise RuntimeError(f"`gym env start` exited early (rc={env_proc.returncode}); see {env_log}")
            text = env_log.read_text(encoding="utf-8", errors="replace") if env_log.exists() else ""
            if "required uv version" in text.lower():
                raise RuntimeError(f"`gym env start` hit the uv required-version gate; see {env_log}")
            if ready.search(text):
                return
            await asyncio.sleep(2)
        raise TimeoutError(f"Gym servers not ready within {cfg.startup_timeout_s}s; see {env_log}")


def _source_datasets(tasks: Sequence[AgentEvalTask]) -> str:
    """Human-readable summary of the dataset(s) the tasks were discovered from, for a log line.

    Purely provenance. Gym reads the dataset :func:`_materialize_dataset` writes from the tasks
    themselves, so nothing here gates the run: tasks drawn from two datasets are legitimate (the
    materialized file is their union), and a task with no stamped path runs fine. Never raises —
    a missing or inconsistent label is not a reason to fail an otherwise valid evaluation.
    """
    stamped = {
        task.metadata["gym_dataset_path"]
        for task in tasks
        if isinstance(task.metadata.get("gym_dataset_path"), str) and task.metadata["gym_dataset_path"]
    }
    return ", ".join(sorted(stamped)) if stamped else "<tasks with no stamped dataset path>"


async def _pump_stream(
    stream: asyncio.StreamReader | None,
    path: Path,
    *,
    label: str,
    tails: dict[str, deque[str]] | None = None,
    key: str = "stdout",
) -> None:
    """Stream a subprocess pipe to ``path`` while mirroring it to the module logger at ``DEBUG``.

    Reads in chunks rather than by line so a pathologically long line can't overrun asyncio's stream
    limit, and retains only the last :data:`_LOG_TAIL_LINES` lines in memory (via ``tails[key]``) for
    inclusion in a failure message — the file on disk is the complete record.
    """
    tail: deque[str] = deque(maxlen=_LOG_TAIL_LINES)
    if tails is not None:
        tails[key] = tail
    if stream is None:
        return

    def emit(raw: bytes) -> None:
        text = raw.decode("utf-8", errors="replace").rstrip("\r")
        logger.debug("[%s %s] %s", label, key, text)
        tail.append(text)

    with path.open("wb") as handle:
        buffer = b""
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                break
            handle.write(chunk)
            handle.flush()
            buffer += chunk
            *complete, buffer = buffer.split(b"\n")
            for line in complete:
                emit(line)
        if buffer:
            emit(buffer)


async def _drain_pumps(pumps: Sequence[asyncio.Task[None]], *, grace_s: float, what: str) -> None:
    """Await log pumps after teardown, but never block on them indefinitely.

    A pump ends at pipe EOF, which requires *every* inheritor of the write end to close it. Gym's
    descendants inherit it, and Ray daemonizes ``gcs_server`` into its own session where our
    process-group signals can't reach it (see :func:`_terminate`) — so a leaked grandchild can hold
    the pipe open forever. Waiting unconditionally would hang the whole run inside a ``finally``.

    Bounded instead: give the pumps ``grace_s`` to flush, then cancel and move on. Everything read
    before the stall is already written and flushed to the log file, so cancelling costs at most the
    tail of a transcript belonging to a process we just killed — and it is reported, not silent.
    """
    if not pumps:
        return
    _done, pending = await asyncio.wait(pumps, timeout=grace_s)
    if not pending:
        return
    logger.warning(
        "%d `%s` log pump(s) did not finish within %.1fs; the pipe is still held open (likely a Gym "
        "grandchild that outlived teardown, e.g. Ray's detached gcs_server). Abandoning them — the log "
        "file holds everything read up to this point, but its tail may be truncated.",
        len(pending),
        what,
        grace_s,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def _materialize_dataset(tasks: Sequence[AgentEvalTask], dest: Path) -> dict[int, str]:
    """Write the normalized dataset Gym will read, and return its ``_ng_task_index`` → task-id map.

    One line per requested task, in task order, carrying the task's full source row plus an explicitly
    stamped ``_ng_task_index``. Gym honors a pre-supplied index instead of deriving one, so this makes
    the rollout→task join total and order-independent, and confines the run to the tasks we asked for.

    The row is reassembled from ``inputs['gym_row']`` (``responses_create_params``) and
    ``metadata['gym_row_extras']`` (everything else), which :func:`discover_gym_tasks` keeps disjoint
    so the run bundle doesn't store the same payload twice. Any pre-existing ``_ng_*`` fields are
    stripped: ours is authoritative, and Gym assigns ``_ng_rollout_index`` itself per attempt.
    """
    index_to_task_id: dict[int, str] = {}
    seen_task_ids: set[str] = set()
    lines: list[str] = []
    for index, task in enumerate(tasks):
        # The source row is stored split across inputs/metadata so the run bundle doesn't persist
        # responses_create_params twice; reassemble it here.
        extras = task.metadata.get("gym_row_extras")
        params = task.inputs.get("gym_row")
        if not isinstance(extras, Mapping) or not isinstance(params, Mapping):
            raise ValueError(
                f"task {task.id!r} is missing inputs['gym_row'] and/or metadata['gym_row_extras']; build tasks "
                "with discover_gym_tasks so the Gym dataset can be re-materialized for the run"
            )
        if task.id in seen_task_ids:
            raise ValueError(
                f"task {task.id!r} was supplied more than once; one distinct row is one task, and repeated "
                "attempts come from GymRuntimeConfig.num_repeats"
            )
        seen_task_ids.add(task.id)
        payload = {key: value for key, value in extras.items() if key not in _RUNTIME_KEYS}
        payload["responses_create_params"] = params
        payload[NG_TASK_INDEX] = index
        lines.append(json.dumps(payload, default=str))
        index_to_task_id[index] = task.id
    if not index_to_task_id:
        raise ValueError("GymAgentTaskRunner was given no tasks to run")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index_to_task_id


def _require_full_coverage(tasks: Sequence[AgentEvalTask], *, covered_task_ids: set[str], rollouts_path: Path) -> None:
    """Fail the run when Gym produced no trial at all for some requested task.

    :class:`AgentEvaluator` already refuses to score a task with no trial
    (``evaluator._score_trials``), and deliberately so: an incomplete run must not read as a
    successful one with quieter counts. We keep that contract rather than papering over it with
    synthesized FAILED trials — an unscored trial is excluded from the mean, so fabricating them
    would report a plausible-looking average over an unannounced subset of the dataset. A rollout
    that failed in a *diagnosable* way already becomes a FAILED trial via the failures sidecar;
    reaching here means the attempt is unaccounted for entirely.

    What this adds over letting the evaluator raise is diagnosis: by the time the run fails the full
    collection cost is already paid, so the error names the evidence instead of just the task ids.
    """
    missing = sorted({task.id for task in tasks} - covered_task_ids)
    if not missing:
        return
    raise RuntimeError(
        f"Gym produced no rollout for {len(missing)} of {len(tasks)} requested task(s), so the run is "
        f"incomplete and will not be scored (a partial run must not be reported as a whole one).\n"
        f"  rollouts:  {rollouts_path}\n"
        f"  failures:  {_failures_path_for(rollouts_path)}\n"
        f"  gym logs:  {rollouts_path.parent} (gym_env.log, gym_eval.stdout.log, gym_eval.stderr.log)\n"
        f"  unrepresented task id(s): {missing}"
    )


def _failures_path_for(rollouts_path: Path) -> Path:
    """Sidecar Gym writes failed rollouts to (mirrors Gym's own ``_failures_path_for``)."""
    return rollouts_path.with_name(rollouts_path.stem + "_failures.jsonl")


def _ensure_fresh_output(rollouts_path: Path) -> None:
    """Enforce one Gym run per output dir (the AgentEvaluator convention).

    Gym appends to the failures sidecar (``open("ab")``) and doesn't clear it between runs, so reusing
    a populated directory would silently mix this run's failures with a prior run's. Rather than clear
    (which would clobber an earlier run's results — infra failures are useful signal), refuse to run
    into a directory that already holds Gym rollout output.
    """
    preexisting = [path for path in (rollouts_path, _failures_path_for(rollouts_path)) if path.exists()]
    if preexisting:
        names = ", ".join(path.name for path in preexisting)
        raise FileExistsError(
            f"{rollouts_path.parent} already holds Gym rollout output ({names}); give each run a fresh "
            "output_dir (the AgentEvaluator convention). Gym appends to the failures sidecar, so reusing a "
            "directory would mix runs and could obscure a prior run's results."
        )


def _coerce_reward(value: Any) -> float | None:
    """Best-effort ``float`` for a reward; returns None (never raises) on a missing/malformed value."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("Gym rollout carried a non-numeric reward %r; recording the trial as unscored.", value)
        return None


def _resolve_task_id(
    record: Mapping[str, Any], index_to_task_id: Mapping[int, str], *, strict: bool = True
) -> str | None:
    """Map a rollout record to a task id via the ``_ng_task_index`` we stamped in the input dataset.

    Returns None when the record carries no usable index (kill-shaped failures can lack one).

    An index we never stamped is handled by ``strict``. In the **successes** file (``strict=True``)
    it is fatal: every row Gym read came from :func:`_materialize_dataset`, so an unknown index means
    Gym reindexed the dataset rather than honoring our stamp, and every reward attribution is
    therefore suspect. In the **failures sidecar** (``strict=False``) it is merely unattributable and
    is counted instead — that file is written during abnormal termination and read tolerantly by
    design, so one odd record must not discard the successes already parsed. That relaxation cannot
    inflate a result: failure records carry no reward, and a task left with no trial still trips
    :func:`_require_full_coverage`.
    """
    index = record.get(NG_TASK_INDEX)
    if not isinstance(index, int) or isinstance(index, bool):
        return None
    task_id = index_to_task_id.get(index)
    if task_id is None:
        if not strict:
            logger.warning(
                "Gym failure record carried %s=%s, which was not stamped on the materialized dataset; "
                "counting it as unattributable rather than failing the run.",
                NG_TASK_INDEX,
                index,
            )
            return None
        raise ValueError(
            f"Gym emitted {NG_TASK_INDEX}={index}, which is not one of the {len(index_to_task_id)} index value(s) "
            f"stamped on the materialized dataset. Gym appears to have reassigned {NG_TASK_INDEX} instead "
            "of honoring the supplied one, so rollout-to-task attribution is unsafe."
        )
    return task_id


def _rollout_trial_id(task_id: str, raw_rollout_index: Any, synth_seq: dict[str, int], *, missing_label: str) -> str:
    """Per-attempt trial id: use the record's ``_ng_rollout_index`` when it's a real int, else a
    per-task-unique ``{missing_label}{n}`` suffix so records lacking an index don't collide on one id."""
    if isinstance(raw_rollout_index, int) and not isinstance(raw_rollout_index, bool):
        return f"{task_id}:{raw_rollout_index}"
    seq = synth_seq[task_id] = synth_seq.get(task_id, 0) + 1
    return f"{task_id}:{missing_label}{seq}"


def _trials_from_rollouts(
    rollouts_path: Path,
    tasks: Sequence[AgentEvalTask],
    index_to_task_id: Mapping[int, str],
    *,
    reward_key: str = DEFAULT_REWARD_KEY,
) -> list[AgentEvalTrial]:
    """Fan Gym's rollout records out into one :class:`AgentEvalTrial` per attempt.

    Reads *both* Gym output files: successes from ``rollouts.jsonl`` (COMPLETED, carrying the reward)
    and failures from the ``*_failures.jsonl`` sidecar (FAILED — so a failed attempt is counted and
    diagnosed rather than silently dropped). Every record is attributed to its task by
    ``_ng_task_index`` → ``index_to_task_id``, the map we stamped in :func:`_materialize_dataset`.
    """
    known_task_ids = {task.id for task in tasks}
    # Defence in depth: the index map and the task list must describe the same run. Gym is an external
    # project on its own release cadence, and people make agent-optimization decisions from these
    # numbers — so any disagreement about *which task a result belongs to* is a hard error, never a
    # best-effort join. Cheap to check once; impossible to notice downstream if it silently drifts.
    mapped_task_ids = set(index_to_task_id.values())
    if mapped_task_ids != known_task_ids:
        raise ValueError(
            f"the {NG_TASK_INDEX} map does not match the task list it will be joined against "
            f"({len(mapped_task_ids - known_task_ids)} mapped task(s) absent from the list, "
            f"{len(known_task_ids - mapped_task_ids)} listed task(s) absent from the map); "
            "attributing rollouts across a mismatch would report results against the wrong tasks"
        )
    trials: list[AgentEvalTrial] = []
    # Shared per-task counter for records lacking a usable _ng_rollout_index (success + failure); a
    # missing/null index must not collapse multiple attempts for one task onto the same trial id.
    synth_seq: dict[str, int] = {}

    success_evidence = CandidateEvidence(
        descriptors={"rollouts": EvidenceDescriptor(kind="filesystem", format="file", ref=str(rollouts_path))}
    )
    unattributed_successes = 0
    for record in _read_jsonl(rollouts_path):
        task_id = _resolve_task_id(record, index_to_task_id)
        if task_id is None:
            # No usable index (an unknown one raises). Skipping is right, but silence is not: with
            # num_repeats > 1 the task keeps its other trials, so _require_full_coverage won't fire and
            # the task would simply be scored on fewer attempts than were actually run.
            unattributed_successes += 1
            continue
        raw_rollout_index = record.get(NG_ROLLOUT_INDEX)
        reward = _coerce_reward(record.get(reward_key))
        trials.append(
            AgentEvalTrial(
                id=_rollout_trial_id(task_id, raw_rollout_index, synth_seq, missing_label="noidx"),
                task_id=task_id,
                status=AgentEvalTrialStatus.COMPLETED if reward is not None else AgentEvalTrialStatus.PARTIAL,
                output=AgentOutput(response=record.get("response"), metadata={"agent_ref": record.get("agent_ref")}),
                evidence=success_evidence,
                metadata={
                    "reward": reward,
                    NG_TASK_INDEX: record.get(NG_TASK_INDEX),
                    NG_ROLLOUT_INDEX: raw_rollout_index,
                },
            )
        )

    failures_path = _failures_path_for(rollouts_path)
    unattributed_failures = 0
    if failures_path.exists():
        failure_evidence = CandidateEvidence(
            descriptors={
                "rollout_failures": EvidenceDescriptor(kind="filesystem", format="file", ref=str(failures_path))
            }
        )
        # tolerant: a truncated line in the abnormal-termination sidecar must not sink the good trials.
        for record in _read_jsonl(failures_path, tolerant=True):
            # strict=False to match this loop's tolerant read: an odd record is counted, not fatal.
            task_id = _resolve_task_id(record, index_to_task_id, strict=False)
            if task_id is None:
                # kill-shaped failures (SIGTERM/OOM/actor-death) can lack a usable index — count, don't drop.
                unattributed_failures += 1
                continue
            raw_rollout_index = record.get(NG_ROLLOUT_INDEX)
            trials.append(
                AgentEvalTrial(
                    id=_rollout_trial_id(task_id, raw_rollout_index, synth_seq, missing_label="fail"),
                    task_id=task_id,
                    status=AgentEvalTrialStatus.FAILED,
                    output=AgentOutput(
                        response=record.get("response"), metadata={"agent_ref": record.get("agent_ref")}
                    ),
                    evidence=failure_evidence,
                    metadata={
                        "reward": None,
                        # best-effort: Gym's failure-record schema isn't contractual, so probe common keys.
                        "gym_failure": record.get("error") or record.get("exception") or record.get("failure_reason"),
                        NG_TASK_INDEX: record.get(NG_TASK_INDEX),
                        NG_ROLLOUT_INDEX: raw_rollout_index,
                    },
                )
            )
    if unattributed_successes:
        logger.warning(
            "%d Gym rollout record(s) in %s carried no usable %s and could not be attributed to a task; "
            "affected tasks are scored on fewer attempts than were collected.",
            unattributed_successes,
            rollouts_path,
            NG_TASK_INDEX,
        )
    if unattributed_failures:
        logger.warning(
            "%d Gym failure record(s) lacked a usable %s and could not be attributed to a task.",
            unattributed_failures,
            NG_TASK_INDEX,
        )

    # Reported here, enforced by _require_full_coverage in run_tasks (which knows the run's log paths).
    missing = known_task_ids - {trial.task_id for trial in trials}
    if missing:
        logger.warning("No Gym rollout produced a trial for %d requested task(s): %s", len(missing), sorted(missing))
    return trials


def _signal_group(pgid: int, sig: int) -> None:
    """Send ``sig`` to a process group, tolerating an already-dead group."""
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


async def _terminate(proc: asyncio.subprocess.Process, *, grace_s: float = 30.0) -> None:
    """Tear down a backgrounded Gym subprocess *and its whole process group*.

    ``gym env start`` fans out into a Ray cluster + uvicorn servers, and Gym stops them from a
    ``KeyboardInterrupt`` handler (``finally: self.shutdown()``) — so we send **SIGINT** (not SIGTERM,
    which would bypass that handler and orphan Ray's detached ``gcs_server``). The child is spawned with
    ``start_new_session=True`` and leads its own group, so SIGINT to the group mimics Ctrl-C exactly;
    SIGKILL to the group is the escalation if Gym's graceful shutdown overstays ``grace_s``.

    Known limitation: Ray daemonizes ``gcs_server`` into its *own* session, outside this group, so the
    escalation SIGKILL cannot reach it — clean Ray teardown depends on Gym's SIGINT ``shutdown()``
    completing within ``grace_s``. POSIX-only (``killpg`` / ``getpgid`` / ``start_new_session`` / SIGINT).
    """
    if proc.returncode is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    _signal_group(pgid, signal.SIGINT)
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_s)
    except asyncio.TimeoutError:
        _signal_group(pgid, signal.SIGKILL)
        await proc.wait()


__all__ = [
    "DEFAULT_REWARD_KEY",
    "GymAgentTaskRunner",
    "GymRewardMetric",
    "GymRuntimeConfig",
    "discover_gym_tasks",
]
