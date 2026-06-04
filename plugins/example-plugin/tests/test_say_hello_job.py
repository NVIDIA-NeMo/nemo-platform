# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for :class:`~nemo_example_plugin.jobs.say_hello.SayHelloJob`.

Pin the job implementation: running it with an explicit
:class:`~nemo_platform_plugin.job_context.JobContext` writes the greeting to
``ctx.storage.persistent`` and registers it via the configured results sink.
"""

from __future__ import annotations

from pathlib import Path

from nemo_example_plugin.jobs.say_hello import (
    DEFAULT_FILE_NAME,
    DEFAULT_RESULT_NAME,
    SayHelloJob,
)
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults


def _ctx(tmp_path: Path) -> JobContext:
    storage = StoragePaths(ephemeral=tmp_path / "e", persistent=tmp_path / "p")
    storage.ephemeral.mkdir()
    storage.persistent.mkdir()
    return JobContext(
        workspace="dev",
        storage=storage,
        results=LocalJobResults(root=storage.persistent / "results"),
    )


def test_say_hello_job_metadata() -> None:
    assert SayHelloJob.name == "say-hello"
    assert SayHelloJob.description


def test_say_hello_writes_artifact(tmp_path: Path) -> None:
    result = SayHelloJob().run({"name": "Razvan"}, ctx=_ctx(tmp_path))
    assert result["result"] == "Hello, Razvan!"
    artefact = result["artifact"]
    assert artefact["name"] == DEFAULT_RESULT_NAME
    artifact_path = Path(artefact["artifact_url"].removeprefix("file://"))
    assert artifact_path.exists()
    assert artifact_path.read_text() == "Hello, Razvan!"


def test_defaults_name_to_world(tmp_path: Path) -> None:
    result = SayHelloJob().run({}, ctx=_ctx(tmp_path))
    assert result["result"] == "Hello, world!"


def test_greeting_text_lands_under_persistent(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    SayHelloJob().run({"name": "Razvan"}, ctx=ctx)
    assert (ctx.storage.persistent / DEFAULT_FILE_NAME).read_text() == "Hello, Razvan!"
