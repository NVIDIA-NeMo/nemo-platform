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
without triggering Gym's split-driven data-prep), preceded by a pre-flight:
``gym env validate`` merges the composed config and reports unset ``???`` values,
bad paths, and dangling cross-references without starting anything; then ``gym env
start`` brings up the resources-server + agent + model servers, and ``gym eval run
--no-serve --input <materialized dataset>`` collects rollouts against them. Both
commands receive the identical selection arguments, so what is validated is what
runs. The runtime shells out to the ``gym`` CLI on PATH, so this SDK never imports
``nemo_gym``. Subprocess
output is streamed to log files under the run's work dir *and* mirrored to this
module's logger at ``DEBUG``, so callers choose terminal visibility through
ordinary ``logging`` configuration.

**Where Gym finds things.** NeMo Gym must be installed and its ``gym`` on PATH,
along with the target environment's own dependencies. Generally that means a
*separate* environment: Gym imports Ray at module load, and nemo-platform
excludes Ray by constraint over an unfixed CVE, so the two cannot share one. In a
job image the image owns PATH and this is unremarkable. There is deliberately no
config field naming a checkout, a venv, or a search root — these runner configs
become serialized job specs, and a local filesystem path means nothing on the
other side of that boundary. Environments themselves ship in the ``nemo-gym``
wheel (``resources_servers`` and friends install beside ``nemo_gym``, configs and
example data included), so no checkout is needed to reach them.

The subprocesses inherit this process's working directory, which is where Gym
looks for the gitignored ``env.yaml`` holding the collector's credentials before
falling back to its install root — so credentials never pass through this SDK.
Run from the directory holding that file; a Gym checkout there also has its
components take precedence, which is how you reach an environment the wheel does
not carry.

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
import math
import os
import re
import shutil
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
from nemo_platform.beta.evaluator.values.results import AggregateRangeScore, AggregateScalarScore, AggregateScore
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

#: Reward key read from each Gym rollout record.
DEFAULT_REWARD_KEY = "reward"
#: Gym's CLI, expected on PATH. Not configurable: these runner configs become serialized job specs,
#: and a path into somebody's venv is meaningless on the other side of that boundary. Note this name
#: is only ever *resolved*, never executed: :func:`_gym_executable` turns it into an absolute path
#: once, and that path is what the subprocesses run — so a child whose PATH differs from ours cannot
#: end up executing a different Gym.
_GYM_CLI = "gym"
#: Bound on `gym env validate`. It merges config without starting anything and returns in about a
#: second; this only exists so a wedged invocation cannot stall the run before it begins.
_VALIDATE_TIMEOUT_S = 120.0
#: Where Gym's Hydra run directories are redirected, relative to the run's work dir.
_HYDRA_SUBDIR = "gym_hydra"
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


#: Substrings that mark an override as carrying a credential. Matched case-insensitively against the
#: full dotted path, so nesting cannot hide one behind an innocuous leaf name.
_SECRET_KEY_MARKERS = ("api_key", "apikey", "token", "secret", "password", "passwd", "credential")
#: Stand-in written in place of a redacted override value.
_REDACTED = "<redacted>"


