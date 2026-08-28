# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import json
import tarfile
from io import StringIO
from pathlib import Path
from typing import Any, ClassVar, cast
from unittest.mock import Mock

import typer
import yaml
from nemo_anonymizer_plugin import cli as cli_module
from nemo_anonymizer_plugin import cli_files as cli_files_module
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest
from nemo_anonymizer_plugin.cli import AnonymizerCLI
from nemo_anonymizer_plugin.functions.preview import PreviewDatasetFrame, PreviewFunction
from nemo_platform_plugin.cli_renderer import CLIRenderer, RendererContext
from nemo_platform_plugin.commands import add_function_commands, add_job_commands
from nemo_platform_plugin.functions.frames import Done, Error, FrameModel
from nemo_platform_plugin.job import NemoJob
from rich.console import Console
from typer.testing import CliRunner


class _AnonymizerRunJob(NemoJob):
    name: ClassVar[str] = "run"
    description: ClassVar[str] = "Run anonymizer test job."
    generate_legacy_verbs: ClassVar[bool] = False
    input_spec_schema = AnonymizerRequest
    spec_schema = AnonymizerRequest

    def run(self, config: dict) -> dict:
        return {"config": config}


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "replace": {
                    "kind": "redact",
                    "format_template": "[REDACTED_{label}]",
                }
            }
        )
    )


def _write_preview_request(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "config": {
                    "replace": {
                        "kind": "redact",
                        "format_template": "[REDACTED_{label}]",
                    }
                },
                "data": {
                    "source": "https://example.test/input.csv",
                    "text_column": "text",
                },
                "num_records": 2,
            }
        )
    )


def _write_anonymizer_request(path: Path, *, source: str) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "config": {
                    "replace": {
                        "kind": "redact",
                        "format_template": "[REDACTED_{label}]",
                    }
                },
                "data": {
                    "source": source,
                    "text_column": "text",
                },
            }
        )
    )


def _app_with_preview_function(monkeypatch) -> typer.Typer:
    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_functions",
        lambda: {"anonymizer.preview": PreviewFunction},
    )
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_function_commands(app, {"anonymizer.preview": PreviewFunction}, cli=cli)
    return app


def _patch_preview_submit(monkeypatch, frames: list[FrameModel]) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_post(
        url: str,
        body: dict,
        *,
        headers: dict[str, str],
        timeout: float = 30.0,
        renderer_cls: type[CLIRenderer] | None = None,
        cli_kwargs: dict[str, Any] | None = None,
    ) -> None:
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["cli_kwargs"] = cli_kwargs
        assert renderer_cls is not None
        renderer = renderer_cls()
        ctx = RendererContext(
            console=Console(file=StringIO()),
            cli_kwargs=cli_kwargs or {},
            verb="submit",
            is_local=False,
        )
        renderer.on_start(ctx=ctx)
        try:
            for frame in frames:
                renderer.on_frame(frame.model_dump(mode="json", exclude_none=True), ctx=ctx)
            renderer.on_complete(ctx=ctx)
        except BaseException as exc:
            renderer.on_error(exc, ctx=ctx)
            raise

    monkeypatch.setattr("nemo_platform_plugin.commands._post_function_submit", fake_post)
    return captured


def test_cli_registers_validate_command() -> None:
    result = CliRunner().invoke(AnonymizerCLI().get_cli(), ["--help"])

    assert result.exit_code == 0, result.output
    assert "validate" in result.output


def test_preview_command_help_does_not_expose_watch(monkeypatch) -> None:
    result = CliRunner().invoke(_app_with_preview_function(monkeypatch), ["preview", "--help"])

    assert result.exit_code == 0, result.output
    assert "--fileset" in result.output
    assert "--input-remote-path" in result.output
    assert "--output-remote-path" in result.output
    assert "--quiet" in result.output
    assert "--output-file" in result.output
    assert "--watch" not in result.output


def test_preview_command_does_not_accept_legacy_nested_verbs(monkeypatch) -> None:
    runner = CliRunner()
    app = _app_with_preview_function(monkeypatch)

    run_result = runner.invoke(app, ["preview", "run", "--spec", "{}"])
    submit_result = runner.invoke(app, ["preview", "submit", "--spec", "{}"])

    assert run_result.exit_code == 2
    assert "unexpected extra argument" in run_result.output
    assert submit_result.exit_code == 2
    assert "unexpected extra argument" in submit_result.output


