# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NeMo-Platform glue that sits on top of the generic agent-eval SDK.

Everything generic (Docker helpers, the environment boundary, environment
authoring, gating, attempt-status/evidence helpers, the verifier mechanic) now
lives in ``nemo_evaluator_sdk.agent_eval`` and is imported directly where used.

This single module holds only the pieces that are specific to the agentic-use
benchmark and therefore do not belong in the SDK:

* run layout with the platform ``state_dir`` and the ``nmp-nat-<id>`` image tag,
* a ``DockerEnvironmentProvider`` defaulting to that platform image tag,
* default metrics (``AgentPhaseSuccessMetric`` namespace + ``VerifierRewardMetric``),
* agent-log/usage parsing and the shared container env,
* attempt construction from live artifacts and from ``nat_runner`` ``result.json``,
* the live VERIFY phase wired through the SDK environment boundary,
* the agentic-use task loader.
"""

from __future__ import annotations

import json
import textwrap
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from evaluator_agent_eval.artifacts import AgentArtifacts
from evaluator_agent_eval.schemas import (
    AgentAttemptInput,
    AgentAttemptMetadata,
    AgentAttemptOutput,
    AgentAttemptTrace,
    CapturedAgentAttempt,
)
from nemo_evaluator_sdk.agent_eval.attempts import resolve_attempt_status, standard_evidence_descriptors
from nemo_evaluator_sdk.agent_eval.common_metrics import AgentPhaseSuccessMetric as _SDKAgentPhaseSuccessMetric
from nemo_evaluator_sdk.agent_eval.runtimes.environment import (
    AgentEnvironmentHandle,
    EnvRunSpec,
)
from nemo_evaluator_sdk.agent_eval.runtimes.environment import (
    DockerEnvironmentProvider as _SDKDockerEnvironmentProvider,
)
from nemo_evaluator_sdk.agent_eval.runtimes.layout import prepare_run_layout, resolve_run_dir
from nemo_evaluator_sdk.agent_eval.runtimes.verify import (
    VerifierOutcome,
    collect_verifier_outcome,
    skipped_outcome,
)
from nemo_evaluator_sdk.agent_eval.types import (
    AgentEvalAttempt,
    AgentEvalRunConfig,
    AgentEvalTask,
    AgentOutput,
)
from nemo_evaluator_sdk.metrics.protocol import (
    Metric,
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)
from nemo_evaluator_sdk.values.evidence import CandidateEvidence, EvidenceDescriptor

from runtimes.shared.config import AgenticRuntimeName, AgenticSharedConfig
from runtimes.shared.constants import (
    AGENTIC_USE_DIR,
    DOCKER_SOCKET_CONTAINER_PATH,
    DOCKER_SOCKET_HOST_PATH,
    EVALUATOR_SDK_SRC,
    FILES_STORAGE_CONFIG,
    PLATFORM_CONFIG_PATH,
    SHARED_DIR,
)

__all__ = [
    "AgenticRunLayout",
    "AgentPhaseSuccessMetric",
    "DockerEnvironmentProvider",
    "ResultDirAttemptSource",
    "VerifierRewardMetric",
    "agent_log_has_workflow_error",
    "agentic_task_from_dir",
    "attempt_from_result",
    "attempt_from_result_dir",
    "base_container_env",
    "build_agent_eval_attempt",
    "build_verify_run_spec",
    "extract_usage_metrics",
    "iter_agent_log_json_payloads",
    "load_task_toml",
    "maybe_run_verify",
    "resolve_run_layout",
    "run_verify",
    "task_agent_timeout_sec",
    "task_image_tag",
    "to_captured_agent_attempt",
    "verifier_log_dir",
    "with_candidate_params",
]


# --------------------------------------------------------------------------- #
# Run layout + image tagging
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgenticRunLayout:
    """Filesystem layout for one task run.

    Extends the SDK's generic ``RunLayout`` shape with a platform-specific
    ``state_dir`` (preserved platform/database state across agent + verifier).
    """

    run_dir: Path
    agent_log_dir: Path
    workspace_dir: Path
    state_dir: Path
    instruction_path: Path


def task_image_tag(task_id: str) -> str:
    return f"nmp-nat-{task_id}:latest"


def default_jobs_dir(shared: AgenticSharedConfig) -> Path:
    if shared.jobs_dir is not None:
        return shared.jobs_dir
    return shared.repo_root / "nat-jobs"


def new_run_dir(jobs_dir: Path, task_id: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = jobs_dir / f"{timestamp}-{task_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def resolve_run_layout(
    task: AgentEvalTask,
    shared: AgenticSharedConfig,
    config: AgentEvalRunConfig | None = None,
) -> AgenticRunLayout:
    """Resolve or create the on-disk layout for one task attempt."""
    output_dir = config.output_dir if config is not None else None
    run_dir = resolve_run_dir(output_dir, lambda: new_run_dir(default_jobs_dir(shared), task.id))

    # Generic agent/workspace dirs + written instruction come from the SDK helper.
    base = prepare_run_layout(run_dir, task.intent)

    # Platform extension: a preserved state dir for platform/db across phases.
    state_dir = base.run_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    return AgenticRunLayout(
        run_dir=base.run_dir,
        agent_log_dir=base.agent_log_dir,
        workspace_dir=base.workspace_dir,
        state_dir=state_dir,
        instruction_path=base.instruction_path,
    )


class DockerEnvironmentProvider(_SDKDockerEnvironmentProvider):
    """Platform default: map ``task.id`` to ``nmp-nat-<id>:latest``."""

    def __init__(self, *, image_tag_fn: Callable[[str], str] = task_image_tag) -> None:
        super().__init__(image_tag_fn=image_tag_fn)


# --------------------------------------------------------------------------- #
# Default metrics
# --------------------------------------------------------------------------- #
class AgentPhaseSuccessMetric(_SDKAgentPhaseSuccessMetric):
    """Agentic-use namespaced agent-phase metric (output stays ``agent_phase_success``)."""

    metric_type = "agentic_use_agent_phase"


class VerifierRewardMetric:
    """Compatibility metric mirroring the legacy pytest verifier reward.

    Reads the verifier outcome that ``nat_runner`` records in ``result.json``
    (projected onto attempt metadata as ``reward``/``passed``) so existing
    ``tests/test_outputs.py`` verifiers can score through the Evaluator SDK
    while task-specific metrics are authored.
    """

    @property
    def type(self) -> str:
        return "agentic_use_verifier_reward"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("verifier_reward")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        metadata = input.candidate.metadata
        reward = metadata.get("reward")
        if reward is None:
            reward = 1.0 if metadata.get("passed") else 0.0
        return MetricResult(
            outputs=[MetricOutput(name="verifier_reward", value=float(reward))],
        )


# --------------------------------------------------------------------------- #
# Agent-log parsing + token usage
# --------------------------------------------------------------------------- #
class TokenMetrics(TypedDict):
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cache_creation_tokens: int | None
    cache_read_tokens: int | None
    n_assistant_messages: int | None
    cost_usd: float | None
    num_turns: int | None
    duration_ms: float | None


def extract_usage_metrics(agent_log: str) -> dict[str, int | float | None]:
    """Extract token usage metrics from an agent log."""
    import nat_runner

    metrics = nat_runner._extract_usage_metrics(agent_log)
    return dict(metrics)


def iter_agent_log_json_payloads(agent_log: str) -> list[dict[str, Any]]:
    """Return JSON dict payloads embedded in an agent log, newest-first after the full log."""
    candidates = [agent_log.strip()]
    lines = [line.strip() for line in agent_log.splitlines() if line.strip()]
    if lines:
        candidates.append(lines[-1])
        candidates.extend(reversed(lines))

    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
    return payloads


def agent_log_has_workflow_error(agent_log: str) -> bool:
    """Detect AUT workflow errors returned as successful HTTP JSON payloads."""
    for payload in iter_agent_log_json_payloads(agent_log):
        if payload.get("code") == "workflow_error":
            return True
    return False


# --------------------------------------------------------------------------- #
# Shared container environment
# --------------------------------------------------------------------------- #
def base_container_env(shared: AgenticSharedConfig, *, timeout_sec: int) -> dict[str, str]:
    """Environment variables shared by all agentic-use container runs."""
    env: dict[str, str] = {
        "NMP_BASE_URL": shared.nmp_base_url,
        "AGENTIC_USE_WORKSPACE_DIR": "/app/workspace",
        "DATABASE_DIALECT": "sqlite",
        "DATABASE_PATH": "/data/nmp-platform.db",
        "NMP_FILES_DEFAULT_STORAGE_CONFIG": FILES_STORAGE_CONFIG,
        "NMP_CONFIG_FILE_PATH": PLATFORM_CONFIG_PATH,
        "NEMO_AGENTS_GATEWAY_READ_TIMEOUT": str(timeout_sec),
        "NEMO_AGENTS_INVOKE_TIMEOUT": str(timeout_sec),
        "AUT_INVOKE_HTTP_TIMEOUT": str(timeout_sec),
    }
    if DOCKER_SOCKET_HOST_PATH.exists():
        env["DOCKER_HOST"] = f"unix://{DOCKER_SOCKET_CONTAINER_PATH}"
    return env


def with_candidate_params(env: dict[str, str], agent_params: dict[str, Any]) -> dict[str, str]:
    if agent_params:
        env = dict(env)
        env["NAT_CANDIDATE_PARAMS"] = json.dumps(agent_params, sort_keys=True)
    return env


# --------------------------------------------------------------------------- #
# Attempt construction from live artifacts
# --------------------------------------------------------------------------- #
def build_agent_eval_attempt(
    *,
    task: AgentEvalTask,
    layout: AgenticRunLayout,
    runtime_name: AgenticRuntimeName,
    agent_model: str,
    exit_code: int,
    agent_ok: bool,
    run_id: str | None = None,
    repo_revision: str | None = None,
    duration_ms: int | None = None,
) -> AgentEvalAttempt:
    """Build an SDK attempt from on-disk agent artifacts.

    Metadata uses the same canonical keys as :class:`CapturedAgentAttempt`
    (``agent_runtime``, ``agent_model``, ``exit_code``, …) so verify/scoring
    helpers can consume attempts without a second adapter.
    """
    artifacts = AgentArtifacts.from_dir(layout.agent_log_dir, workspace_dir=layout.workspace_dir)
    log_text = _read_agent_log(layout.agent_log_dir)
    usage = extract_usage_metrics(log_text)
    duration = duration_ms if duration_ms is not None else usage.get("duration_ms")

    output_text = artifacts.final_answer.text if artifacts.final_answer.extracted else None
    raw_log_paths = _raw_log_paths(artifacts.agent_log_dir)
    initial_state = task.inputs.get("filesystem")
    descriptors = _evidence_descriptors(
        layout, artifacts, initial_state_ref=str(initial_state) if initial_state else None
    )

    metadata: dict[str, object] = {
        # Canonical CapturedAgentAttempt fields
        "agent_runtime": runtime_name,
        "agent_model": agent_model,
        "agent_runtime_version": None,
        "repo_revision": repo_revision,
        "run_id": run_id,
        "exit_code": exit_code,
        "duration_ms": duration,
        # SDK / orchestration extensions
        "model_id": agent_model,
        "target_name": agent_model,
        "attempt_id": f"{task.id}:{runtime_name}",
        "agent_ok": agent_ok,
        "agent_log_dir": str(layout.agent_log_dir),
        "workspace_dir": str(layout.workspace_dir),
        "state_dir": str(layout.state_dir),
        "run_dir": str(layout.run_dir),
        "instruction_path": task.metadata.get("instruction_path"),
        "final_answer_extracted": artifacts.final_answer.extracted,
        "final_answer_source": artifacts.final_answer.source,
        "raw_log_paths": raw_log_paths,
        "atif_trajectory_path": str(artifacts.atif_trajectory_path) if artifacts.atif_trajectory_path else None,
        **usage,
    }

    status = resolve_attempt_status(agent_ok)
    if output_text:
        output = AgentOutput(text=output_text)
    elif agent_ok:
        output = AgentOutput(text=log_text.strip() or "")
    else:
        output = AgentOutput(text=log_text.strip() or "(agent phase failed)")

    return AgentEvalAttempt(
        id=f"{task.id}:{runtime_name}",
        task_id=task.id,
        status=status,
        output=output,
        evidence=CandidateEvidence(descriptors=descriptors) if descriptors else None,
        metadata=metadata,
    )


def to_captured_agent_attempt(task: AgentEvalTask, attempt: AgentEvalAttempt) -> CapturedAgentAttempt:
    """Project an SDK attempt onto the portable CapturedAgentAttempt schema."""
    metadata = attempt.metadata
    trace_path = metadata.get("atif_trajectory_path")
    return CapturedAgentAttempt(
        task_id=attempt.task_id,
        input=AgentAttemptInput(
            instruction_text=task.intent,
            instruction_path=str(metadata.get("instruction_path")) if metadata.get("instruction_path") else None,
        ),
        output=AgentAttemptOutput(
            final_text=attempt.output.text if attempt.output is not None else "",
            final_answer_extracted=bool(metadata.get("final_answer_extracted")),
            final_answer_source=str(metadata.get("final_answer_source"))
            if metadata.get("final_answer_source") is not None
            else None,
            raw_log_paths=list(metadata.get("raw_log_paths") or []),
        ),
        metadata=AgentAttemptMetadata(
            agent_runtime=str(metadata.get("agent_runtime", "unknown")),
            agent_model=str(metadata.get("agent_model", "unknown")),
            agent_runtime_version=str(metadata["agent_runtime_version"])
            if metadata.get("agent_runtime_version") is not None
            else None,
            repo_revision=str(metadata["repo_revision"]) if metadata.get("repo_revision") is not None else None,
            run_id=str(metadata["run_id"]) if metadata.get("run_id") is not None else None,
            exit_code=int(metadata["exit_code"]) if isinstance(metadata.get("exit_code"), int) else None,
            duration_ms=int(metadata["duration_ms"]) if isinstance(metadata.get("duration_ms"), int | float) else None,
        ),
        trace=AgentAttemptTrace(atif_path=str(trace_path)) if trace_path else None,
    )


def _evidence_descriptors(
    layout: AgenticRunLayout,
    artifacts: AgentArtifacts,
    *,
    initial_state_ref: str | None = None,
) -> dict[str, EvidenceDescriptor]:
    """Compose the SDK's standard evidence keys + the platform ``state`` extension.

    The doc-standard keys (``initial_state``/``trace``/``logs``/``final_state``/
    ``verifier_logs``) come from :func:`standard_evidence_descriptors`. ``state``
    is a NeMo-Platform-specific *extension* (not a doc key): it carries the
    preserved platform/database state across the agent + verifier phases.
    """
    descriptors = standard_evidence_descriptors(
        logs_dir=layout.agent_log_dir,
        final_state_dir=layout.workspace_dir,
        trace_path=artifacts.atif_trajectory_path,
        initial_state_ref=initial_state_ref,
        verifier_logs_dir=layout.run_dir / "verifier",
        primary_log="nat_agent.log",
    )

    # Platform extension (non-doc key): preserved platform/db state across phases.
    descriptors["state"] = EvidenceDescriptor(
        kind="filesystem",
        format="dir",
        ref=str(layout.state_dir),
        metadata={"role": "platform_state", "extension": "nemo-platform"},
    )

    return descriptors


def _raw_log_paths(agent_log_dir: Path) -> list[str]:
    if not agent_log_dir.is_dir():
        return []
    return [str(path.relative_to(agent_log_dir)) for path in sorted(agent_log_dir.iterdir()) if path.is_file()]


def _read_agent_log(agent_log_dir: Path) -> str:
    log_path = agent_log_dir / "nat_agent.log"
    if log_path.is_file():
        return log_path.read_text(encoding="utf-8", errors="replace")
    return ""


# --------------------------------------------------------------------------- #
# Attempt construction from nat_runner result.json
# --------------------------------------------------------------------------- #
# Token/cost measurement keys carried in result.json["metrics"].
_METRIC_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "n_assistant_messages",
    "cost_usd",
    "num_turns",
    "duration_ms",
    "token_metrics_status",
    "token_metrics_note",
)


class ResultDirAttemptSource:
    """``AgentAttemptSerde`` for a ``nat_runner`` run directory.

    Implements the SDK :class:`~nemo_evaluator_sdk.agent_eval.types.AgentAttemptSerde`
    protocol so the generic pipeline's offline path can rescore captured runs. The
    serde is bound to one directory: :meth:`read` materializes an attempt from a
    persisted ``attempt.json`` when present, otherwise it projects ``nat_runner``'s
    legacy ``result.json``; :meth:`write` persists an attempt back as
    ``attempt.json`` so capture/replay round-trips through the same codec.
    """

    ATTEMPT_FILENAME = "attempt.json"

    def __init__(self, path: str | Path, *, task: AgentEvalTask | None = None) -> None:
        self._path = Path(path)
        self._task = task

    def read(self) -> AgentEvalAttempt:
        attempt_path = self._path / self.ATTEMPT_FILENAME
        if attempt_path.is_file():
            return AgentEvalAttempt.model_validate_json(attempt_path.read_text(encoding="utf-8"))
        return attempt_from_result_dir(self._path, task=self._task)

    def write(self, attempt: AgentEvalAttempt) -> None:
        self._path.mkdir(parents=True, exist_ok=True)
        (self._path / self.ATTEMPT_FILENAME).write_text(
            attempt.model_dump_json(indent=2), encoding="utf-8"
        )


def attempt_from_result_dir(output_dir: str | Path, *, task: AgentEvalTask | None = None) -> AgentEvalAttempt:
    """Load ``<output_dir>/result.json`` and build an attempt from it."""
    output_dir = Path(output_dir)
    result_path = output_dir / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError(f"result.json not found in {output_dir}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    return attempt_from_result(result, output_dir=output_dir, task=task)


def attempt_from_result(
    result: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    task: AgentEvalTask | None = None,
) -> AgentEvalAttempt:
    """Project a ``result.json`` dict onto :class:`AgentEvalAttempt`.

    The attempt ``status`` reflects whether the agent produced a usable
    response (``agent`` phase outcome). Pass/fail from the verifier is recorded
    as a *measurement* in metadata (``reward``/``passed``) so scoring metrics —
    not the runtime — remain the source of truth.
    """
    task_id = str(result.get("task") or (task.id if task is not None else "unknown"))
    backend = str(result.get("agent_backend") or "unknown")
    resolved_dir = Path(output_dir) if output_dir is not None else Path(str(result.get("output_dir") or "."))
    layout = _layout_from_result_dir(resolved_dir)

    agent_phase = str(result.get("agent") or "")
    agent_ok = agent_phase in {"ok", "skipped"}
    status = resolve_attempt_status(agent_ok)

    output_text, final_extracted, final_source = _resolve_output_text(layout)
    if not output_text:
        output_text = "" if agent_ok else "(agent phase failed)"

    descriptors = _evidence_descriptors(
        layout, AgentArtifacts.from_dir(layout.agent_log_dir, workspace_dir=layout.workspace_dir)
    )

    metrics = dict(result.get("metrics") or {})
    metadata: dict[str, Any] = {
        # Canonical CapturedAgentAttempt-style provenance fields.
        "agent_runtime": backend,
        "agent_model": result.get("agent_model"),
        "run_id": (result.get("provenance") or {}).get("run_id"),
        "exit_code": 0 if agent_ok else 1,
        "duration_ms": metrics.get("duration_ms"),
        # Phase outcomes from result.json.
        "agent_ok": agent_ok,
        "build_status": result.get("build"),
        "agent_status": result.get("agent"),
        "verify_status": result.get("verify"),
        # Measurements (verifier reward is a measurement, not attempt status).
        "passed": result.get("passed"),
        "reward": result.get("reward"),
        "runtime_sec": result.get("runtime_sec"),
        "verifier_scores": result.get("verifier_scores"),
        # Provenance + candidate identity.
        "provenance": result.get("provenance"),
        "candidate_id": result.get("candidate_id"),
        "candidate_params": result.get("candidate_params"),
        "image": result.get("image"),
        "output_dir": str(resolved_dir),
        # Artifact discovery helpers.
        "agent_log_dir": str(layout.agent_log_dir),
        "workspace_dir": str(layout.workspace_dir),
        "state_dir": str(layout.state_dir),
        "final_answer_extracted": final_extracted,
        "final_answer_source": final_source,
    }
    metadata.update({key: metrics.get(key) for key in _METRIC_KEYS})

    return AgentEvalAttempt(
        id=f"{task_id}:{backend}",
        task_id=task_id,
        status=status,
        output=AgentOutput(text=output_text),
        evidence=CandidateEvidence(descriptors=descriptors) if descriptors else None,
        metadata=metadata,
    )


def _layout_from_result_dir(output_dir: Path) -> AgenticRunLayout:
    agent_log_dir = output_dir / "agent"
    return AgenticRunLayout(
        run_dir=output_dir,
        agent_log_dir=agent_log_dir,
        workspace_dir=output_dir / "workspace",
        state_dir=output_dir / "state",
        instruction_path=agent_log_dir / "instruction.md",
    )


def _resolve_output_text(layout: AgenticRunLayout) -> tuple[str, bool, str | None]:
    if not layout.agent_log_dir.is_dir():
        return "", False, None
    artifacts = AgentArtifacts.from_dir(layout.agent_log_dir, workspace_dir=layout.workspace_dir)
    if artifacts.final_answer.extracted and artifacts.final_answer.text:
        return artifacts.final_answer.text, True, artifacts.final_answer.source
    log_path = layout.agent_log_dir / "nat_agent.log"
    if log_path.is_file():
        return log_path.read_text(encoding="utf-8", errors="replace").strip(), False, None
    return "", False, None


# --------------------------------------------------------------------------- #
# Live VERIFY phase through the SDK environment boundary
# --------------------------------------------------------------------------- #
def verifier_log_dir(layout: AgenticRunLayout) -> Path:
    return layout.run_dir / "verifier"


def build_verify_run_spec(
    task_dir: Path,
    layout: AgenticRunLayout,
    *,
    nmp_base_url: str,
    agent_backend: str,
    agent_model: str,
    smoke_workspace: str | None = None,
    timeout_sec: int | None = None,
    extra_args: list[str] | None = None,
) -> EnvRunSpec | None:
    """Build the verifier ``EnvRunSpec`` mirroring ``nat_runner.run_verify_phase``.

    Returns ``None`` when the task has no ``tests/test_outputs.py`` (nothing to
    verify), matching the runner's behavior.
    """
    tests_dir = task_dir / "tests"
    if not (tests_dir / "test_outputs.py").exists():
        return None

    log_dir = verifier_log_dir(layout)
    log_dir.mkdir(parents=True, exist_ok=True)
    layout.workspace_dir.mkdir(parents=True, exist_ok=True)

    smoke_seed_cmd = ""
    smoke_cleanup_cmd = ""
    if smoke_workspace:
        smoke_seed_cmd = textwrap.dedent("""\
            /app/.venv/bin/nemo workspaces create "${SMOKE_WORKSPACE}" \
              --description "Seeded by agentic runtime smoke mode" >/dev/null 2>&1 || true
        """)
        smoke_cleanup_cmd = textwrap.dedent("""\
            /app/.venv/bin/nemo workspaces delete "${SMOKE_WORKSPACE}" >/dev/null 2>&1 || true
        """)

    verify_cmd = [
        "bash",
        "-c",
        textwrap.dedent(f"""\
            export PYTHONPATH="/app/tests/agentic-use/shared:/app/packages/nemo_evaluator_sdk/src:${{PYTHONPATH}}"
            export NAT_AGENT=1
            {smoke_seed_cmd}
            /app/.venv/bin/python -m pytest /tests/test_outputs.py -rA -v 2>&1 | tee /logs/verifier/test-stdout.txt
            EXIT=${{PIPESTATUS[0]}}
            {smoke_cleanup_cmd}
            if [ $EXIT -eq 0 ]; then echo 1; else echo 0; fi > /logs/verifier/reward.txt
            exit $EXIT
        """),
    ]

    env: dict[str, str] = {
        "NMP_BASE_URL": nmp_base_url,
        "NAT_AGENT": "1",
        "NAT_AGENT_BACKEND": agent_backend,
        "NAT_AGENT_MODEL": agent_model,
        "AGENTIC_USE_TASK_DIR": "/task",
        "AGENTIC_USE_WORKSPACE_DIR": "/app/workspace",
        "SMOKE_WORKSPACE": smoke_workspace or "",
        "DATABASE_DIALECT": "sqlite",
        "DATABASE_PATH": "/data/nmp-platform.db",
        "NMP_FILES_DEFAULT_STORAGE_CONFIG": FILES_STORAGE_CONFIG,
        "NMP_CONFIG_FILE_PATH": PLATFORM_CONFIG_PATH,
    }
    if DOCKER_SOCKET_HOST_PATH.exists():
        env["DOCKER_HOST"] = f"unix://{DOCKER_SOCKET_CONTAINER_PATH}"

    mounts: list[tuple[str, str]] = [
        (str(tests_dir), "/tests"),
        (str(task_dir), "/task"),
        (str(layout.workspace_dir), "/app/workspace"),
        (str(SHARED_DIR), "/app/tests/agentic-use/shared:ro"),
        (str(EVALUATOR_SDK_SRC), "/app/packages/nemo_evaluator_sdk/src:ro"),
        (str(layout.agent_log_dir), "/logs/agent"),
        (str(log_dir), "/logs/verifier"),
        # Persist platform/db state across AGENT and VERIFY containers.
        (str(layout.state_dir), "/data"),
    ]
    if DOCKER_SOCKET_HOST_PATH.exists():
        mounts.append((str(DOCKER_SOCKET_HOST_PATH), DOCKER_SOCKET_CONTAINER_PATH))

    return EnvRunSpec(
        command=verify_cmd,
        env=env,
        mounts=mounts,
        timeout=timeout_sec,
        extra_args=list(extra_args or []),
    )


async def run_verify(
    handle: AgentEnvironmentHandle,
    spec: EnvRunSpec,
    layout: AgenticRunLayout,
) -> VerifierOutcome:
    """Execute the verifier through the environment handle and collect reward."""
    result = await handle.run_verifier(spec)
    return collect_verifier_outcome(
        ok=result.ok,
        exit_code=result.exit_code,
        log_dir=verifier_log_dir(layout),
    )


async def maybe_run_verify(
    handle: AgentEnvironmentHandle,
    *,
    enabled: bool,
    task_dir: Path,
    layout: AgenticRunLayout,
    nmp_base_url: str,
    agent_backend: str,
    agent_model: str,
    smoke_workspace: str | None = None,
    timeout_sec: int | None = None,
    extra_args: list[str] | None = None,
) -> VerifierOutcome:
    """Run the verifier through ``handle`` when enabled and a verifier exists."""
    if not enabled:
        return skipped_outcome()
    spec = build_verify_run_spec(
        task_dir,
        layout,
        nmp_base_url=nmp_base_url,
        agent_backend=agent_backend,
        agent_model=agent_model,
        smoke_workspace=smoke_workspace,
        timeout_sec=timeout_sec,
        extra_args=extra_args,
    )
    if spec is None:
        return skipped_outcome()
    return await run_verify(handle, spec, layout)


# --------------------------------------------------------------------------- #
# Agentic-use task loader
# --------------------------------------------------------------------------- #
def load_task_toml(task_dir: Path) -> dict[str, object]:
    task_toml = task_dir / "task.toml"
    if not task_toml.exists():
        return {}
    try:
        with task_toml.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def task_agent_timeout_sec(task_dir: Path) -> int | None:
    data = load_task_toml(task_dir)
    agent = data.get("agent")
    if not isinstance(agent, dict):
        return None
    timeout_value = agent.get("timeout_sec")
    if isinstance(timeout_value, (int, float)) and timeout_value > 0:
        return int(timeout_value)
    return None


def agentic_task_from_dir(
    task_dir: str | Path,
    *,
    tasks_root: Path | None = None,
    metrics: list[Metric] | None = None,
) -> AgentEvalTask:
    """Build an :class:`AgentEvalTask` from an agentic-use task directory.

    ``inputs`` carries only agent-facing material (``instruction``) per the SDK
    design doc; runtime materialization details such as ``task_dir`` live in
    ``metadata`` so they cannot leak into metric scoring rows. Metrics are
    authored *on the task* (defaulting to :class:`AgentPhaseSuccessMetric`); the
    orchestrator only appends compatibility metrics, it does not own the set.
    """
    root = Path(tasks_root or AGENTIC_USE_DIR)
    task_path = Path(task_dir)
    if not task_path.is_absolute():
        task_path = (root / task_path).resolve()

    instruction_path = task_path / "instruction.md"
    if not instruction_path.exists():
        raise FileNotFoundError(f"instruction.md not found in {task_path}")

    instruction = instruction_path.read_text(encoding="utf-8")
    task_toml = load_task_toml(task_path)

    return AgentEvalTask(
        id=task_path.name,
        intent=instruction,
        inputs={
            "instruction": instruction,
        },
        metrics=metrics if metrics is not None else [AgentPhaseSuccessMetric()],
        metadata={
            "benchmark": "agentic-use",
            "task_toml": task_toml,
            "instruction_path": str(instruction_path),
            "task_dir": str(task_path),
        },
    )
