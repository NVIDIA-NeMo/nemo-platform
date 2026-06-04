# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for generated NemoJob and NemoFunction CLI commands."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import httpx
import pytest
import typer
from nemo_platform_plugin.commands import add_function_commands, add_job_commands
from nemo_platform_plugin.discovery import discover, discover_manifests
from nemo_platform_plugin.function import NemoFunction
from nemo_platform_plugin.job import NemoJob
from pydantic import BaseModel
from typer.testing import CliRunner

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI escape codes from Rich/Typer output for robust matching."""
    return _ANSI_RE.sub("", text)


@pytest.fixture(autouse=True)
def clear_discovery_cache():
    discover.cache_clear()
    discover_manifests.cache_clear()
    yield
    discover.cache_clear()
    discover_manifests.cache_clear()


class _GreetJob(NemoJob):
    name = "greet"
    description = "Return a greeting."

    def run(self, config: dict) -> dict:
        return {"message": f"Hello, {config.get('name', 'world')}!"}


class _FailJob(NemoJob):
    name = "fail"
    description = "Always raises."

    def run(self, config: dict) -> dict:
        raise RuntimeError("job exploded")


runner = CliRunner()


def _app_with_jobs(*job_classes: type[NemoJob]) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    jobs = {f"plugin.{cls.name}": cls for cls in job_classes}
    add_job_commands(app, jobs)
    return app


def _patch_job_submit(monkeypatch, *, result: dict | None = None) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _capture(self, job_cls, spec, **kwargs) -> dict:  # noqa: ANN001
        del self
        captured["job_cls"] = job_cls
        captured["spec"] = spec
        captured["kwargs"] = kwargs
        return result or {"id": "job-123"}

    monkeypatch.setattr("nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote", _capture)
    return captured


class TestJobSubgroupRegistration:
    def test_registers_subgroup_for_each_job(self) -> None:
        app = _app_with_jobs(_GreetJob, _FailJob)
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "greet" in result.output
        assert "fail" in result.output
        assert "Jobs" in result.output

    def test_subgroup_lists_submit_and_explain_only(self) -> None:
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "--help"])
        plain = _plain(result.output)
        assert result.exit_code == 0
        assert "submit" in plain
        assert "explain" in plain
        assert "run" not in plain

    def test_bare_job_name_exits_non_zero_and_prints_usage(self) -> None:
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet"])
        assert result.exit_code != 0
        assert "submit" in result.output
        assert "explain" in result.output


class TestJobSubmitVerb:
    @pytest.mark.parametrize(
        ("args", "env_base_url", "context_base_url", "expected_base_url"),
        [
            (
                ["--base-url", "http://from-flag:9999", "--cluster", "configured-cluster"],
                "http://from-env:1234",
                "http://from-context:7777",
                "http://from-flag:9999",
            ),
            (
                ["--cluster", "configured-cluster"],
                "http://from-env:1234",
                "http://from-context:7777",
                "http://from-cluster:8888",
            ),
            ([], "http://from-env:1234", "http://from-context:7777", "http://from-context:7777"),
            ([], "http://from-env:1234", None, "http://from-env:1234"),
            ([], None, None, "http://localhost:8080"),
        ],
    )
    def test_submit_host_resolution_precedence(
        self,
        monkeypatch,
        args: list[str],
        env_base_url: str | None,
        context_base_url: str | None,
        expected_base_url: str,
    ) -> None:
        captured = _patch_job_submit(monkeypatch)

        class _State:
            def __init__(self, resolved_base_url: str | None) -> None:
                self._resolved_base_url = resolved_base_url

            def get_base_url(self, default: str | None = None) -> str | None:
                return self._resolved_base_url if self._resolved_base_url is not None else default

        class _FakeConfig:
            def get_config_file(self) -> SimpleNamespace:
                return SimpleNamespace(
                    clusters=[SimpleNamespace(name="configured-cluster", base_url="http://from-cluster:8888")]
                )

        if env_base_url is None:
            monkeypatch.delenv("NMP_BASE_URL", raising=False)
        else:
            monkeypatch.setenv("NMP_BASE_URL", env_base_url)
        monkeypatch.setattr("nemo_platform.config.config.Config.load", lambda: _FakeConfig())

        app = _app_with_jobs(_GreetJob)
        state = _State(context_base_url)
        result = runner.invoke(app, ["greet", "submit", *args], obj=state)

        assert result.exit_code == 0, result.output
        assert captured["kwargs"]["base_url"] == expected_base_url

    def test_submit_accepts_spec_and_spec_file(self, monkeypatch, tmp_path: Path) -> None:
        captured = _patch_job_submit(monkeypatch)
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: FromYaml\n")

        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(
            app,
            [
                "greet",
                "submit",
                "--spec",
                '{"name": "Ignored"}',
                "--spec-file",
                str(spec_file),
            ],
        )

        assert result.exit_code == 0, result.output
        assert captured["spec"] == {"name": "FromYaml"}
        assert json.loads(result.output) == {"id": "job-123"}

    def test_submit_rejects_legacy_config_alias(self, monkeypatch) -> None:
        _patch_job_submit(monkeypatch)
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "submit", "--config", "{}"])
        assert result.exit_code != 0
        assert "--config" in ((result.output or "") + (result.stderr or ""))

    def test_submit_accepts_profile_options_and_auth_headers(self, monkeypatch) -> None:
        captured = _patch_job_submit(monkeypatch)

        class _State:
            def get_sdk_context(self) -> object:
                return SimpleNamespace(
                    user=SimpleNamespace(get_client_config=lambda: {"default_headers": {"Authorization": "Bearer t"}})
                )

        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(
            app,
            [
                "greet",
                "submit",
                "--spec",
                '{"name": "Ada"}',
                "--profile",
                "research",
                "-o",
                "slurm.nodes=4",
                "--workspace",
                "team-alpha",
            ],
            obj=_State(),
        )

        assert result.exit_code == 0, result.output
        assert captured["spec"] == {"name": "Ada"}
        assert captured["kwargs"]["profile"] == "research"
        assert captured["kwargs"]["options"] == {"slurm": {"nodes": "4"}}
        assert captured["kwargs"]["workspace"] == "team-alpha"
        assert captured["kwargs"]["headers"] == {"Authorization": "Bearer t"}

    def test_submit_malformed_options_file_exits_cleanly(self, tmp_path: Path) -> None:
        scalar_file = tmp_path / "opts.yaml"
        scalar_file.write_text("just-a-string")
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "submit", "--options-file", str(scalar_file)])
        assert result.exit_code != 0
        combined = (result.output or "") + (result.stderr or "")
        assert "top-level mapping" in combined

    def test_submit_returns_exit_code_2_on_connect_error(self, monkeypatch) -> None:
        request = httpx.Request("POST", "http://test/apis/tests/v2/workspaces/default/jobs/greet")

        def _raise_connect(*_args, **_kwargs) -> dict:
            raise httpx.ConnectError("Connection refused", request=request)

        monkeypatch.setattr("nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote", _raise_connect)

        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "submit", "--base-url", "http://test"])

        assert result.exit_code == 2
        combined = (result.output or "") + (result.stderr or "")
        assert "Connection refused" in combined
        assert "Request: POST http://test/apis/tests/v2/workspaces/default/jobs/greet" in combined
        assert "Target: tests API route /apis/tests/v2/workspaces/default/jobs/greet" in combined
        assert "Traceback" not in combined

    def test_submit_help_lists_expected_flags(self) -> None:
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "submit", "--help"])
        output = _plain(result.output)
        assert result.exit_code == 0
        assert "--spec" in output
        assert "--spec-file" in output
        assert "--profile" in output
        assert "--cluster" in output
        assert "--base-url" in output
        assert "--workspace" in output
        assert "-o" in output
        assert "--options-file" in output
        assert "--config" not in output


class TestJobExplainVerb:
    def test_explain_works_without_cluster(self) -> None:
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "explain"])
        assert result.exit_code == 0
        bundle = json.loads(result.output)
        assert "{workspace}" in bundle["endpoint"]
        assert bundle["endpoint"].endswith("/jobs/greet")
        assert bundle["profile"] is None
        assert bundle["profile_providers"] == []
        assert bundle["options"] == {}

    def test_explain_annotates_with_profile(self) -> None:
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "explain", "--profile", "research"])
        assert result.exit_code == 0
        bundle = json.loads(result.output)
        assert bundle["profile"] == "research"


class _GreetSpec(BaseModel):
    name: str


class _GreetResponse(BaseModel):
    message: str


class _GreetFunction(NemoFunction[_GreetSpec]):
    name: ClassVar[str] = "greet"
    description: ClassVar[str] = "Say hello to a name."
    spec_schema: ClassVar[type[BaseModel]] = _GreetSpec

    async def run(self, spec: _GreetSpec) -> _GreetResponse:
        return _GreetResponse(message=f"Hello, {spec.name}!")


class _CountSpec(BaseModel):
    upto: int


class _CountFunction(NemoFunction[_CountSpec]):
    name: ClassVar[str] = "count"
    spec_schema: ClassVar[type[BaseModel]] = _CountSpec

    async def run(self, spec: _CountSpec) -> dict:
        return {"upto": spec.upto}


def _app_with_functions(*function_classes: type[NemoFunction]) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def _noop() -> None:
        pass

    fns = {f"plugin.{cls.name}": cls for cls in function_classes}
    add_function_commands(app, fns)
    return app


class TestFunctionSubgroupRegistration:
    def test_registers_submit_only(self) -> None:
        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(app, ["greet", "--help"])
        plain = _plain(result.output)
        assert result.exit_code == 0
        assert "submit" in plain
        assert "run" not in plain
        assert "explain" not in plain

    def test_bare_function_name_exits_non_zero(self) -> None:
        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(app, ["greet"])
        assert result.exit_code != 0
        assert "submit" in result.output


class TestFunctionSubmitVerb:
    def test_submit_help_lists_expected_flags(self) -> None:
        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(app, ["greet", "submit", "--help"])
        output = _plain(result.output)
        assert result.exit_code == 0
        assert "--spec" in output
        assert "--spec-file" in output
        assert "--cluster" in output
        assert "--base-url" in output
        assert "--workspace" in output
        assert "--request-id" in output
        assert "--profile" not in output

    def test_submit_invalid_spec_exits_before_network(self, monkeypatch) -> None:
        called: list[bool] = []

        def _fail(*_args, **_kwargs) -> None:
            called.append(True)
            raise AssertionError("HTTP layer must not be reached for invalid spec")

        monkeypatch.setattr("nemo_platform_plugin.commands._post_function_submit", _fail)

        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(app, ["greet", "submit", "--spec", "{}"])
        assert result.exit_code == 1
        assert called == []

    def test_submit_posts_to_canonical_url_and_prints_json(self, monkeypatch) -> None:
        captured_url: list[str] = []
        captured_body: list[dict] = []
        captured_headers: list[dict[str, str]] = []

        def _fake_post(url: str, body: dict, *, headers: dict, timeout: float = 30.0, **_kwargs) -> None:
            captured_url.append(url)
            captured_body.append(body)
            captured_headers.append(dict(headers))
            del timeout
            typer.echo(json.dumps({"message": "ok"}))

        monkeypatch.setattr("nemo_platform_plugin.commands._post_function_submit", _fake_post)

        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(
            app,
            [
                "greet",
                "submit",
                "--name",
                "Ada",
                "--base-url",
                "http://my-platform:9090",
                "--workspace",
                "team-alpha",
                "--request-id",
                "req-42",
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured_url[0].endswith("/v2/workspaces/team-alpha/greet")
        assert "/apis/" in captured_url[0]
        assert captured_body[0] == {"name": "Ada"}
        assert captured_headers[0]["X-Request-ID"] == "req-42"

    def test_submit_streams_ndjson_lines(self, monkeypatch) -> None:
        ndjson_body = json.dumps({"kind": "heartbeat"}) + "\n" + json.dumps({"kind": "done"}) + "\n"

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

        app = _app_with_functions(_CountFunction)
        result = runner.invoke(
            app,
            ["count", "submit", "--upto", "1", "--base-url", "http://test"],
        )
        assert result.exit_code == 0, result.output
        lines = [line for line in result.output.splitlines() if line.strip()]
        kinds = [json.loads(line)["kind"] for line in lines]
        assert kinds == ["heartbeat", "done"]

    def test_submit_returns_exit_code_2_on_http_error(self, monkeypatch) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                500,
                headers={"content-type": "application/json"},
                stream=httpx.ByteStream(b'{"detail": "boom"}'),
            )

        transport = httpx.MockTransport(_handler)
        original_client = httpx.Client

        def _client_factory(*args, **kwargs):
            kwargs.setdefault("transport", transport)
            return original_client(*args, **kwargs)

        monkeypatch.setattr("nemo_platform_plugin.commands.httpx.Client", _client_factory)

        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(
            app,
            ["greet", "submit", "--name", "x", "--base-url", "http://test"],
        )
        assert result.exit_code == 2
        combined = (result.output or "") + (result.stderr or "")
        assert "500" in combined
        assert "boom" in combined
        assert "Request: POST http://test/" in combined


class TestApiSegmentForFunction:
    def test_uses_registered_entry_point_key(self, monkeypatch) -> None:
        from nemo_platform_plugin.commands import _api_segment_for_function

        class _Spec(BaseModel):
            pass

        class _Fn(NemoFunction[_Spec]):
            name: ClassVar[str] = "greet"
            spec_schema: ClassVar[type[BaseModel]] = _Spec

            async def run(self, spec: _Spec) -> dict:
                del spec
                return {}

        _Fn.__module__ = "nemo_my_plugin.functions.greet"
        monkeypatch.setattr(
            "nemo_platform_plugin.discovery.discover_functions",
            lambda: {"my-plugin.greet": _Fn},
        )
        assert _api_segment_for_function(_Fn) == "my-plugin"

    def test_falls_back_to_module_when_not_registered(self, monkeypatch) -> None:
        from nemo_platform_plugin.commands import _api_segment_for_function

        class _Spec(BaseModel):
            pass

        class _Fn(NemoFunction[_Spec]):
            name: ClassVar[str] = "greet"
            spec_schema: ClassVar[type[BaseModel]] = _Spec

            async def run(self, spec: _Spec) -> dict:
                del spec
                return {}

        _Fn.__module__ = "nemo_example_plugin.functions.greet"
        monkeypatch.setattr("nemo_platform_plugin.discovery.discover_functions", lambda: {})
        assert _api_segment_for_function(_Fn) == "example-plugin"


class _NestedTarget(BaseModel):
    url: str
    timeout_seconds: int = 30


class _NestedSpec(BaseModel):
    name: str
    target: _NestedTarget


class _NestedFunction(NemoFunction[_NestedSpec]):
    name: ClassVar[str] = "ping"
    description: ClassVar[str] = "Ping a nested target."
    spec_schema: ClassVar[type[BaseModel]] = _NestedSpec

    async def run(self, spec: _NestedSpec) -> dict:
        return {
            "name": spec.name,
            "url": spec.target.url,
            "timeout": spec.target.timeout_seconds,
        }


class TestFunctionAutoSpecFlags:
    def test_submit_help_lists_one_flag_per_scalar_leaf(self) -> None:
        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(app, ["greet", "submit", "--help"])
        plain = _plain(result.output)
        assert result.exit_code == 0
        assert "--name" in plain
        assert "Function Spec" in plain
        assert "GreetSpec" in plain

    def test_nested_field_uses_dotted_flag_name(self) -> None:
        app = _app_with_functions(_NestedFunction)
        result = runner.invoke(app, ["ping", "submit", "--help"])
        plain = _plain(result.output)
        assert result.exit_code == 0
        assert "--name" in plain
        assert "--target.url" in plain
        assert "--target.timeout-seconds" in plain

    def test_per_field_flag_overlays_on_top_of_spec(self, monkeypatch) -> None:
        captured_body: list[dict] = []

        def _fake_post(url: str, body: dict, *, headers: dict, timeout: float = 30.0, **_kwargs) -> None:
            del url, headers, timeout
            captured_body.append(body)

        monkeypatch.setattr("nemo_platform_plugin.commands._post_function_submit", _fake_post)

        app = _app_with_functions(_GreetFunction)
        result = runner.invoke(
            app,
            ["greet", "submit", "--spec", '{"name": "from-spec"}', "--name", "from-flag"],
        )
        assert result.exit_code == 0, result.output
        assert captured_body == [{"name": "from-flag"}]

    def test_workspace_field_in_spec_does_not_collide_with_static_flag(self, monkeypatch) -> None:
        class _ConfusingSpec(BaseModel):
            workspace: str = "default-ws"

        class _ConfusingFunction(NemoFunction[_ConfusingSpec]):
            name: ClassVar[str] = "confuse"
            spec_schema: ClassVar[type[BaseModel]] = _ConfusingSpec

            async def run(self, spec: _ConfusingSpec) -> dict:
                return {"in_spec": spec.workspace}

        captured_body: list[dict] = []

        def _fake_post(url: str, body: dict, *, headers: dict, timeout: float = 30.0, **_kwargs) -> None:
            del url, headers, timeout
            captured_body.append(body)

        monkeypatch.setattr("nemo_platform_plugin.commands._post_function_submit", _fake_post)

        app = _app_with_functions(_ConfusingFunction)
        help_result = runner.invoke(app, ["confuse", "submit", "--help"])
        plain = _plain(help_result.output)
        assert plain.count("--workspace") == 1

        submit_result = runner.invoke(
            app,
            ["confuse", "submit", "--spec", '{"workspace": "from-spec"}', "--workspace", "ctx-ws"],
        )
        assert submit_result.exit_code == 0, submit_result.output
        assert captured_body == [{"workspace": "from-spec"}]


class _GreetJobSpec(BaseModel):
    name: str = "world"
    loud: bool = False


class _GreetSpecJob(NemoJob):
    name = "greet-spec"
    description = "Return a greeting validated against a schema."
    spec_schema: ClassVar[type[BaseModel]] = _GreetJobSpec

    def run(self, config: dict) -> dict:
        spec = _GreetJobSpec.model_validate(config)
        message = f"Hello, {spec.name}!"
        if spec.loud:
            message = message.upper()
        return {"message": message}


class _NestedJobTarget(BaseModel):
    url: str
    timeout_seconds: int = 30


class _NestedJobSpec(BaseModel):
    name: str
    target: _NestedJobTarget


class _NestedSpecJob(NemoJob):
    name = "ping-spec"
    description = "Ping a nested target."
    spec_schema: ClassVar[type[BaseModel]] = _NestedJobSpec

    def run(self, config: dict) -> dict:
        spec = _NestedJobSpec.model_validate(config)
        return {
            "name": spec.name,
            "url": spec.target.url,
            "timeout": spec.target.timeout_seconds,
        }


class TestJobAutoSpecFlags:
    def test_submit_help_lists_one_flag_per_scalar_leaf(self) -> None:
        app = _app_with_jobs(_GreetSpecJob)
        result = runner.invoke(app, ["greet-spec", "submit", "--help"])
        plain = _plain(result.output)
        assert result.exit_code == 0
        assert "--name" in plain
        assert "--loud" in plain
        assert "Job Spec" in plain

    def test_nested_field_uses_dotted_flag_name(self) -> None:
        app = _app_with_jobs(_NestedSpecJob)
        result = runner.invoke(app, ["ping-spec", "submit", "--help"])
        plain = _plain(result.output)
        assert result.exit_code == 0
        assert "--name" in plain
        assert "--target.url" in plain
        assert "--target.timeout-seconds" in plain

    def test_per_field_flag_overlays_on_top_of_spec(self, monkeypatch) -> None:
        captured = _patch_job_submit(monkeypatch)

        app = _app_with_jobs(_GreetSpecJob)
        result = runner.invoke(
            app,
            [
                "greet-spec",
                "submit",
                "--spec",
                '{"name": "from-spec", "loud": true}',
                "--name",
                "from-flag",
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured["spec"] == {"name": "from-flag", "loud": True}

    def test_no_spec_schema_renders_only_static_panels(self) -> None:
        app = _app_with_jobs(_GreetJob)
        result = runner.invoke(app, ["greet", "submit", "--help"])
        plain = _plain(result.output)
        assert "Job Spec" not in plain
        assert "Spec Source" in plain

    def test_input_spec_schema_drives_auto_flags_when_declared(self) -> None:
        class _InputShape(BaseModel):
            target_name: str

        class _CanonicalShape(BaseModel):
            resolved_id: str

        class _TwoShapeJob(NemoJob):
            name = "two-shape"
            input_spec_schema: ClassVar[type[BaseModel]] = _InputShape
            spec_schema: ClassVar[type[BaseModel]] = _CanonicalShape

            def run(self, config: dict) -> dict:
                return {"got": config}

        app = _app_with_jobs(_TwoShapeJob)
        result = runner.invoke(app, ["two-shape", "submit", "--help"])
        plain = _plain(result.output)
        assert "--target-name" in plain
        assert "--resolved-id" not in plain