def _load_json_documents(output: str) -> list[object]:
    decoder = json.JSONDecoder()
    remaining = output.strip()
    documents: list[object] = []
    while remaining:
        document, index = decoder.raw_decode(remaining)
        documents.append(document)
        remaining = remaining[index:].strip()
    return documents


def test_anonymizer_run_help_exposes_files_options_without_output_location() -> None:
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)

    result = CliRunner().invoke(app, ["run", "--help"])

    assert result.exit_code == 0, result.output
    assert "[COMMAND]" not in result.output
    assert "--fileset" in result.output
    assert "--input-remote-path" in result.output
    assert "--output-dir" in result.output
    assert "--verbose" in result.output
    assert "--print-request" not in result.output
    assert "--output-location" not in result.output


def test_anonymizer_run_command_does_not_accept_legacy_nested_verbs() -> None:
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)

    run_result = CliRunner().invoke(app, ["run", "run", "--spec", "{}"])
    submit_result = CliRunner().invoke(app, ["run", "submit", "--spec", "{}"])

    assert run_result.exit_code == 2
    assert "unexpected extra argument" in run_result.output
    assert submit_result.exit_code == 2
    assert "unexpected extra argument" in submit_result.output


def test_anonymizer_run_delegates_to_generated_job_submit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    spec_file = tmp_path / "run.yaml"
    _write_anonymizer_request(spec_file, source="https://example.test/input.csv")
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)
    captured: dict[str, object] = {}

    def fake_submit_remote(self, job_cls, spec, **kwargs):
        captured["job_cls"] = job_cls
        captured["spec"] = spec
        captured["kwargs"] = kwargs
        return {"name": "anon-job-1", "workspace": "team-a"}

    monkeypatch.setattr("nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote", fake_submit_remote)

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--spec-file",
            str(spec_file),
            "--workspace",
            "team-a",
            "--base-url",
            "http://platform.example",
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"name": "anon-job-1", "workspace": "team-a"}
    assert captured["job_cls"] is _AnonymizerRunJob
    spec = cast(dict[str, Any], captured["spec"])
    assert spec["data"]["source"] == "https://example.test/input.csv"
    assert captured["kwargs"] == {
        "base_url": "http://platform.example",
        "workspace": "team-a",
        "profile": None,
        "options": None,
        "metadata": None,
        "headers": None,
    }


def test_anonymizer_run_uploads_local_input_and_maps_fileset_to_output_location(
    tmp_path: Path,
    monkeypatch,
) -> None:
    local_input = tmp_path / "input.csv"
    local_input.write_text("text\nAlice met Bob\n")
    spec_file = tmp_path / "run.yaml"
    _write_anonymizer_request(spec_file, source=str(local_input))
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)
    captured: dict[str, object] = {"ensured": [], "uploads": []}
    platform_client = object()

    def fake_make_platform_client(**kwargs: object) -> object:
        captured["platform_kwargs"] = kwargs
        return platform_client

    def fake_ensure(platform: object, *, workspace: str, fileset: str) -> None:
        assert platform is platform_client
        cast(list[tuple[str, str]], captured["ensured"]).append((workspace, fileset))

    def fake_upload(
        platform: object,
        *,
        local_path: Path,
        remote_path: str,
        fileset: str,
        workspace: str,
        description: str,
        quiet: bool = False,
    ) -> None:
        assert platform is platform_client
        cast(list[dict[str, object]], captured["uploads"]).append(
            {
                "local_path": local_path,
                "remote_path": remote_path,
                "fileset": fileset,
                "workspace": workspace,
                "description": description,
                "quiet": quiet,
            }
        )

    def fake_submit_remote(self, job_cls, spec, **kwargs):
        captured["job_cls"] = job_cls
        captured["spec"] = spec
        captured["kwargs"] = kwargs
        return {"name": "anon-job-1", "workspace": "team-a"}

    monkeypatch.setattr(cli_files_module, "make_platform_client", fake_make_platform_client)
    monkeypatch.setattr(cli_files_module, "ensure_fileset_exists", fake_ensure)
    monkeypatch.setattr(cli_files_module, "upload_file_to_fileset", fake_upload)
    monkeypatch.setattr(
        "nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote",
        fake_submit_remote,
    )

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--spec-file",
            str(spec_file),
            "--fileset",
            "anonymizer-inputs",
            "--input-remote-path",
            "inputs/input.csv",
            "--workspace",
            "team-a",
            "--base-url",
            "http://platform.example",
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    assert captured["platform_kwargs"] == {
        "base_url": "http://platform.example",
        "workspace": "team-a",
        "headers": {},
    }
    assert captured["ensured"] == [("team-a", "anonymizer-inputs")]
    assert captured["uploads"] == [
        {
            "local_path": local_input,
            "remote_path": "inputs/input.csv",
            "fileset": "anonymizer-inputs",
            "workspace": "team-a",
            "description": "local input",
            "quiet": False,
        }
    ]
    assert captured["job_cls"] is _AnonymizerRunJob
    spec = cast(dict[str, Any], captured["spec"])
    assert spec["data"]["source"] == "team-a/anonymizer-inputs#inputs/input.csv"
    assert captured["kwargs"] == {
        "base_url": "http://platform.example",
        "workspace": "team-a",
        "profile": None,
        "options": None,
        "metadata": {"output_location": "anonymizer-inputs"},
        "headers": None,
    }


