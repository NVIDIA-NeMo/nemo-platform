# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for NemoCLI renderer hooks on generated submit commands."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, ClassVar

import httpx
import typer
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


class _GreetResponse(BaseModel):
    message: str


class _GreetFunction(NemoFunction[_GreetSpec]):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Say hello to a name."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    async def run(self, spec: _GreetSpec) -> _GreetResponse:
        return _GreetResponse(message=f"Hello, {spec.name}!")


class _CountSpec(BaseModel):
    upto: int


class _CountFunction(NemoFunction[_CountSpec]):
    name: ClassVar[str] = "count"
    spec_schema: ClassVar[type[_CountSpec]] = _CountSpec

    async def run(self, spec: _CountSpec) -> dict:
        return {"upto": spec.upto}


class _GreetJob(NemoJob):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Return a greeting."

    def run(self, config: dict) -> dict:
        return {"message": f"Hello, {config.get('name', 'world')}!"}


class _NoOpCLI(NemoCLI):
    name: ClassVar[str] = "test-plugin"

    def get_cli(self) -> typer.Typer:
        return typer.Typer()


class _RecordingRenderer(CLIRenderer):
    """Renderer that records lifecycle events for assertions."""

    events: list[tuple[str, Any]] = []  # noqa: RUF012 - class state shared for tests

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


class _RaisingRenderer(_RecordingRenderer):
    def on_frame(self, frame: Any, *, ctx: RendererContext) -> None:
        super().on_frame(frame, ctx=ctx)
        raise RuntimeError("boom")


def _typer_context_with_overrides(output_format: str | None = None) -> object:
    overrides: dict[str, Any] = {}
    if output_format is not None:
        overrides["output_format"] = output_format
    return SimpleNamespace(overrides=overrides)


def _build_function_app(*fn_classes: type[NemoFunction], cli: NemoCLI | None = None) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    fns = {f"plugin.{cls.name}": cls for cls in fn_classes}
    add_function_commands(app, fns, cli=cli)
    return app


def _build_job_app(*job_classes: type[NemoJob], cli: NemoCLI | None = None) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    jobs = {f"plugin.{cls.name}": cls for cls in job_classes}
    add_job_commands(app, jobs, cli=cli)
    return app


