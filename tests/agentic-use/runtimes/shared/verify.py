# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live VERIFY phase executed through the environment boundary.

Ports ``nat_runner.run_verify_phase`` onto :meth:`AgentEnvironmentHandle.run_verifier`
so the task-local ``tests/test_outputs.py`` pytest verifier runs in the *same*
prepared environment (and against the same persisted workspace/state) as the
agent phase. The resulting reward is stamped onto the attempt metadata so the
``VerifierRewardMetric`` compatibility metric scores it through the Evaluator SDK.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtimes.shared.constants import (
    DOCKER_SOCKET_CONTAINER_PATH,
    DOCKER_SOCKET_HOST_PATH,
    EVALUATOR_SDK_SRC,
    FILES_STORAGE_CONFIG,
    PLATFORM_CONFIG_PATH,
    SHARED_DIR,
)
from runtimes.shared.environment import AgentEnvironmentHandle, EnvRunSpec
from runtimes.shared.layout import AgenticRunLayout


@dataclass(frozen=True)
class VerifierOutcome:
    """Result of the live verifier phase for one task."""

    ran: bool
    passed: bool
    reward: int
    exit_code: int
    stdout: str
    verifier_log_dir: Path | None


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
    log_dir = verifier_log_dir(layout)
    passed = result.ok

    stdout = ""
    stdout_path = log_dir / "test-stdout.txt"
    if stdout_path.is_file():
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")

    reward_path = log_dir / "reward.txt"
    if reward_path.is_file():
        reward = 1 if reward_path.read_text(encoding="utf-8").strip() == "1" else 0
    else:
        reward = 1 if passed else 0
        reward_path.write_text("1\n" if passed else "0\n", encoding="utf-8")

    return VerifierOutcome(
        ran=True,
        passed=passed,
        reward=reward,
        exit_code=result.exit_code,
        stdout=stdout,
        verifier_log_dir=log_dir,
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
        return VerifierOutcome(ran=False, passed=False, reward=0, exit_code=0, stdout="", verifier_log_dir=None)
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
        return VerifierOutcome(ran=False, passed=False, reward=0, exit_code=0, stdout="", verifier_log_dir=None)
    return await run_verify(handle, spec, layout)


def apply_verify_to_metadata(metadata: dict[str, Any], outcome: VerifierOutcome) -> None:
    """Stamp verifier reward/status onto attempt metadata for scoring + gating."""
    if not outcome.ran:
        metadata.setdefault("verify_status", "skipped")
        return
    metadata["verify_status"] = "ok" if outcome.passed else "failed"
    metadata["passed"] = outcome.passed
    metadata["reward"] = outcome.reward
    metadata["verifier_log_dir"] = str(outcome.verifier_log_dir) if outcome.verifier_log_dir else None