def test_anonymizer_run_verbose_outputs_submit_payload_then_submits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    spec_file = tmp_path / "run.yaml"
    _write_anonymizer_request(spec_file, source="https://example.test/input.csv")
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)
    captured: dict[str, object] = {}

    def fake_build_submit_url(self, job_cls, *, base_url, workspace):
        assert job_cls is _AnonymizerRunJob
        return f"{base_url.rstrip('/')}/submit/{workspace}"

    def fake_build_submit_body(self, spec, *, profile, options, metadata):
        assert metadata is None
        return {"spec": spec, "profile": profile, "options": options}

    def fake_submit_remote(self, job_cls, spec, **kwargs):
        captured["job_cls"] = job_cls
        captured["spec"] = spec
        captured["kwargs"] = kwargs
        return {"name": "anon-job-1", "workspace": "team-a"}

    monkeypatch.setattr(
        "nemo_platform_plugin.scheduler.NemoJobScheduler._build_submit_url",
        fake_build_submit_url,
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.scheduler.NemoJobScheduler._build_submit_body",
        fake_build_submit_body,
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote",
        fake_submit_remote,
    )

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--spec-file",
            str(spec_file),
            "--workspace",
            "team-a",
            "--base-url",
            "http://platform.example",
            "--profile",
            "gpu",
            "--verbose",
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    documents = _load_json_documents(result.output)
    schema_document = cast(dict[str, Any], documents[0])
    request_document = cast(dict[str, Any], documents[1])
    job_document = documents[2]
    assert schema_document["profile"] == "gpu"
    assert schema_document["input_spec_schema"]["title"] == "AnonymizerRequest"
    assert request_document["method"] == "POST"
    assert request_document["url"] == "http://platform.example/submit/team-a"
    assert request_document["body"]["profile"] == "gpu"
    assert request_document["body"]["options"] is None
    assert request_document["body"]["spec"]["data"] == {
        "source": "https://example.test/input.csv",
        "text_column": "text",
    }
    assert request_document["body"]["spec"]["config"]["replace"] == {
        "kind": "redact",
        "format_template": "[REDACTED_{label}]",
        "normalize_label": True,
    }
    assert job_document == {"name": "anon-job-1", "workspace": "team-a"}
    assert captured["job_cls"] is _AnonymizerRunJob
    assert captured["kwargs"] == {
        "base_url": "http://platform.example",
        "workspace": "team-a",
        "profile": "gpu",
        "options": None,
        "metadata": None,
        "headers": None,
    }


