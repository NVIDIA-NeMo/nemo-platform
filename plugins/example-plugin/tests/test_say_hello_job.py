# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for :class:`~nemo_example_plugin.jobs.say_hello.SayHelloJob`."""

from __future__ import annotations

import json
from pathlib import Path

from nemo_example_plugin.jobs.say_hello import (
    DEFAULT_FILE_NAME,
    DEFAULT_RESULT_NAME,
    SayHelloJob,
)
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults
from nemo_platform_plugin.jobs.constants import NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR
from nemo_platform_plugin.tasks.dispatcher import run_task


def _write_config(tmp_path: Path, payload: dict) -> Path:
    config_path = tmp_path / "step-config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


def _local_ctx(tmp_path: Path, *, workspace: str = "dev") -> JobContext:
    storage = StoragePaths(ephemeral=tmp_path / "e", persistent=tmp_path / "p")
    storage.ephemeral.mkdir()
    storage.persistent.mkdir()
    return JobContext(
        workspace=workspace,
        storage=storage,
        results=LocalJobResults(root=storage.persistent / "results"),
    )


def test_say_hello_job_metadata() -> None:
    assert SayHelloJob.name == "say-hello"
    assert SayHelloJob.description


def test_say_hello_runs_through_task_dispatcher(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, {"name": "Razvan"})
    monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_path))
    ctx = _local_ctx(tmp_path)

    exit_code = run_task(SayHelloJob, ctx=ctx)

    assert exit_code == 0
    artifact_path = ctx.storage.persistent / "results" / DEFAULT_RESULT_NAME
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == "Hello, Razvan!"


def test_defaults_name_to_world(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, {})
    monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_path))
    ctx = _local_ctx(tmp_path)

    assert run_task(SayHelloJob, ctx=ctx) == 0
    assert (ctx.storage.persistent / DEFAULT_FILE_NAME).read_text(encoding="utf-8") == "Hello, world!"


def test_greeting_text_lands_under_persistent(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path, {"name": "Razvan"})
    monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_path))
    ctx = _local_ctx(tmp_path)

    run_task(SayHelloJob, ctx=ctx)

    assert (ctx.storage.persistent / DEFAULT_FILE_NAME).read_text(encoding="utf-8") == "Hello, Razvan!"
