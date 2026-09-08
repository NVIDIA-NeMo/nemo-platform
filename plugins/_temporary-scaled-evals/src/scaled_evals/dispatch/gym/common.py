# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared NeMo Gym CLI dispatch helpers.

Both :mod:`scaled_evals.dispatch.gym.daytona` (Harbor ``harbor_agent`` on
Daytona) and :mod:`scaled_evals.dispatch.gym.sandbox_daytona` (``nemo_gym.sandbox``
via Mini SWE Agent 2) launch Gym evaluation work as detached processes.

**``run_and_collect``** (default when ``examples/.../run_and_collect.sh`` exists):
``ng_run`` in the background → ``ng_collect_rollouts`` → shutdown. Used for
custom JSONL inputs (Mini SWE Agent 2 smokes and API dispatch).

**``ng_e2e_collect_rollouts``** (Harbor / dataset-driven configs): downloads or
builds a dataset split from YAML configs, then starts servers and collects.
Requires ``++split=train|validation|task`` — not for arbitrary JSONL files.

**``ng_collect_rollouts``**: rollouts only; ``ng_run`` must already be up.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from scaled_evals.dispatch.credentials import write_env_file
from scaled_evals.dispatch.gym.profile import gym_profile_env
from scaled_evals.dispatch.process import spawn_detached_process
from scaled_evals.dispatch.runtime_backend import LaunchHandle, LaunchSpec
from scaled_evals.dispatch.sandbox_k8s import (
    Runner,
    _inject_extra_skills,
    _patch_instruction,
    _should_stage_uploaded_task_tree,
    _stage_task_tree,
    apply_agent_timeout_floor,
    load_env_file,
)

GYM_E2E_RUN = ("uv", "run", "--no-sync", "ng_e2e_collect_rollouts")
GYM_COLLECT_RUN = ("uv", "run", "--no-sync", "ng_collect_rollouts")


class GymCliBackend(Protocol):
    name: str


def repo_root() -> Path:
    """Scaled-evals repository root (``src/scaled_evals/dispatch/gym/`` → parents[4])."""
    return Path(__file__).resolve().parents[4]


CONTAINER_HARNESS_ROOT = Path("/harness")


def resolve_env_file_path(env_file: str | Path) -> Path:
    """Absolute path to a harness env file (relative paths are repo-rooted)."""
    path = Path(env_file).expanduser()
    if path.is_absolute():
        return path.resolve()

    repo_candidate = (repo_root() / path).resolve()
    if repo_candidate.is_file():
        return repo_candidate

    # Compose mounts repo examples/* at /harness/*; installed api packages have no
    # checkout root, so examples/... relative paths must fall back to that mount.
    parts = path.parts
    if len(parts) >= 2 and parts[0] == "examples":
        harness_candidate = CONTAINER_HARNESS_ROOT.joinpath(*parts[1:]).resolve()
        if harness_candidate.is_file():
            return harness_candidate

    return repo_candidate


def harness_root_from_env_file(env_file: Path) -> Path | None:
    """Return the harness root when env lives at ``<harness>/targets/*.env``."""
    if env_file.parent.name == "targets":
        return env_file.parent.parent
    return None


def resolve_gym_command(target_env: dict[str, str], harness_root: Path | None) -> str:
    if cmd := target_env.get("GYM_COMMAND"):
        return cmd
    if harness_root and (harness_root / "run_and_collect.sh").is_file():
        return "run_and_collect"
    return "ng_e2e_collect_rollouts"


def build_gym_argv(
    *,
    command: str,
    config_paths: str,
    input_jsonl: str | None,
    output_jsonl: str,
    agent_name: str,
    extra_overrides: list[str] | None = None,
) -> list[str]:
    """Build argv for a single Gym CLI invocation (e2e or collect-only)."""
    base = GYM_COLLECT_RUN if command == "ng_collect_rollouts" else GYM_E2E_RUN
    argv = [
        *base,
        f"+config_paths=[{config_paths}]",
        f"++output_jsonl_fpath={output_jsonl}",
        f"++agent_name={agent_name}",
    ]
    if input_jsonl:
        argv.append(f"++input_jsonl_fpath={input_jsonl}")
    if extra_overrides:
        argv.extend(extra_overrides)
    return argv