def test_anonymizer_run_dry_run_rewrites_local_input_without_uploading(
    tmp_path: Path,
    monkeypatch,
) -> None:
    local_input = tmp_path / "input.csv"
    local_input.write_text("text\nAlice met Bob\n")
    spec_file = tmp_path / "run.yaml"
    _write_anonymizer_request(spec_file, source=str(local_input))
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)
    monkeypatch.setattr(cli_files_module, "make_platform_client", Mock(side_effect=AssertionError("no client")))
    monkeypatch.setattr(cli_files_module, "ensure_fileset_exists", Mock(side_effect=AssertionError("no create")))
    monkeypatch.setattr(cli_files_module, "upload_file_to_fileset", Mock(side_effect=AssertionError("no upload")))

    def fake_build_submit_url(self, job_cls, *, base_url, workspace):
        assert job_cls is _AnonymizerRunJob
        return f"{base_url.rstrip('/')}/submit/{workspace}"

    monkeypatch.setattr(
        "nemo_platform_plugin.scheduler.NemoJobScheduler._build_submit_url",
        fake_build_submit_url,
    )

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--spec-file",
            str(spec_file),
            "--fileset",
            "anonymizer-inputs",
            "--workspace",
            "team-a",
            "--base-url",
            "http://platform.example",
            "--dry-run",
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    documents = _load_json_documents(result.output)
    schema_document = cast(dict[str, Any], documents[0])
    request_document = cast(dict[str, Any], documents[1])
    assert schema_document["input_spec_schema"]["title"] == "AnonymizerRequest"
    body = request_document["body"]
    assert body["spec"]["data"]["source"] == "team-a/anonymizer-inputs#input.csv"
    assert body["output_location"] == "anonymizer-inputs"


def test_anonymizer_run_output_dir_requires_watch(tmp_path: Path) -> None:
    spec_file = tmp_path / "run.yaml"
    _write_anonymizer_request(spec_file, source="https://example.test/input.csv")
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--spec-file",
            str(spec_file),
            "--base-url",
            "http://platform.example",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 2
    assert "--output-dir requires --watch" in result.output


def test_anonymizer_run_downloads_artifacts_after_successful_watch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    spec_file = tmp_path / "run.yaml"
    _write_anonymizer_request(spec_file, source="https://example.test/input.csv")
    cli = AnonymizerCLI()
    app = cli.get_cli()
    add_job_commands(app, {"anonymizer.run": _AnonymizerRunJob}, cli=cli)
    platform_client = object()
    jobs_client = Mock()
    events = object()
    jobs_client.watch_job.return_value = events
    captured: dict[str, object] = {}

    def fake_client_from_platform(platform: object, client_type: object) -> object:
        assert platform is platform_client
        assert client_type is cli_module.JobsClient
        return jobs_client

    def fake_download(url: str, *, headers: dict[str, str], output_dir: Path) -> None:
        captured["download"] = {
            "url": url,
            "headers": headers,
            "output_dir": output_dir,
        }

    def fake_submit_remote(self, job_cls, spec, **kwargs):
        captured["job_cls"] = job_cls
        captured["spec"] = spec
        captured["kwargs"] = kwargs
        return {"name": "anon-job-1", "workspace": "team-a"}

    monkeypatch.setattr(cli_files_module, "make_platform_client", Mock(return_value=platform_client))
    monkeypatch.setattr(cli_module, "client_from_platform", fake_client_from_platform)
    monkeypatch.setattr("nemo_platform_plugin.scheduler.NemoJobScheduler.submit_remote", fake_submit_remote)
    monkeypatch.setattr(cli_module, "render_job_watch_events", Mock(return_value=True))
    monkeypatch.setattr(cli_module, "_download_run_artifacts", fake_download)

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    output_dir = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--spec-file",
            str(spec_file),
            "--base-url",
            "http://platform.example",
            "--workspace",
            "team-a",
            "--watch",
            "--output-dir",
            str(output_dir),
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    assert captured["job_cls"] is _AnonymizerRunJob
    assert captured["kwargs"] == {
        "base_url": "http://platform.example",
        "workspace": "team-a",
        "profile": None,
        "options": None,
        "metadata": None,
        "headers": None,
    }
    jobs_client.watch_job.assert_called_once_with(
        "anon-job-1",
        workspace="team-a",
        timeout=None,
        poll_interval=3,
        include_history=True,
    )
    assert captured["download"] == {
        "url": "http://platform.example/apis/anonymizer/v2/workspaces/team-a/jobs/run/anon-job-1/results/artifacts/download",
        "headers": {},
        "output_dir": output_dir,
    }


