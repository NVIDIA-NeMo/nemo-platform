# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for NemoCLI submit renderer hooks."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
import typer
from nemo_platform_plugin import commands
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.cli_renderer import CLIRenderer, RendererContext
from nemo_platform_plugin.commands import add_function_commands, add_job_commands
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.job import NemoJob
from pydantic import BaseModel
from typer.testing import CliRunner

runner = CliRunner()


class _GreetSpec(BaseModel):
    name: str


class _GreetJob(NemoJob):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Submit a greeting."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    def run(self, config: dict) -> dict:
        return {"message": f"Hello, {config['name']}!"}


class _GreetFunction(NemoFunction[_GreetSpec]):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Submit a greeting function."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    async def run(self, spec: _GreetSpec) -> dict:
        return {"message": f"Hello, {spec.name}!"}


_GreetFunction.__module__ = "nemo_plugin.functions.greet"


class _NoOpCLI(NemoCLI):
    name: ClassVar[str] = "test-plugin"

    def get_cli(self) -> typer.Typer:
        return typer.Typer()


class _RecordingRenderer(CLIRenderer):
    """Renderer that records lifecycle events for assertions."""

    events: list[tuple[str, Any]] = []

    def __init__(self) -> None:
        type(self).events = []

    def on_start(self, *, ctx: RendererContext) -> None:
        type(self).events.append(("start", {"verb": ctx.verb, "is_local": ctx.is_local}))

    def on_frame(self, frame: Any, *, ctx: RendererContext) -> None:
        del ctx
        type(self).events.append(("frame", frame))

    def on_complete(self, *, ctx: RendererContext) -> None:
        del ctx
        type(self).events.append(("complete", None))

    def on_error(self, error: BaseException, *, ctx: RendererContext) -> None:
        del ctx
        type(self).events.append(("error", type(error).__name__))


def _typer_context_with_overrides(output_format: str | None = None) -> object:
    overrides: dict[str, Any] = {}
    if output_format is not None:
        overrides["output_format"] = output_format
    return SimpleNamespace(overrides=overrides)


def _build_job_app(*job_classes: type[NemoJob], cli: NemoCLI | None = None) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    jobs = {f"plugin.{cls.name}": cls for cls in job_classes}
    add_job_commands(app, jobs, cli=cli)
    return app


def _build_function_app(*fn_classes: type[NemoFunction], cli: NemoCLI | None = None) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    functions = {f"plugin.{cls.name}": cls for cls in fn_classes}
    add_function_commands(app, functions, cli=cli)
    return app


def test_job_submit_no_renderer_falls_through_to_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        del self, job_cls, kwargs
        return {"submitted": spec_data}

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)
    app = _build_job_app(_GreetJob, cli=_NoOpCLI())
    result = runner.invoke(app, ["greet", "submit", "--name", "World"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"submitted": {"name": "World"}}


def test_job_submit_renderer_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        del self, job_cls, kwargs
        return {"submitted": spec_data}

    class _CLI(_NoOpCLI):
        def get_job_renderer(self, job_cls, *, verb):
            return _RecordingRenderer if job_cls is _GreetJob and verb == "submit" else None

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)
    app = _build_job_app(_GreetJob, cli=_CLI())
    _RecordingRenderer.events = []
    result = runner.invoke(app, ["greet", "submit", "--name", "Renderer"])

    assert result.exit_code == 0, result.output
    assert _RecordingRenderer.events == [
        ("start", {"verb": "submit", "is_local": False}),
        ("frame", {"submitted": {"name": "Renderer"}}),
        ("complete", None),
    ]


def test_output_format_json_bypasses_job_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        del self, job_cls, kwargs
        return {"submitted": spec_data}

    class _CLI(_NoOpCLI):
        def get_job_renderer(self, job_cls, *, verb):
            del job_cls, verb
            return _RecordingRenderer

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)
    app = _build_job_app(_GreetJob, cli=_CLI())
    ctx_obj = _typer_context_with_overrides(output_format="json")
    _RecordingRenderer.events = []
    result = runner.invoke(app, ["greet", "submit", "--name", "X"], obj=ctx_obj)

    assert result.exit_code == 0
    assert _RecordingRenderer.events == []
    assert json.loads(result.output) == {"submitted": {"name": "X"}}


def test_function_submit_forwards_renderer_to_http_streamer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def post_function_submit(url, body, **kwargs):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["body"] = body
        captured["renderer_cls"] = kwargs["renderer_cls"]

    class _CLI(_NoOpCLI):
        def get_function_renderer(self, fn_cls, *, verb):
            return _RecordingRenderer if fn_cls is _GreetFunction and verb == "submit" else None

    monkeypatch.setattr(commands, "_post_function_submit", post_function_submit)
    app = _build_function_app(_GreetFunction, cli=_CLI())
    result = runner.invoke(app, ["greet", "submit", "--name", "Fn", "--base-url", "https://nmp.test"])

    assert result.exit_code == 0
    assert captured["url"] == "https://nmp.test/apis/plugin/v2/workspaces/default/greet"
    assert captured["body"] == {"name": "Fn"}
    assert captured["renderer_cls"] is _RecordingRenderer


def test_function_submit_output_format_json_bypasses_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def post_function_submit(url, body, **kwargs):  # type: ignore[no-untyped-def]
        del url, body
        captured["renderer_cls"] = kwargs["renderer_cls"]

    class _CLI(_NoOpCLI):
        def get_function_renderer(self, fn_cls, *, verb):
            del fn_cls, verb
            return _RecordingRenderer

    monkeypatch.setattr(commands, "_post_function_submit", post_function_submit)
    app = _build_function_app(_GreetFunction, cli=_CLI())
    ctx_obj = _typer_context_with_overrides(output_format="json")
    result = runner.invoke(app, ["greet", "submit", "--name", "Fn"], obj=ctx_obj)

    assert result.exit_code == 0
    assert captured["renderer_cls"] is None


def test_delegating_job_submit_wrapper_still_drives_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        del self, job_cls, kwargs
        return {"submitted": spec_data}

    class _CLI(_NoOpCLI):
        def update_job_cli(self, job_cls, group):
            if job_cls is not _GreetJob:
                return
            original = next(c for c in group.registered_commands if c.name == "submit").callback
            assert original is not None

            @group.command("submit")
            def submit(typer_ctx: typer.Context, name: str = typer.Option(..., "--name")) -> None:
                original(typer_ctx, spec=json.dumps({"name": name}), spec_file=None)

        def get_job_renderer(self, job_cls, *, verb):
            return _RecordingRenderer if job_cls is _GreetJob and verb == "submit" else None

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)
    app = _build_job_app(_GreetJob, cli=_CLI())
    _RecordingRenderer.events = []
    result = runner.invoke(app, ["greet", "submit", "--name", "Wrapped"])

    assert result.exit_code == 0, result.output
    assert [name for name, _ in _RecordingRenderer.events] == ["start", "frame", "complete"]


def test_job_submit_renderer_on_error_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        del self, job_cls, spec_data, kwargs
        raise RuntimeError("boom")

    class _CLI(_NoOpCLI):
        def get_job_renderer(self, job_cls, *, verb):
            return _RecordingRenderer if job_cls is _GreetJob and verb == "submit" else None

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)
    app = _build_job_app(_GreetJob, cli=_CLI())
    _RecordingRenderer.events = []
    result = runner.invoke(app, ["greet", "submit", "--name", "Err"])

    assert result.exit_code != 0
    assert ("error", "RuntimeError") in _RecordingRenderer.events
    assert "complete" not in [name for name, _ in _RecordingRenderer.events]