def validate_gym_launch_contract(spec: LaunchSpec, *, backend_name: str) -> None:
    """Reject LaunchSpec fields this Gym provider cannot honor safely."""
    if spec.network_policy != "unrestricted" or spec.network_policy_config:
        raise RuntimeError(
            f"{backend_name} does not support network_policy={spec.network_policy!r}; "
            "use sandbox_k8s for Kubernetes-enforced egress policy or request "
            "network_policy='unrestricted' for Gym"
        )
    if spec.initial_user_turns:
        raise RuntimeError(f"{backend_name} does not support initial_user_turns")


def materialize_gym_launch_env(
    spec: LaunchSpec,
    target_env: Mapping[str, str],
    *,
    eval_work: Path,
    runner_task_path: Path,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Materialize effective per-run Gym env plus non-secret provenance metadata."""
    env = {key: value for key, value in target_env.items() if value}
    metadata: dict[str, Any] = {
        "task_image_ref": spec.image_ref or None,
        "task_image_digest": spec.image_digest,
        "task_pack_object_key": spec.tarball_object_key,
        "parallelism": spec.parallelism,
        "n_attempts": spec.n_attempts,
        "network_policy": spec.network_policy,
        "network_policy_config": spec.network_policy_config,
    }
    if spec.image_ref:
        env["TASK_IMAGE"] = spec.image_ref
        env["SCALED_EVALS_TASK_IMAGE"] = spec.image_ref
    if spec.image_digest:
        env["SCALED_EVALS_TASK_IMAGE_DIGEST"] = spec.image_digest
    if spec.tarball_object_key:
        env["SCALED_EVALS_TASK_PACK_OBJECT_KEY"] = spec.tarball_object_key

    requested_task_tree_mutation = bool(
        spec.extra_skill_object_keys
        or spec.instruction_prefix
        or spec.instruction_postfix
        or spec.agent_timeout_floor_sec is not None
    )
    staged_task_dir = eval_work / "task"
    if _should_stage_uploaded_task_tree(spec):
        staged = _stage_task_tree(spec.tarball_object_key or "", staged_task_dir)
        if staged is not None:
            materials: list[dict[str, Any]] = []
            if spec.extra_skill_object_keys:
                materials = _inject_extra_skills(staged, spec.extra_skill_object_keys)
            _patch_instruction(staged, spec.instruction_prefix, spec.instruction_postfix)
            if spec.agent_timeout_floor_sec is not None:
                metadata["agent_timeout_apply"] = apply_agent_timeout_floor(staged, spec.agent_timeout_floor_sec)
            env["TASK_PATH"] = str(runner_task_path)
            metadata["task_path"] = str(runner_task_path)
            metadata["task_pack_staged"] = True
            metadata["extra_skill_materials"] = materials
        elif requested_task_tree_mutation:
            raise RuntimeError("Gym task-tree mutations require an uploaded task pack containing task.toml")
        else:
            metadata["task_pack_staged"] = False
    elif requested_task_tree_mutation:
        raise RuntimeError("Gym task-tree mutations require a staged uploaded task pack")

    overrides = [f"++num_samples_in_parallel={spec.parallelism}"]
    if spec.n_attempts != 1:
        overrides.append(f"++num_repeats={spec.n_attempts}")
    existing = env.get("GYM_EXTRA_OVERRIDES")
    env["GYM_EXTRA_OVERRIDES"] = ",".join([*([existing] if existing else []), *overrides])
    metadata["gym_extra_overrides"] = env["GYM_EXTRA_OVERRIDES"]
    return env, metadata


def build_run_and_collect_argv(
    *,
    script: Path,
    env_file: Path,
    evaluation_id: str,
    work_dir: Path,
) -> list[str]:
    """Argv to run the shared harness script (API dispatch and local smokes)."""
    return [
        "bash",
        str(script),
        *build_run_and_collect_command(
            env_file=env_file,
            evaluation_id=evaluation_id,
            work_dir=work_dir,
        ),
    ]


def build_run_and_collect_command(
    *,
    env_file: Path,
    evaluation_id: str,
    work_dir: Path,
) -> list[str]:
    """Arguments for run_and_collect.sh (host bash or container ENTRYPOINT)."""
    return [
        "--env-file",
        str(env_file),
        "--job-name",
        evaluation_id,
        "--work-dir",
        str(work_dir),
    ]


def _spawn_detached(argv: list[str], cwd: Path, log_path: Path, env: dict[str, str]) -> None:
    with log_path.open("w") as log:
        spawn_detached_process(argv, cwd=cwd, log=log, env=env)


def make_gym_submitter(
    *,
    backend_name: str,
    gym_dir: str,
    env_file: str,
    work_dir: str = "/tmp",
    runner: Runner | None = None,
    process_runner: Callable[[list[str], Path, Path, dict[str, str]], Mapping[str, object]] | None = None,
    extra_overrides_for_spec: Callable[[LaunchSpec, dict[str, str]], list[str]] | None = None,
) -> Callable[[LaunchSpec], LaunchHandle]:
    """Build a live submitter that fires detached Gym work for one evaluation."""
    gym = Path(gym_dir).expanduser().resolve()
    envf = resolve_env_file_path(env_file)
    work = Path(work_dir).expanduser().resolve()
    harness_root = harness_root_from_env_file(envf)

    def submit(spec: LaunchSpec) -> LaunchHandle:
        validate_gym_launch_contract(spec, backend_name=backend_name)
        target_env = load_env_file(envf)
        if spec.framework_config:
            target_env.update(gym_profile_env(spec.framework_config))
        eval_work = work / spec.evaluation_id
        eval_work.mkdir(parents=True, exist_ok=True)
        target_env, launch_metadata = materialize_gym_launch_env(
            spec,
            target_env,
            eval_work=eval_work,
            runner_task_path=eval_work / "task",
        )
        command = resolve_gym_command(target_env, harness_root)
        agent_name = target_env.get("GYM_AGENT_NAME")
        if not agent_name:
            raise RuntimeError(
                "Gym run configuration is incomplete: select a non-empty gym "
                "framework_profile_id with agent_name, command, and config_paths"
            )

        output_jsonl = str(eval_work / "rollouts.jsonl")
        log_path = eval_work / "gym.log"
        credential_envf = eval_work / "target.env"
        write_env_file(credential_envf, {**target_env, **spec.credential_env})
        merged_env = {**os.environ, **target_env, **spec.credential_env}

        if command == "run_and_collect":
            if harness_root is None:
                raise RuntimeError(
                    f"GYM_COMMAND=run_and_collect requires env file under <harness>/targets/*.env; got {envf}"
                )
            script = (harness_root / "run_and_collect.sh").resolve()
            if not script.is_file():
                raise RuntimeError(f"run_and_collect script not found: {script}")
            argv = build_run_and_collect_argv(
                script=script,
                env_file=credential_envf,
                evaluation_id=spec.evaluation_id,
                work_dir=eval_work,
            )
        else:
            config_paths = target_env["GYM_CONFIG_PATHS"]
            input_jsonl = target_env.get("GYM_INPUT_JSONL")
            if command == "ng_collect_rollouts" and not input_jsonl:
                raise RuntimeError("GYM_INPUT_JSONL is required for ng_collect_rollouts")
            extra: list[str] = []
            if extra_overrides_for_spec is not None:
                extra.extend(extra_overrides_for_spec(spec, target_env))
            if raw_extra := target_env.get("GYM_EXTRA_OVERRIDES"):
                extra.extend(part.strip() for part in raw_extra.split(",") if part.strip())
            if command == "ng_e2e_collect_rollouts":
                if split := target_env.get("GYM_SPLIT"):
                    extra.append(f"++split={split}")
                if limit := target_env.get("GYM_LIMIT"):
                    extra.append(f"++limit={limit}")
            argv = build_gym_argv(
                command=command,
                config_paths=config_paths,
                input_jsonl=input_jsonl,
                output_jsonl=output_jsonl,
                agent_name=agent_name,
                extra_overrides=extra or None,
            )

        def _live_runner(argv: list[str], cwd: Path, log: Path) -> None:
            _spawn_detached(argv, cwd, log, merged_env)

        process_metadata: Mapping[str, object] = {}
        if process_runner is not None:
            process_metadata = process_runner(argv, gym, log_path, merged_env)
        else:
            (runner or _live_runner)(argv, gym, log_path)

        return LaunchHandle(
            backend=backend_name,
            external_id=spec.evaluation_id,
            raw={
                "argv": argv,
                "log": str(log_path),
                "output_jsonl": output_jsonl,
                "gym_dir": str(gym),
                "command": command,
                "agent_timeout_apply": launch_metadata.get("agent_timeout_apply"),
                "effective_runtime_settings": launch_metadata,
                **process_metadata,
            },
        )

    return submit