def _patch_ndjson_client(monkeypatch, *, body: str | None = None) -> None:
    ndjson_body = body or json.dumps({"kind": "heartbeat"}) + "\n" + json.dumps({"kind": "done"}) + "\n"

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=ndjson_body,
            headers={"content-type": "application/x-ndjson"},
        )

    transport = httpx.MockTransport(_handler)
    original_client = httpx.Client

    def _client_factory(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return original_client(*args, **kwargs)

    monkeypatch.setattr("nemo_platform_plugin.commands.httpx.Client", _client_factory)


class TestStreamingFunctionSubmitRenderer:
    def test_no_renderer_falls_through_to_default_echo(self, monkeypatch) -> None:
        _patch_ndjson_client(monkeypatch)
        app = _build_function_app(_CountFunction, cli=_NoOpCLI())
        result = runner.invoke(app, ["count", "submit", "--upto", "2", "--base-url", "http://test"])
        assert result.exit_code == 0
        json_lines = [ln for ln in result.output.splitlines() if ln.strip().startswith("{")]
        assert len(json_lines) == 2

    def test_renderer_lifecycle_fires_in_order(self, monkeypatch) -> None:
        _patch_ndjson_client(monkeypatch)

        class _CLI(_NoOpCLI):
            def get_function_renderer(self, fn_cls, *, verb):
                return _RecordingRenderer if fn_cls is _CountFunction else None

        app = _build_function_app(_CountFunction, cli=_CLI())
        result = runner.invoke(app, ["count", "submit", "--upto", "2", "--base-url", "http://test"])
        assert result.exit_code == 0, result.output

        events = _RecordingRenderer.events
        names = [name for name, _ in events]
        assert names == ["start", "frame", "frame", "complete"]
        assert events[0][1] == {"verb": "submit", "is_local": False}

    def test_output_format_json_bypasses_renderer(self, monkeypatch) -> None:
        _patch_ndjson_client(monkeypatch)

        class _CLI(_NoOpCLI):
            def get_function_renderer(self, fn_cls, *, verb):
                return _RecordingRenderer

        app = _build_function_app(_CountFunction, cli=_CLI())
        ctx_obj = _typer_context_with_overrides(output_format="json")

        _RecordingRenderer.events = []
        result = runner.invoke(
            app,
            ["count", "submit", "--upto", "1", "--base-url", "http://test"],
            obj=ctx_obj,
        )
        assert result.exit_code == 0, result.output
        assert _RecordingRenderer.events == []
        assert result.output.count('"kind"') == 2

    def test_renderer_dispatches_per_function_and_verb(self, monkeypatch) -> None:
        _patch_ndjson_client(monkeypatch)
        seen: list[tuple[str, str]] = []

        class _CLI(_NoOpCLI):
            def get_function_renderer(self, fn_cls, *, verb):
                seen.append((fn_cls.name, verb))
                return None

        app = _build_function_app(_CountFunction, _GreetFunction, cli=_CLI())
        runner.invoke(app, ["count", "submit", "--upto", "1", "--base-url", "http://test"])

        assert ("count", "submit") in seen


class TestJobSubmitRenderer:
    def test_no_renderer_falls_through_to_default(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote",
            lambda *_args, **_kwargs: {"message": "Hello, World!"},
        )
        app = _build_job_app(_GreetJob, cli=_NoOpCLI())
        result = runner.invoke(app, ["greet", "submit", "--spec", '{"name": "World"}'])
        assert result.exit_code == 0
        assert json.loads(result.output) == {"message": "Hello, World!"}

    def test_renderer_lifecycle_for_submit(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote",
            lambda *_args, **_kwargs: {"message": "Hello, Renderer!"},
        )

        class _CLI(_NoOpCLI):
            def get_job_renderer(self, job_cls, *, verb):
                return _RecordingRenderer

        app = _build_job_app(_GreetJob, cli=_CLI())
        _RecordingRenderer.events = []
        result = runner.invoke(app, ["greet", "submit", "--spec", '{"name": "Renderer"}'])
        assert result.exit_code == 0, result.output

        events = _RecordingRenderer.events
        assert [name for name, _ in events] == ["start", "frame", "complete"]
        assert events[0][1] == {"verb": "submit", "is_local": False}
        assert events[1][1] == {"message": "Hello, Renderer!"}

    def test_output_format_json_bypasses_job_renderer(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote",
            lambda *_args, **_kwargs: {"message": "Hello, X!"},
        )

        class _CLI(_NoOpCLI):
            def get_job_renderer(self, job_cls, *, verb):
                return _RecordingRenderer

        app = _build_job_app(_GreetJob, cli=_CLI())
        ctx_obj = _typer_context_with_overrides(output_format="json")
        _RecordingRenderer.events = []
        result = runner.invoke(app, ["greet", "submit", "--spec", '{"name": "X"}'], obj=ctx_obj)
        assert result.exit_code == 0
        assert _RecordingRenderer.events == []
        assert json.loads(result.output) == {"message": "Hello, X!"}


class TestDelegateContract:
    def test_delegating_wrapper_still_drives_renderer(self, monkeypatch) -> None:
        _patch_ndjson_client(monkeypatch)

        class _CLI(_NoOpCLI):
            def update_function_cli(self, fn_cls, group):
                if fn_cls is not _CountFunction:
                    return
                original = next(c for c in group.registered_commands if c.name == "submit").callback
                assert original is not None

                @group.command("submit")
                def submit(typer_ctx: typer.Context, count: int = typer.Option(2, "--count")) -> None:
                    spec_json = json.dumps({"upto": count})
                    original(
                        typer_ctx,
                        spec=spec_json,
                        spec_file=None,
                        cluster=None,
                        base_url="http://test",
                        workspace="default",
                        request_id=None,
                    )

            def get_function_renderer(self, fn_cls, *, verb):
                return _RecordingRenderer if fn_cls is _CountFunction else None

        app = _build_function_app(_CountFunction, cli=_CLI())
        _RecordingRenderer.events = []
        result = runner.invoke(app, ["count", "submit", "--count", "1"])
        assert result.exit_code == 0, result.output

        events = _RecordingRenderer.events
        assert [name for name, _ in events] == ["start", "frame", "frame", "complete"]


class TestOnError:
    def test_on_error_fires_when_renderer_frame_raises(self, monkeypatch) -> None:
        _patch_ndjson_client(monkeypatch, body=json.dumps({"kind": "heartbeat"}) + "\n")

        class _CLI(_NoOpCLI):
            def get_function_renderer(self, fn_cls, *, verb):
                return _RaisingRenderer

        app = _build_function_app(_CountFunction, cli=_CLI())
        _RaisingRenderer.events = []
        result = runner.invoke(app, ["count", "submit", "--upto", "1", "--base-url", "http://test"])

        assert result.exit_code != 0
        events = _RaisingRenderer.events
        names = [name for name, _ in events]
        assert names == ["start", "frame", "error"]
        assert events[-1][1] == "RuntimeError"
