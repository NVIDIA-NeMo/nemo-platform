# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run Gym inside the owning Kubernetes evaluation Job process namespace."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from scaled_evals.api.settings import settings
from scaled_evals.dispatch.gym.common import make_gym_submitter
from scaled_evals.dispatch.gym.docker import (
    _status_from_gym_result,
    rollouts_jsonl_to_result_envelope,
)
from scaled_evals.dispatch.process import spawn_detached_process
from scaled_evals.dispatch.runtime_backend import LaunchHandle, LaunchSpec, RuntimeStatus


def _process_start_identity(pid: int) -> str:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    return stat.rsplit(")", 1)[1].split()[19]


def _write_exit_code(path: Path, process: subprocess.Popen[bytes]) -> None:
    code = process.wait()
    temp = path.with_suffix(".tmp")
    temp.write_text(f"{code}\n", encoding="utf-8")
    temp.replace(path)


def _launch_process(argv: list[str], cwd: Path, log_path: Path, env: dict[str, str]) -> dict[str, object]:
    exit_code_path = log_path.parent / "exit-code"
    exit_code_path.unlink(missing_ok=True)
    with log_path.open("wb") as log:
        process = spawn_detached_process(argv, cwd=cwd, log=log, env=env)
    thread = threading.Thread(
        target=_write_exit_code,
        args=(exit_code_path, process),
        daemon=True,
        name=f"gym-reaper-{process.pid}",
    )
    thread.start()
    return {
        "process_pid": process.pid,
        "process_start_identity": _process_start_identity(process.pid),
        "process_owner_pod": os.getenv("HOSTNAME", ""),
        "exit_code_path": str(exit_code_path),
    }


def make_gym_process_submitter(
    *,
    backend_name: str,
    gym_dir: str,
    env_file: str,
    work_dir: str,
) -> Callable[[LaunchSpec], LaunchHandle]:
    """Launch Gym as a child of the owning evaluation Job worker."""
    submit = make_gym_submitter(
        backend_name=backend_name,
        gym_dir=gym_dir,
        env_file=env_file,
        work_dir=work_dir,
        process_runner=_launch_process,
    )

    def launch(spec: LaunchSpec) -> LaunchHandle:
        handle = submit(spec)
        raw = {
            **handle.raw,
            "process": True,
            "observed_runner_image_digest": spec.runner_image_digest,
            "observed_gym_source_revision": spec.runner_source_revision,
            "observed_gym_package_version": spec.runner_package_version,
            "remote_teardown": {
                "strategy": "owning_job_process_group",
                "providers": ["opensandbox"],
            },
        }
        return LaunchHandle(backend=handle.backend, external_id=handle.external_id, raw=raw)

    return launch


def _tail(path: Path) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-800:] if len(text) > 800 else text


def make_gym_process_status_reader(*, work_dir: str) -> Callable[[LaunchHandle], RuntimeStatus]:
    work = Path(work_dir).expanduser().resolve()

    def read(handle: LaunchHandle) -> RuntimeStatus:
        eval_work = work / handle.external_id
        output = eval_work / "rollouts.jsonl"
        exit_path = Path(str(handle.raw.get("exit_code_path") or eval_work / "exit-code"))
        if exit_path.is_file():
            exit_code = int(exit_path.read_text(encoding="utf-8").strip())
            if exit_code != 0:
                detail = _tail(eval_work / "gym.log") or _tail(eval_work / "ng_run.log")
                return RuntimeStatus(
                    phase="failed",
                    detail=f"gym process exited {exit_code}: {detail}",
                )
            if not output.is_file():
                return RuntimeStatus(
                    phase="failed",
                    detail="gym process exited 0 but rollouts.jsonl is missing",
                )
            result = rollouts_jsonl_to_result_envelope(output, evaluation_id=handle.external_id)
            return _status_from_gym_result(result)

        owner = str(handle.raw.get("process_owner_pod") or "")
        if owner and owner != os.getenv("HOSTNAME", ""):
            return RuntimeStatus(
                phase="failed",
                detail="gym process cannot be resumed in a replacement pod",
            )
        pid = int(handle.raw.get("process_pid") or 0)
        expected_start = str(handle.raw.get("process_start_identity") or "")
        try:
            running = pid > 0 and _process_start_identity(pid) == expected_start
        except (FileNotFoundError, ProcessLookupError, ValueError):
            running = False
        if running:
            return RuntimeStatus(phase="running", detail="gym process running in evaluation Job")
        return RuntimeStatus(phase="failed", detail="gym process disappeared without exit status")

    return read


def make_gym_process_terminator() -> Callable[[LaunchHandle], None]:
    def terminate(handle: LaunchHandle) -> None:
        owner = str(handle.raw.get("process_owner_pod") or "")
        if owner and owner != os.getenv("HOSTNAME", ""):
            return
        pid = int(handle.raw.get("process_pid") or 0)
        expected_start = str(handle.raw.get("process_start_identity") or "")
        if pid <= 0:
            return
        try:
            if _process_start_identity(pid) != expected_start:
                return
        except (FileNotFoundError, ProcessLookupError, ValueError):
            return
        with suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + settings.gym_runner_teardown_timeout_seconds
        while time.monotonic() < deadline:
            try:
                _process_start_identity(pid)
            except (FileNotFoundError, ProcessLookupError, ValueError):
                return
            time.sleep(0.2)
        with suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)

    return terminate
