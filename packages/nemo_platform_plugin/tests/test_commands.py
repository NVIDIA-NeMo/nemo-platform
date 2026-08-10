# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the generated submit-only plugin CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import AsyncIterator

import pytest
import typer
from nemo_platform_plugin import commands
from nemo_platform_plugin.commands import add_function_commands, add_job_commands
from nemo_platform_plugin.discovery import discover, discover_manifests
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.job import NemoJob
from pydantic import BaseModel
from typer.testing import CliRunner


@pytest.fixture(autouse=True)
def clear_discovery_cache():
    discover.cache_clear()
    discover_manifests.cache_clear()
    yield
    discover.cache_clear()
    discover_manifests.cache_clear()


class _GreetSpec(BaseModel):
    name: str
    count: int = 1


class _GreetJob(NemoJob):
    name = "greet"
    description = "Submit a greeting job."
    spec_schema = _GreetSpec

    def run(self, config: dict) -> dict:
        return {"message": f"Hello, {config['name']}!"}


class _RunNamedJob(NemoJob):
    name = "run"
    description = "A job whose name collides with the removed local verb."

    def run(self, config: dict) -> dict:
        return config


class _GreetFunction(NemoFunction):
    name = "greet"
    description = "Submit a greeting function."
    spec_schema = _GreetSpec

    async def run(self, spec: _GreetSpec) -> dict:
        return {"message": f"Hello, {spec.name}!"}


class _CountFunction(NemoFunction):
    name = "count"
    description = "Submit a streaming function."
    spec_schema = _GreetSpec

    async def run(self, spec: _GreetSpec) -> AsyncIterator[BaseModel]:
        for idx in range(spec.count):
            yield _GreetSpec(name=spec.name, count=idx)


_GreetFunction.__module__ = "nemo_plugin.functions.greet"
_CountFunction.__module__ = "nemo_plugin.functions.count"

runner = CliRunner()


def _app_with_jobs(*job_classes: type[NemoJob]) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    jobs = {f"plugin.{cls.name}": cls for cls in job_classes}
    add_job_commands(app, jobs)
    return app


def _app_with_functions(*fn_classes: type[NemoFunction]) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    functions = {f"plugin.{cls.name}": cls for cls in fn_classes}
    add_function_commands(app, functions)
    return app


def test_job_subgroup_exposes_submit_and_explain_only() -> None:
    app = _app_with_jobs(_GreetJob)
    result = runner.invoke(app, ["greet", "--help"])

    assert result.exit_code == 0
    assert "submit" in result.output
    assert "explain" in result.output
    assert "Run locally" not in result.output


def test_bare_job_name_exits_non_zero_and_points_at_submit() -> None:
    app = _app_with_jobs(_GreetJob)
    result = runner.invoke(app, ["greet"])

    assert result.exit_code != 0
    assert "submit" in result.output


def test_job_named_run_is_still_a_group_without_local_run_verb() -> None:
    app = _app_with_jobs(_RunNamedJob)
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "submit" in result.output
    assert "explain" in result.output
    assert "Run locally" not in result.output


def test_job_submit_uses_spec_json_and_field_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        captured["job_cls"] = job_cls
        captured["spec"] = spec_data
        captured["kwargs"] = kwargs
        return {"id": "job-123", "status": "queued"}

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)
    app = _app_with_jobs(_GreetJob)
    result = runner.invoke(
        app,
        [
            "greet",
            "submit",
            "--spec",
            '{"name": "Base"}',
            "--count",
            "3",
            "--base-url",
            "https://nmp.test",
            "--workspace",
            "team",
            "--profile",
            "gpu",
            "-o",
            "slurm.nodes=2",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"id": "job-123", "status": "queued"}
    assert captured["job_cls"] is _GreetJob
    assert captured["spec"] == {"name": "Base", "count": 3}
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["base_url"] == "https://nmp.test"
    assert kwargs["workspace"] == "team"
    assert kwargs["profile"] == "gpu"
    assert kwargs["options"] == {"slurm": {"nodes": "2"}}


def test_job_submit_accepts_spec_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    spec_file = tmp_path / "spec.json"
    spec_file.write_text('{"name": "File"}', encoding="utf-8")

    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        del self, job_cls, kwargs
        captured["spec"] = spec_data
        return {"id": "job-file"}

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)
    app = _app_with_jobs(_GreetJob)
    result = runner.invoke(app, ["greet", "submit", "--spec-file", str(spec_file)])

    assert result.exit_code == 0
    assert captured["spec"] == {"name": "File"}


def test_job_submit_rejects_invalid_json() -> None:
    app = _app_with_jobs(_GreetJob)
    result = runner.invoke(app, ["greet", "submit", "--spec", "not-json"])

    assert result.exit_code == 1
    assert "invalid spec" in result.output


def test_job_submit_rejects_removed_run_verb() -> None:
    app = _app_with_jobs(_GreetJob)
    result = runner.invoke(app, ["greet", "run", "--spec", '{"name": "X"}'])

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_explain_renders_schema() -> None:
    app = _app_with_jobs(_GreetJob)
    result = runner.invoke(app, ["greet", "explain"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["job_key"].endswith(".greet")
    assert output["spec_schema"]["properties"]["name"]["type"] == "string"


def test_function_subgroup_exposes_submit_only() -> None:
    app = _app_with_functions(_GreetFunction)
    result = runner.invoke(app, ["greet", "--help"])

    assert result.exit_code == 0
    assert "submit" in result.output
    assert "Run locally" not in result.output


def test_function_submit_posts_to_function_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def post_function_submit(url, body, **kwargs):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["body"] = body
        captured["kwargs"] = kwargs

    monkeypatch.setattr(commands, "_post_function_submit", post_function_submit)
    app = _app_with_functions(_GreetFunction)
    result = runner.invoke(
        app,
        [
            "greet",
            "submit",
            "--name",
            "Claude",
            "--count",
            "2",
            "--base-url",
            "https://nmp.test",
            "--workspace",
            "team",
            "--request-id",
            "req-1",
        ],
    )

    assert result.exit_code == 0
    assert captured["url"] == "https://nmp.test/apis/plugin/v2/workspaces/team/greet"
    assert captured["body"] == {"name": "Claude", "count": 2}
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["headers"] == {"X-Request-ID": "req-1"}


def test_function_submit_rejects_invalid_spec_shape() -> None:
    app = _app_with_functions(_GreetFunction)
    result = runner.invoke(app, ["greet", "submit", "--spec", "[]"])

    assert result.exit_code == 1
    assert "invalid spec" in result.output


def test_function_submit_rejects_removed_run_verb() -> None:
    app = _app_with_functions(_CountFunction)
    result = runner.invoke(app, ["count", "run", "--name", "X"])

    assert result.exit_code != 0
    assert "No such command" in result.output