def _hydra_scalar(value: Any) -> str:
    """Render a leaf value the way Hydra's override grammar reads it back.

    ``None`` and booleans have dedicated spellings — ``str(None)`` would set the literal string
    ``"None"``, and ``str(True)`` the string ``"True"``. Sequences use Hydra's bracket form. Anything
    else is stringified, which leaves interpolations like ``${policy_base_url}`` intact for OmegaConf
    to resolve later.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_hydra_scalar(item) for item in value) + "]"
    return str(value)


def _flatten_overrides(overrides: Mapping[str, Any], _prefix: str = "") -> list[str]:
    """Flatten a nested override mapping into Hydra ``++dotted.path=value`` arguments.

    Callers describe overrides as structured data — ``{"a": {"b": 1}}`` — rather than as
    pre-serialized Hydra strings, so the config survives being sent somewhere as JSON. Hydra itself
    only speaks the flat form, so the translation happens here, at the point of invocation.

    ``++`` rather than ``+``: it sets a key whether or not it already exists, which is what an
    override means. A bare ``+`` fails on a key the merged config already defines.
    """
    arguments: list[str] = []
    for key, value in overrides.items():
        path = f"{_prefix}{key}"
        if isinstance(value, Mapping):
            arguments.extend(_flatten_overrides(value, f"{path}."))
        else:
            arguments.append(f"++{path}={_hydra_scalar(value)}")
    return arguments


def _redact_env_overrides(overrides: Mapping[str, Any], _prefix: str = "") -> dict[str, Any]:
    """Redact credential-looking values from overrides before they are recorded as provenance.

    ``env_overrides`` is a free-form escape hatch forwarded to Gym, so nothing stops a caller passing
    ``{"model": {"api_key": "sk-..."}}``. ``RunnerInfo.config`` is persisted into the run bundle, so a
    value that looks like a credential must not be written there.

    The *key* is always kept — knowing that a run overrode ``model.api_key`` is useful provenance;
    knowing the value is a leak. Matching is on the full dotted path, so a marker anywhere in it
    redacts, and nesting cannot hide a credential behind an innocuous leaf name.
    """
    redacted: dict[str, Any] = {}
    for key, value in overrides.items():
        path = f"{_prefix}{key}"
        if isinstance(value, Mapping):
            redacted[key] = _redact_env_overrides(value, f"{path}.")
        elif any(marker in path.casefold() for marker in _SECRET_KEY_MARKERS):
            redacted[key] = _REDACTED
        else:
            redacted[key] = value
    return redacted


def _selection_args(config: GymRuntimeConfig, work_dir: Path) -> list[str]:
    """The environment/agent/model selection passed to Gym.

    Built once and handed verbatim to both ``gym env validate`` and ``gym env start``, so what is
    validated is exactly what runs — a pre-flight against a different config would be worse than
    none.
    """
    selection = [
        "--config",
        config.agent_config,
        "--model-type",
        config.model_type,
        "--resources-server",
        config.resources_server,
    ]
    if config.bind_resources_server:
        # Composable (Pattern-A) agents leave resources_server.name unbound ('???'); bind it to the
        # env we're running. Assumes the agent config's top-level key equals the agent name (the
        # simple_agent convention) *and* that the resources-server is registered under the
        # environment's own name — not universally true, so self-contained or differently-named
        # servers set bind_resources_server=False and bind themselves via env_overrides.
        selection.append(
            f"+{config.agent}.responses_api_agents.{config.agent}.resources_server.name={config.resources_server}"
        )
    selection.extend(_flatten_overrides(config.env_overrides))
    # Gym is a Hydra app, so each invocation writes a timestamped run directory — by default
    # `outputs/<date>/<time>/` under the *current* directory. Since the subprocesses inherit this
    # process's cwd (so Gym can find env.yaml), the default would litter whatever directory the
    # caller happened to run from. Redirect it under the run's work dir, with the rest of the run's
    # artifacts. Applies to every Gym entry point, `gym list` included.
    selection.append(f"hydra.run.dir={work_dir / _HYDRA_SUBDIR}")
    return selection


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
    env_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Nested config overrides merged into Gym's config, applied after the auto-derived "
        "resources-server binding. Structured rather than pre-serialized Hydra strings so the config "
        "travels as JSON — `{'a': {'b': 1}}` becomes `++a.b=1` at invocation. This is the escape "
        "hatch for what Gym does not standardize: an environment whose resources-server is registered "
        "under a different name, or which references a model server no shipped config defines.",
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


def _gym_executable() -> str:
    """Locate the ``gym`` CLI on PATH, or fail saying what to do about it.

    Deliberately PATH-only, with no config field pointing at a checkout or a particular venv: these
    runner configs become serialized job specs, and a local filesystem path cannot cross that
    boundary. Resolving here rather than at spawn time turns a missing Gym into one legible error
    instead of an ``ENOENT`` out of ``create_subprocess_exec`` after the run has already started.

    Note that Gym generally cannot live in this SDK's own environment: it imports Ray at module load,
    and nemo-platform excludes Ray by constraint over an unfixed CVE. Install Gym separately and put
    its ``bin`` on PATH; in a job image, the image owns PATH and this resolves normally.
    """
    resolved = shutil.which(_GYM_CLI)
    if resolved is None:
        raise RuntimeError(
            f"The {_GYM_CLI!r} CLI was not found on PATH. Install NeMo Gym in its own environment "
            "(it needs Ray, which nemo-platform excludes over an unfixed CVE, so it cannot share this "
            "one) and put that environment's `bin` directory on PATH. Each resources-server also "
            "ships its own requirements.txt, installed from that server's directory."
        )
    return resolved


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
        self._run_aggregations: dict[str, Any] | None = None

    def run_aggregate_scores(self) -> Sequence[AggregateScore]:
        """Gym's ``agent_metrics`` mapped onto typed aggregate scores, namespaced ``runner.gym.<metric>``.

        Satisfies :class:`RunAggregationsProvider`. ``reward`` is skipped: the SDK already scores it
        natively as ``gym_reward.reward``, and two differently-derived numbers under one name invites
        exactly the confusion the namespace is there to prevent.
        """
        return _aggregate_scores_from_gym(self._run_aggregations)

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
        self._run_aggregations = None  # reset per run so a reused runner never leaks a prior run's numbers
        # Provenance for the log line only — the file Gym actually reads is the normalized one we
        # materialize below from the tasks themselves.
        source_dataset = _source_datasets(tasks)

        # config.parallelism still governs how the evaluator *scores* the trials we return (its scoring
        # semaphore). It is deliberately not mapped onto Gym's rollout `--concurrency`: those are different
        # phases — parallelism bounds concurrent scoring (SDK-side, cheap), while Gym's `--concurrency`
        # bounds concurrent rollouts against the model endpoint during collection (tuned to that endpoint's
        # limits via GymRuntimeConfig.concurrency).
        if config is not None and config.work_dir is not None:
            work_dir = Path(config.work_dir) / "gym_run"
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
        self._run_aggregations = _read_run_aggregations(rollouts_path)
        trials = _trials_from_rollouts(rollouts_path, tasks, index_to_task_id, reward_key=cfg.reward_key)
        _require_full_coverage(tasks, covered_task_ids={trial.task_id for trial in trials}, rollouts_path=rollouts_path)
        return trials

    async def _validate_config(
        self, gym: str, selection: Sequence[str], subprocess_env: Mapping[str, str], work_dir: Path
    ) -> None:
        """Pre-flight the composed Gym config with ``gym env validate`` before starting anything.

        Gym does not publish what configuration an environment requires — the typed
        ``*ResourcesServerConfig`` classes cover behavioural knobs, while the model wiring lives in
        each environment's YAML under names that vary per environment. ``gym env validate`` is the
        only way to find out short of running: it merges configs, flags, and overrides, then reports
        unresolved ``???`` values, bad paths, and cross-references to servers that are not defined —
        without Ray and without starting a server.

        Running it every time is worth the second it costs. A config mistake otherwise surfaces after
        ``gym env start`` has brought up a Ray cluster and several uvicorn servers, as a readiness
        timeout up to ``startup_timeout_s`` (240s by default) whose message says nothing about the
        actual problem.
        """
        proc = await asyncio.create_subprocess_exec(
            gym,
            "env",
            "validate",
            *selection,
            env=dict(subprocess_env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_VALIDATE_TIMEOUT_S)
        except TimeoutError:
            await _terminate(proc, grace_s=self._config.shutdown_grace_s)
            raise RuntimeError(
                f"`gym env validate` did not finish within {_VALIDATE_TIMEOUT_S}s for resources-server "
                f"{self._config.resources_server!r}"
            ) from None

        report = stdout.decode("utf-8", errors="replace").strip()
        (work_dir / "gym_validate.log").write_text(report, encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(
                f"Gym rejected the composed config for resources-server {self._config.resources_server!r} "
                f"before any server started. `gym env validate` said:\n\n{report}"
            )
        logger.debug("gym env validate: %s", report)

    async def _run_two_step(self, input_path: Path, output_path: Path, work_dir: Path) -> None:
        """Start the Gym servers, collect against them with ``--no-serve``, then tear them down."""
        cfg = self._config
        gym = _gym_executable()
        env_log = work_dir / "gym_env.log"

        # Gym launches each server from its own subdir with its own .venv. Ray (>=2.56) otherwise
        # detects a `uv run` ancestor and tries to replicate that uv project onto its workers,
        # asserting the project pyproject.toml lives in the driver's cwd — which aborts startup. That
        # hook is wrong for Gym (servers manage their own deps), so disable it for the subprocesses.
        subprocess_env = {**os.environ, "RAY_ENABLE_UV_RUN_RUNTIME_ENV": "0"}

        selection = _selection_args(cfg, work_dir)

        await self._validate_config(gym, selection, subprocess_env, work_dir)

        env_cmd = [gym, "env", "start", *selection]
        # start_new_session=True puts `gym env start` in its own process group so teardown can signal
        # the *whole* Ray-cluster + uvicorn tree, not just the direct child (else they orphan).
        # stderr is merged into stdout here (unlike `eval run`, which splits them) because readiness
        # detection scans a single chronological transcript and Gym's readiness line is not guaranteed
        # to land on a particular stream.
        env_proc = await asyncio.create_subprocess_exec(
            *env_cmd,
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


def _aggregate_metrics_path_for(rollouts_path: Path) -> Path:
    """Sidecar Gym writes run-level aggregate metrics to (``<stem>_aggregate_metrics.json``)."""
    return rollouts_path.with_name(rollouts_path.stem + "_aggregate_metrics.json")


def _read_run_aggregations(rollouts_path: Path) -> dict[str, Any] | None:
    """Parse Gym's ``rollouts_aggregate_metrics.json``, or ``None`` when absent/unparseable.

    Gym's file is a list with one entry per agent (``agent_ref`` / ``agent_metrics`` / ``key_metrics`` /
    ``group_level_metrics``), so it is returned keyed by agent name. Carried through as-is — Gym's schema
    isn't contractual, so the SDK does not type it.
    """
    path = _aggregate_metrics_path_for(rollouts_path)
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        # UnicodeDecodeError is a ValueError, not an OSError: a sidecar truncated mid-codepoint would
        # otherwise raise straight out of run_tasks and discard a collection that already succeeded.
        logger.warning("Could not parse Gym aggregate metrics at %s; skipping run aggregations.", path)
        return None
    if not isinstance(parsed, list):
        logger.warning("Unexpected Gym aggregate-metrics shape at %s (%s); skipping.", path, type(parsed).__name__)
        return None
    # Gym's schema is not contractual, and this runs after a collection that already succeeded — an
    # entry in an unexpected shape must not raise out of run_tasks and discard every trial with it.
    aggregations: dict[str, Any] = {}
    for entry in parsed:
        agent_ref = entry.get("agent_ref") if isinstance(entry, Mapping) else None
        name = agent_ref.get("name") if isinstance(agent_ref, Mapping) else None
        if not isinstance(name, str):
            logger.warning(
                "Skipping a Gym aggregate-metrics entry in %s with no usable agent_ref.name (got %r).", path, agent_ref
            )
            continue
        aggregations[name] = {key: value for key, value in entry.items() if key != "agent_ref"}
    return aggregations or None


#: Gym flattens a distribution into ``<stat>/<metric>`` keys. Its RewardProfiler emits this exact set
#: together for every numeric column (``describe_dataframe``), minus ``histogram``, which
#: ``prepare_for_serialization`` strips before the file is written. All five must be present before we
#: treat a group of keys as one distribution: a resources-server is free to define a metric literally
#: named ``mean`` (36 of Gym's ~97 servers override ``compute_metrics``), and re-assembling on a partial
#: match would rename someone's standalone metric into a statistic of a distribution that never existed.
_GYM_STAT_FAMILY = ("mean", "max", "min", "median", "std")

#: Metric Gym reports that the SDK already computes natively from the same rollouts (``gym_reward.reward``).
_GYM_REDUNDANT_METRICS = frozenset({"reward"})


def _aggregate_scores_from_gym(aggregations: Mapping[str, Any] | None) -> list[AggregateScore]:
    """Map Gym's run-level ``agent_metrics`` onto typed aggregate scores named ``runner.gym.<metric>``.

    Reads ``agent_metrics``, not ``key_metrics``: ``key_metrics`` is a *subset* of it chosen by the
    resources-server, and the default selection (``get_key_metrics``) keeps only the ``mean/*`` entries —
    so the max/min/median/std that make a distribution never appear there, and every metric would arrive
    as a lone ``mean/<name>`` scalar.

    Keys forming a full stat family are re-assembled into one :class:`AggregateRangeScore`; every other
    numeric key becomes an :class:`AggregateScalarScore`. Non-numeric values are skipped — they are
    labels or notes, not measurements.

    Names are namespaced by runner (not by agent): each run is instrumented with a single agent, so the
    agent adds no disambiguation, and a reader needs to know which *backend* produced a number.
    """
    if not aggregations:
        return []
    multi_agent = len(aggregations) > 1
    scores: list[AggregateScore] = []
    for agent_name, payload in sorted(aggregations.items()):
        agent_metrics = payload.get("agent_metrics") if isinstance(payload, Mapping) else None
        if not isinstance(agent_metrics, Mapping):
            continue
        # One agent per run is the norm, so `runner.gym.<metric>` reads cleanly; qualify by agent only
        # when a run really did produce several, where the unqualified names would collide.
        prefix = f"runner.gym.{agent_name}." if multi_agent else "runner.gym."
        scores.extend(_scores_from_agent_metrics(agent_metrics, prefix=prefix))
    return scores


def _scores_from_agent_metrics(agent_metrics: Mapping[str, Any], *, prefix: str) -> list[AggregateScore]:
    families: dict[str, dict[str, float]] = {}
    scalars: dict[str, float] = {}
    for key, value in agent_metrics.items():
        number = _as_float(value)
        if number is None:
            continue
        stat, _, metric = key.partition("/")
        if metric and stat in _GYM_STAT_FAMILY:
            families.setdefault(metric, {})[stat] = number
        else:
            scalars[key] = number

    scores: list[AggregateScore] = []
    for metric, stats in sorted(families.items()):
        # Redundancy is a property of the metric, not of how complete its family is. Checking after the
        # fallback below would let a partial `reward` family survive as `mean/reward` scalars, since the
        # scalar filter matches the bare name -- reintroducing the duplicate of `gym_reward.reward` that
        # skipping reward exists to prevent.
        if metric in _GYM_REDUNDANT_METRICS:
            continue
        if set(stats) < set(_GYM_STAT_FAMILY):
            # Not a distribution we can vouch for; keep each key as the standalone number it may well be.
            scalars.update({f"{stat}/{metric}": value for stat, value in stats.items()})
            continue
        scores.append(
            AggregateRangeScore(
                name=f"{prefix}{metric}",
                # Gym reports the statistics but not the sample size behind them, and inventing one
                # would misreport coverage. `None` says "unknown"; 0 would assert nothing was evaluated.
                count=None,
                nan_count=0,
                mean=stats["mean"],
                min=stats["min"],
                max=stats["max"],
                median=stats["median"],
                # Gym computes this with pandas (ddof=1), so it is the sample standard deviation.
                sample_std_dev=stats["std"],
                sample_variance=stats["std"] ** 2,
            )
        )
    scores.extend(
        AggregateScalarScore(name=f"{prefix}{key}", count=None, nan_count=0, value=value)
        for key, value in sorted(scalars.items())
        if key not in _GYM_REDUNDANT_METRICS
    )
    return scores


def _as_float(value: Any) -> float | None:
    """``float`` for a numeric Gym metric value; None for anything else (bools included: not measurements)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


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