def test_preview_command_delegates_to_function_submit(tmp_path: Path, monkeypatch) -> None:
    spec_file = tmp_path / "preview.yaml"
    _write_preview_request(spec_file)
    captured: dict[str, object] = {}
    platform_client = object()
    output_file = tmp_path / "preview.ndjson"
    submit_capture = _patch_preview_submit(monkeypatch, [PreviewDatasetFrame(records=[]), Done()])

    def fake_make_platform_client(**kwargs: object) -> object:
        captured["platform_kwargs"] = kwargs
        return platform_client

    monkeypatch.setattr(cli_files_module, "make_platform_client", fake_make_platform_client)

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    result = CliRunner().invoke(
        _app_with_preview_function(monkeypatch),
        [
            "preview",
            "--spec-file",
            str(spec_file),
            "--base-url",
            "http://platform.example/",
            "--workspace",
            "team/a",
            "--request-id",
            "req-1",
            "--quiet",
            "--output-file",
            str(output_file),
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    assert captured["platform_kwargs"] == {
        "base_url": "http://platform.example/",
        "workspace": "team/a",
        "headers": {"X-Request-ID": "req-1"},
    }
    assert str(submit_capture["url"]).endswith("/apis/anonymizer/v2/workspaces/team/a/preview")
    assert submit_capture["headers"] == {"X-Request-ID": "req-1"}
    body = cast(dict[str, object], submit_capture["body"])
    config = cast(dict[str, object], body["config"])
    replace = cast(dict[str, object], config["replace"])
    assert replace["kind"] == "redact"
    assert replace["format_template"] == "[REDACTED_{label}]"
    assert body["data"] == {
        "source": "https://example.test/input.csv",
        "text_column": "text",
    }
    assert body["num_records"] == 2
    assert [json.loads(line) for line in output_file.read_text().splitlines()] == [
        {
            "kind": "preview_dataset",
            "records": [],
        },
        {"kind": "done"},
    ]


def test_preview_command_num_records_overrides_spec(tmp_path: Path, monkeypatch) -> None:
    spec_file = tmp_path / "preview.yaml"
    _write_preview_request(spec_file)
    submit_capture = _patch_preview_submit(monkeypatch, [PreviewDatasetFrame(records=[]), Done()])

    result = CliRunner().invoke(
        _app_with_preview_function(monkeypatch),
        [
            "preview",
            "--spec-file",
            str(spec_file),
            "--base-url",
            "http://platform.example/",
            "--num-records",
            "4",
        ],
    )

    assert result.exit_code == 0, result.output
    assert cast(dict[str, object], submit_capture["body"])["num_records"] == 4


def test_preview_command_uploads_local_input_before_streaming(tmp_path: Path, monkeypatch) -> None:
    local_input = tmp_path / "input.csv"
    local_input.write_text("text\nAlice met Bob\n")
    spec_file = tmp_path / "preview.yaml"
    _write_anonymizer_request(spec_file, source=str(local_input))
    captured: dict[str, object] = {"ensured": [], "uploads": []}
    platform_client = object()
    submit_capture = _patch_preview_submit(monkeypatch, [PreviewDatasetFrame(records=[]), Done()])

    def fake_make_platform_client(**kwargs: object) -> object:
        captured["platform_kwargs"] = kwargs
        return platform_client

    def fake_ensure(platform: object, *, workspace: str, fileset: str) -> None:
        assert platform is platform_client
        cast(list[tuple[str, str]], captured["ensured"]).append((workspace, fileset))

    def fake_upload(
        platform: object,
        *,
        local_path: Path,
        remote_path: str,
        fileset: str,
        workspace: str,
        description: str,
        quiet: bool = False,
    ) -> None:
        assert platform is platform_client
        cast(list[dict[str, object]], captured["uploads"]).append(
            {
                "local_path": local_path,
                "remote_path": remote_path,
                "fileset": fileset,
                "workspace": workspace,
                "description": description,
                "quiet": quiet,
            }
        )

    monkeypatch.setattr(cli_files_module, "make_platform_client", fake_make_platform_client)
    monkeypatch.setattr(cli_files_module, "ensure_fileset_exists", fake_ensure)
    monkeypatch.setattr(cli_files_module, "upload_file_to_fileset", fake_upload)

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    result = CliRunner().invoke(
        _app_with_preview_function(monkeypatch),
        [
            "preview",
            "--spec-file",
            str(spec_file),
            "--fileset",
            "anonymizer-inputs",
            "--input-remote-path",
            "inputs/input.csv",
            "--workspace",
            "team-a",
            "--base-url",
            "http://platform.example",
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    assert captured["platform_kwargs"] == {
        "base_url": "http://platform.example",
        "workspace": "team-a",
        "headers": {},
    }
    assert captured["ensured"] == [("team-a", "anonymizer-inputs")]
    assert captured["uploads"] == [
        {
            "local_path": local_input,
            "remote_path": "inputs/input.csv",
            "fileset": "anonymizer-inputs",
            "workspace": "team-a",
            "description": "local input",
            "quiet": False,
        }
    ]
    assert cast(dict[str, object], cast(dict[str, object], submit_capture["body"])["data"])["source"] == (
        "team-a/anonymizer-inputs#inputs/input.csv"
    )


def test_preview_command_local_input_requires_fileset(tmp_path: Path, monkeypatch) -> None:
    local_input = tmp_path / "input.csv"
    local_input.write_text("text\nAlice met Bob\n")
    spec_file = tmp_path / "preview.yaml"
    _write_anonymizer_request(spec_file, source=str(local_input))

    result = CliRunner().invoke(
        _app_with_preview_function(monkeypatch),
        [
            "preview",
            "--spec-file",
            str(spec_file),
            "--base-url",
            "http://platform.example",
        ],
    )

    assert result.exit_code == 2
    assert "Local input sources require --fileset" in result.output


def test_preview_command_uploads_output_remote_path(tmp_path: Path, monkeypatch) -> None:
    spec_file = tmp_path / "preview.yaml"
    _write_preview_request(spec_file)
    captured: dict[str, object] = {"ensured": [], "uploads": []}
    platform_client = object()
    _patch_preview_submit(monkeypatch, [PreviewDatasetFrame(records=[]), Done()])

    def fake_ensure(platform: object, *, workspace: str, fileset: str) -> None:
        assert platform is platform_client
        cast(list[tuple[str, str]], captured["ensured"]).append((workspace, fileset))

    def fake_upload(
        platform: object,
        *,
        local_path: Path,
        remote_path: str,
        fileset: str,
        workspace: str,
        description: str,
        quiet: bool = False,
    ) -> None:
        assert platform is platform_client
        captured["uploaded_content"] = local_path.read_text()
        cast(list[dict[str, object]], captured["uploads"]).append(
            {
                "local_path": local_path,
                "remote_path": remote_path,
                "fileset": fileset,
                "workspace": workspace,
                "description": description,
                "quiet": quiet,
            }
        )

    monkeypatch.setattr(cli_files_module, "make_platform_client", Mock(return_value=platform_client))
    monkeypatch.setattr(cli_files_module, "ensure_fileset_exists", fake_ensure)
    monkeypatch.setattr(cli_files_module, "upload_file_to_fileset", fake_upload)

    class _State:
        def get_base_url(self, default: str | None = None) -> str | None:
            return default

    result = CliRunner().invoke(
        _app_with_preview_function(monkeypatch),
        [
            "preview",
            "--spec-file",
            str(spec_file),
            "--base-url",
            "http://platform.example",
            "--fileset",
            "anonymizer-inputs",
            "--output-remote-path",
            "previews/latest.ndjson",
            "--quiet",
        ],
        obj=_State(),
    )

    assert result.exit_code == 0, result.output
    assert captured["ensured"] == [("default", "anonymizer-inputs")]
    uploads = cast(list[dict[str, object]], captured["uploads"])
    assert len(uploads) == 1
    upload = uploads[0]
    assert isinstance(upload["local_path"], Path)
    assert {key: value for key, value in upload.items() if key != "local_path"} == {
        "remote_path": "previews/latest.ndjson",
        "fileset": "anonymizer-inputs",
        "workspace": "default",
        "description": "preview output",
        "quiet": True,
    }
    assert [json.loads(line) for line in cast(str, captured["uploaded_content"]).splitlines()] == [
        {
            "kind": "preview_dataset",
            "records": [],
        },
        {"kind": "done"},
    ]


def test_preview_command_exits_one_when_stream_reports_error(tmp_path: Path, monkeypatch) -> None:
    spec_file = tmp_path / "preview.yaml"
    _write_preview_request(spec_file)
    _patch_preview_submit(monkeypatch, [Error(message="bad config")])

    result = CliRunner().invoke(
        _app_with_preview_function(monkeypatch),
        [
            "preview",
            "--spec-file",
            str(spec_file),
            "--base-url",
            "http://platform.example",
        ],
    )

    assert result.exit_code == 1


def test_preview_stream_routes_log_frames_to_stderr(capsys) -> None:
    assert (
        cli_module._emit_preview_line(
            '{"kind":"log","level":"info","message":"loading models"}',
            quiet=False,
        )
        is False
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "loading models\n"


def test_preview_stream_quiet_suppresses_log_frames(capsys) -> None:
    assert (
        cli_module._emit_preview_line(
            '{"kind":"log","level":"info","message":"loading models"}',
            quiet=True,
        )
        is False
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_preview_stream_writes_non_log_frames_to_stdout(capsys) -> None:
    line = '{"kind":"preview_dataset","records":[{"text":"[REDACTED_PERSON]"}]}'

    assert cli_module._emit_preview_line(line, quiet=False) is False

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "kind": "preview_dataset",
        "records": [{"text": "[REDACTED_PERSON]"}],
    }
    assert captured.err == ""


def test_preview_stream_writes_non_log_frames_to_output_file(capsys) -> None:
    line = '{"kind":"preview_dataset","records":[{"text":"[REDACTED_PERSON]"}]}'
    output = StringIO()

    assert cli_module._emit_preview_line(line, quiet=False, output=output) is False

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert json.loads(output.getvalue()) == {
        "kind": "preview_dataset",
        "records": [{"text": "[REDACTED_PERSON]"}],
    }


def test_download_run_artifacts_extracts_tar(tmp_path: Path, monkeypatch) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        content = b"ok"
        info = tarfile.TarInfo("artifacts/dataset.txt")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

    class _Response:
        status_code = 200
        content = buffer.getvalue()

    class _Client:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, url: str, *, headers: dict[str, str]) -> _Response:
            assert url == "http://platform.example/artifacts"
            assert headers == {"Authorization": "Bearer token"}
            return _Response()

    monkeypatch.setattr(cli_module.httpx, "Client", _Client)

    cli_module._download_run_artifacts(
        "http://platform.example/artifacts",
        headers={"Authorization": "Bearer token"},
        output_dir=tmp_path / "out",
    )

    assert (tmp_path / "out" / "artifacts" / "dataset.txt").read_text() == "ok"


def test_preview_stream_error_frame_exits_unsuccessfully(capsys) -> None:
    line = '{"kind":"error","message":"bad config","details":{"type":"ValueError"}}'

    assert cli_module._emit_preview_line(line, quiet=False) is True

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "kind": "error",
        "message": "bad config",
        "details": {"type": "ValueError"},
    }
    assert captured.err == ""


def test_validate_command_runs_library_validation(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAnonymizer:
        def validate_config(self, config: object) -> None:
            captured["config"] = config

    def fake_make_local_anonymizer(*, model_configs: str | Path | None, artifact_path: Path | None = None):
        captured["model_configs"] = model_configs
        captured["artifact_path"] = artifact_path
        return FakeAnonymizer()

    monkeypatch.setattr(cli_module, "_make_local_anonymizer", fake_make_local_anonymizer)

    config = tmp_path / "config.yaml"
    model_configs = tmp_path / "models.yaml"
    _write_config(config)
    model_configs.write_text("model_configs: []\n")

    result = CliRunner().invoke(
        AnonymizerCLI().get_cli(),
        [
            "validate",
            "--config",
            str(config),
            "--model-configs",
            str(model_configs),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["model_configs"] == str(model_configs)
    assert captured["artifact_path"] is None
    assert "Config is valid." in result.output
