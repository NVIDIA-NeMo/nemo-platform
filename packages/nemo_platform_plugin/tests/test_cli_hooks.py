# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for NemoCLI.update_function_cli / update_job_cli submit hooks."""

from __future__ import annotations

import json
from typing import ClassVar

import pytest
import typer
from nemo_platform_plugin import commands
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.commands import add_function_commands, add_job_commands
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.job import NemoJob
from pydantic import BaseModel
from typer.testing import CliRunner
import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


runner = CliRunner()


class _GreetSpec(BaseModel):
    name: str


class _GreetJob(NemoJob):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Submit a greeting."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    def run(self, config: dict) -> dict:
        return {"message": f"Hello, {config['name']}!"}


class _ByeJob(NemoJob):
    name: ClassVar[str] = "bye"
    description: ClassVar[str] = "Submit a farewell."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    def run(self, config: dict) -> dict:
        return {"message": f"Bye, {config['name']}!"}


class _GreetResponse(BaseModel):
    message: str


class _GreetFunction(NemoFunction[_GreetSpec]):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Submit a greeting function."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    async def run(self, spec: _GreetSpec) -> _GreetResponse:
        return _GreetResponse(message=f"Hello, {spec.name}!")


class _ByeFunction(NemoFunction[_GreetSpec]):
    name: ClassVar[str] = "bye"
    description: ClassVar[str] = "Submit a farewell function."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    async def run(self, spec: _GreetSpec) -> _GreetResponse:
        return _GreetResponse(message=f"Bye, {spec.name}!")


_GreetFunction.__module__ = "nemo_plugin.functions.greet"
_ByeFunction.__module__ = "nemo_plugin.functions.bye"


class _NoOpCLI(NemoCLI):
    name: ClassVar[str] = "test-plugin"

    def get_cli(self) -> typer.Typer:
        return typer.Typer()


def _app_with_jobs(*job_classes: type[NemoJob], cli: NemoCLI | None = None) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    jobs = {f"plugin.{cls.name}": cls for cls in job_classes}
    add_job_commands(app, jobs, cli=cli)
    return app


def _app_with_functions(*fn_classes: type[NemoFunction], cli: NemoCLI | None = None) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    fns = {f"plugin.{cls.name}": cls for cls in fn_classes}
    add_function_commands(app, fns, cli=cli)
    return app


def _stub_job_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    def submit_remote(self, job_cls, spec_data, **kwargs):  # type: ignore[no-untyped-def]
        del self, job_cls, kwargs
        return {"submitted": spec_data}

    monkeypatch.setattr(commands.NemoJobScheduler, "submit_remote", submit_remote)


def _stub_function_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    def post_function_submit(url, body, **kwargs):  # type: ignore[no-untyped-def]
        del url, body, kwargs

    monkeypatch.setattr(commands, "_post_function_submit", post_function_submit)


class TestUpdateJobCli:
    def test_default_noop_leaves_subcommands_unchanged(self) -> None:
        app = _app_with_jobs(_GreetJob, cli=_NoOpCLI())
        result = runner.invoke(app, ["greet", "--help"])

        assert result.exit_code == 0
        assert "submit" in result.output
        assert "explain" in result.output
        assert "Run locally" not in result.output

    def test_no_cli_argument_uses_default_submit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_job_submit(monkeypatch)
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "submit", "--name", "X"])

        assert result.exit_code == 0
        assert json.loads(result.output) == {"submitted": {"name": "X"}}

    def test_hook_invoked_once_per_job(self) -> None:
        seen: list[str] = []

        class _CLI(_NoOpCLI):
            def update_job_cli(self, job_cls, group) -> None:  # noqa: ARG002
                seen.append(job_cls.name)

        _app_with_jobs(_GreetJob, _ByeJob, cli=_CLI())
        assert sorted(seen) == ["bye", "greet"]

    def test_hook_can_replace_submit_with_a_new_signature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_job_submit(monkeypatch)

        class _CLI(_NoOpCLI):
            def update_job_cli(self, job_cls, group) -> None:
                if job_cls is not _GreetJob:
                    return
                original = next(c for c in group.registered_commands if c.name == "submit").callback
                assert original is not None

                @group.command("submit")
                def submit(
                    typer_ctx: typer.Context,
                    name: str = typer.Option(..., "--name"),
                    spec: str = typer.Option("{}", "--spec"),
                ) -> None:
                    merged = json.dumps({**json.loads(spec), "name": name})
                    original(typer_ctx, spec=merged, spec_file=None)

        app = _app_with_jobs(_GreetJob, cli=_CLI())
        help_result = runner.invoke(app, ["greet", "submit", "--help"])
        assert help_result.exit_code == 0
        assert "--name" in _plain(help_result.output)

        result = runner.invoke(app, ["greet", "submit", "--name", "Wrapped"])
        assert result.exit_code == 0
        assert json.loads(result.output) == {"submitted": {"name": "Wrapped"}}

    def test_hook_can_drop_submit(self) -> None:
        class _CLI(_NoOpCLI):
            def update_job_cli(self, job_cls, group) -> None:  # noqa: ARG002
                group.registered_commands = [c for c in group.registered_commands if c.name != "submit"]

        app = _app_with_jobs(_GreetJob, cli=_CLI())
        result = runner.invoke(app, ["greet", "--help"])
        assert result.exit_code == 0
        assert "submit" not in result.output
        assert "explain" in result.output

    def test_hook_can_add_a_verb(self) -> None:
        class _CLI(_NoOpCLI):
            def update_job_cli(self, job_cls, group) -> None:  # noqa: ARG002
                @group.command("cancel")
                def cancel() -> None:
                    typer.echo("canceled")

        app = _app_with_jobs(_GreetJob, cli=_CLI())
        help_result = runner.invoke(app, ["greet", "--help"])
        assert "cancel" in help_result.output
        result = runner.invoke(app, ["greet", "cancel"])
        assert result.exit_code == 0
        assert "canceled" in result.output

    def test_hook_dispatches_per_job(self) -> None:
        class _CLI(_NoOpCLI):
            def update_job_cli(self, job_cls, group) -> None:
                if job_cls is not _GreetJob:
                    return

                @group.command("custom")
                def custom() -> None:
                    typer.echo("greet-only")

        app = _app_with_jobs(_GreetJob, _ByeJob, cli=_CLI())
        assert "custom" in runner.invoke(app, ["greet", "--help"]).output
        assert "custom" not in runner.invoke(app, ["bye", "--help"]).output


