# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for NemoCLI.update_function_cli / update_job_cli hooks.

Covers the override-by-replacement contract:
- No-op default leaves the auto-generated CLI surface unchanged.
- Hook fires once per primitive after default verb registration and
  before the sub-group is mounted.
- Override-by-replacement (Typer's last-write-wins materialization) lets
  a plugin author add, drop, or replace verbs and flags.
- Both jobs and functions are covered symmetrically.
"""

from __future__ import annotations

import json
from typing import ClassVar

import typer
from nemo_platform_plugin.cli import NemoCLI
from nemo_platform_plugin.commands import add_function_commands, add_job_commands
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.job import NemoJob
from pydantic import BaseModel
from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _GreetJob(NemoJob):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Return a greeting."

    def run(self, config: dict) -> dict:
        return {"message": f"Hello, {config.get('name', 'world')}!"}


class _ByeJob(NemoJob):
    name: ClassVar[str] = "bye"
    description: ClassVar[str] = "Return a farewell."

    def run(self, config: dict) -> dict:
        return {"message": f"Bye, {config.get('name', 'world')}!"}


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


class _ByeFunction(NemoFunction[_GreetSpec]):
    name: ClassVar[str] = "bye"
    description: ClassVar[str] = "Say bye to a name."
    spec_schema: ClassVar[type[_GreetSpec]] = _GreetSpec

    async def run(self, spec: _GreetSpec) -> _GreetResponse:
        return _GreetResponse(message=f"Bye, {spec.name}!")


class _NoOpCLI(NemoCLI):
    """Minimal NemoCLI subclass with no hook overrides."""

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


# ---------------------------------------------------------------------------
# update_job_cli
# ---------------------------------------------------------------------------


class TestUpdateJobCli:
    def test_default_noop_leaves_subcommands_unchanged(self) -> None:
        app = _app_with_jobs(_GreetJob, cli=_NoOpCLI())
        result = runner.invoke(app, ["greet", "--help"])
        assert result.exit_code == 0
        assert "submit" in result.output
        assert "explain" in result.output
        assert "run" not in result.output

    def test_no_cli_argument_means_no_hook_called(self, monkeypatch) -> None:
        # Smoke: the default no-cli path still works (backwards compat).
        monkeypatch.setattr(
            "nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote",
            lambda *_args, **_kwargs: {"id": "job-123"},
        )
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "submit", "--spec", '{"name": "X"}'])
        assert result.exit_code == 0

    def test_hook_invoked_once_per_job(self) -> None:
        seen: list[str] = []

        class _CLI(_NoOpCLI):
            def update_job_cli(self, job_cls, group) -> None:  # noqa: ARG002
                seen.append(job_cls.name)

        _app_with_jobs(_GreetJob, _ByeJob, cli=_CLI())
        assert sorted(seen) == ["bye", "greet"]

    def test_hook_can_replace_submit_with_a_new_signature(self, monkeypatch) -> None:
        captured: dict[str, object] = {}

        def _capture(_self, _job_cls, spec, **_kwargs):
            captured["spec"] = spec
            return {"id": "job-123"}

        monkeypatch.setattr("nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote", _capture)

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
                    original(
                        typer_ctx,
                        spec=merged,
                        spec_file=None,
                        options=[],
                        options_file=None,
                        profile=None,
                        cluster=None,
                        base_url=None,
                        workspace="default",
                    )

        app = _app_with_jobs(_GreetJob, cli=_CLI())

        # The new flag shows up in --help.
        help_result = runner.invoke(app, ["greet", "submit", "--help"])
        assert help_result.exit_code == 0
        assert "--name" in help_result.output

        # Invoking with --name calls wrapper -> original chain.
        result = runner.invoke(app, ["greet", "submit", "--name", "Wrapped"])
        assert result.exit_code == 0
        assert captured["spec"] == {"name": "Wrapped"}

    def test_hook_can_drop_a_verb(self) -> None:
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
        """A hook that only modifies _GreetJob leaves _ByeJob untouched."""

        class _CLI(_NoOpCLI):
            def update_job_cli(self, job_cls, group) -> None:
                if job_cls is not _GreetJob:
                    return

                @group.command("custom")
                def custom() -> None:
                    typer.echo("greet-only")

        app = _app_with_jobs(_GreetJob, _ByeJob, cli=_CLI())

        greet_help = runner.invoke(app, ["greet", "--help"])
        assert "custom" in greet_help.output

        bye_help = runner.invoke(app, ["bye", "--help"])
        assert "custom" not in bye_help.output


# ---------------------------------------------------------------------------
# update_function_cli
# ---------------------------------------------------------------------------


class TestUpdateFunctionCli:
    def test_default_noop_leaves_subcommands_unchanged(self) -> None:
        app = _app_with_functions(_GreetFunction, cli=_NoOpCLI())
        result = runner.invoke(app, ["greet", "--help"])
        assert result.exit_code == 0
        assert "submit" in result.output
        assert "run" not in result.output

    def test_no_cli_argument_means_no_hook_called(self, monkeypatch) -> None:
        def _fake_post(_url, _body, **_kwargs) -> None:
            typer.echo(json.dumps({"message": "Hello, World!"}))

        monkeypatch.setattr("nemo_platform_plugin.commands._post_function_submit", _fake_post)
        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(app, ["greet", "submit", "--name", "World"])
        assert result.exit_code == 0
        assert json.loads(result.output) == {"message": "Hello, World!"}

    def test_hook_invoked_once_per_function(self) -> None:
        seen: list[str] = []

        class _CLI(_NoOpCLI):
            def update_function_cli(self, fn_cls, group) -> None:  # noqa: ARG002
                seen.append(fn_cls.name)

        _app_with_functions(_GreetFunction, _ByeFunction, cli=_CLI())
        assert sorted(seen) == ["bye", "greet"]

    def test_hook_can_replace_submit_with_a_new_signature(self, monkeypatch) -> None:
        captured: dict[str, object] = {}

        def _fake_post(_url, body, **_kwargs) -> None:
            captured["body"] = body
            typer.echo(json.dumps({"message": f"Hello, {body['name']}!"}))

        monkeypatch.setattr("nemo_platform_plugin.commands._post_function_submit", _fake_post)

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
                    original(
                        typer_ctx,
                        spec=spec_json,
                        spec_file=None,
                        cluster=None,
                        base_url=None,
                        workspace="default",
                        request_id=None,
                    )

        app = _app_with_functions(_GreetFunction, cli=_CLI())

        help_result = runner.invoke(app, ["greet", "submit", "--help"])
        assert help_result.exit_code == 0
        assert "--nickname" in help_result.output

        result = runner.invoke(app, ["greet", "submit", "--nickname", "Wrapped"])
        assert result.exit_code == 0
        assert json.loads(result.output) == {"message": "Hello, Wrapped!"}
        assert captured["body"] == {"name": "Wrapped"}

    def test_hook_can_drop_a_verb(self) -> None:
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

        greet_help = runner.invoke(app, ["greet", "--help"])
        assert "custom" in greet_help.output

        bye_help = runner.invoke(app, ["bye", "--help"])
        assert "custom" not in bye_help.output