class TestUpdateFunctionCli:
    def test_default_noop_leaves_submit_only(self) -> None:
        app = _app_with_functions(_GreetFunction, cli=_NoOpCLI())
        result = runner.invoke(app, ["greet", "--help"])

        assert result.exit_code == 0
        assert "submit" in result.output
        assert "Run locally" not in result.output

    def test_no_cli_argument_uses_default_submit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_function_submit(monkeypatch)
        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(app, ["greet", "submit", "--name", "World"])

        assert result.exit_code == 0

    def test_hook_invoked_once_per_function(self) -> None:
        seen: list[str] = []

        class _CLI(_NoOpCLI):
            def update_function_cli(self, fn_cls, group) -> None:  # noqa: ARG002
                seen.append(fn_cls.name)

        _app_with_functions(_GreetFunction, _ByeFunction, cli=_CLI())
        assert sorted(seen) == ["bye", "greet"]

    def test_hook_can_replace_submit_with_a_new_signature(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_function_submit(monkeypatch)

        class _CLI(_NoOpCLI):
            def update_function_cli(self, fn_cls, group) -> None:
                if fn_cls is not _GreetFunction:
                    return
                original = next(c for c in group.registered_commands if c.name == "submit").callback
                assert original is not None

                @group.command("submit")
                def submit(
                    typer_ctx: typer.Context,
                    nickname: str = typer.Option(..., "--nickname"),
                ) -> None:
                    spec_json = json.dumps({"name": nickname})
                    original(typer_ctx, spec=spec_json, spec_file=None, workspace="default")

        app = _app_with_functions(_GreetFunction, cli=_CLI())
        help_result = runner.invoke(app, ["greet", "submit", "--help"])
        assert help_result.exit_code == 0
        assert "--nickname" in _plain(help_result.output)

        result = runner.invoke(app, ["greet", "submit", "--nickname", "Wrapped"])
        assert result.exit_code == 0

    def test_hook_can_drop_submit(self) -> None:
        class _CLI(_NoOpCLI):
            def update_function_cli(self, fn_cls, group) -> None:  # noqa: ARG002
                group.registered_commands = [c for c in group.registered_commands if c.name != "submit"]

        app = _app_with_functions(_GreetFunction, cli=_CLI())
        result = runner.invoke(app, ["greet", "--help"])
        assert "submit" not in result.output

    def test_hook_can_add_a_verb(self) -> None:
        class _CLI(_NoOpCLI):
            def update_function_cli(self, fn_cls, group) -> None:  # noqa: ARG002
                @group.command("ping")
                def ping() -> None:
                    typer.echo("pong")

        app = _app_with_functions(_GreetFunction, cli=_CLI())
        help_result = runner.invoke(app, ["greet", "--help"])
        assert "ping" in help_result.output
        result = runner.invoke(app, ["greet", "ping"])
        assert result.exit_code == 0
        assert "pong" in result.output

    def test_hook_dispatches_per_function(self) -> None:
        class _CLI(_NoOpCLI):
            def update_function_cli(self, fn_cls, group) -> None:
                if fn_cls is not _GreetFunction:
                    return

                @group.command("custom")
                def custom() -> None:
                    typer.echo("greet-only")

        app = _app_with_functions(_GreetFunction, _ByeFunction, cli=_CLI())
        assert "custom" in runner.invoke(app, ["greet", "--help"]).output
        assert "custom" not in runner.invoke(app, ["bye", "--help"]).output
