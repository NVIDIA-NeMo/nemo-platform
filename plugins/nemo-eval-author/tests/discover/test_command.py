# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests for the discovery command."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import typer
from harbor_fixtures import StubClient, StubFiles, read_front_matter, write_dataset, write_job_config
from nemo_eval_author_plugin import cli
from nemo_eval_author_plugin.discovery import run as discovery
from nemo_eval_author_plugin.discovery import validate
from typer.testing import CliRunner

runner = CliRunner()
AGENT = "ticket-triage"


@pytest.fixture
def app() -> typer.Typer:
    return cli.EvalAuthorCLI().get_cli()


@pytest.fixture
def client(monkeypatch) -> StubClient:
    stub = StubClient()
    monkeypatch.setattr(discovery, "make_client", lambda base_url: stub)
    return stub


@pytest.fixture(autouse=True)
def workspace(monkeypatch, tmp_path):
    config = tmp_path / "nmp-config.yaml"
    config.touch()
    monkeypatch.setenv("NMP_WORKSPACE", "default")
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config))


@pytest.fixture(autouse=True)
def successful_external_preflight(monkeypatch):
    monkeypatch.setattr(validate.EnvironmentFactory, "run_preflight", lambda *args: None)
    monkeypatch.setattr(
        validate,
        "check_config_file",
        lambda path, root: validate._check("round-trip", "pass", "The config file loads through the Harbor CLI."),
    )


def _invoke(app: typer.Typer, repo: Path, *extra: str):
    return runner.invoke(app, ["discover", "--repo", str(repo), *extra])


def _healthy_repo(root: Path) -> Path:
    write_dataset(root / "evals" / "validation")
    write_job_config(root / "configs" / "eval.yaml", dataset="evals/validation")
    return root


def _snapshot(root: Path) -> list[tuple[str, bytes | None]]:
    return [
        (path.relative_to(root).as_posix(), path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    ]


def test_command_reads_the_canonical_platform_agent_spec(app, client, monkeypatch, tmp_path):
    repo = _healthy_repo(tmp_path / "agent-repo")
    (repo / "ETHOS.md").write_text("# Local\n", encoding="utf-8")
    ref = f"default/{AGENT}-spec#AGENT-SPEC.md"
    download = AsyncMock(side_effect=[b"# Platform one\n", b"# Platform two\n"])
    monkeypatch.setattr(client.files, "download_content", download)

    first = _invoke(app, repo, "--agent", AGENT)
    first_front = read_front_matter(client.files.stored[f"{AGENT}/discovery.md"])
    second = _invoke(app, repo, "--agent", AGENT)
    second_front = read_front_matter(client.files.stored[f"{AGENT}/discovery.md"])

    assert (first.exit_code, second.exit_code) == (0, 0)
    assert first_front["ethos_path"] == ref
    assert first_front["fingerprint"] != second_front["fingerprint"]
    assert [awaited.kwargs for awaited in download.await_args_list] == [{"remote_path": ref}] * 2


def test_healthy_config_uploads_only_discovery_report_and_does_not_write_to_repo(app, client, tmp_path):
    repo = _healthy_repo(tmp_path / "agent-repo")
    before = _snapshot(repo)

    result = _invoke(app, repo, "--agent", AGENT)

    assert result.exit_code == 0, result.output
    assert "Repository\n  ✓ Using Harbor config configs/eval.yaml." in result.output
    assert "harbor job start -c configs/eval.yaml" in result.output
    assert "Uploaded ticket-triage/discovery.md to fileset 'nemo-eval-author'." in result.output
    assert client.files.stored.keys() == {f"{AGENT}/discovery.md"}
    assert len(client.files.uploads) == 1
    assert client.files.uploads[0]["fileset"] == "nemo-eval-author"
    assert client.files.uploads[0]["workspace"] == "default"
    assert client.files.uploads[0]["fileset_auto_create"] is True
    assert read_front_matter(client.files.stored[f"{AGENT}/discovery.md"])["runnable"] is True
    assert _snapshot(repo) == before
    assert client.closed is True
    assert result.output.rstrip().endswith("Final overview: Discovery passed with 0 failures and 2 warnings.")


def test_missing_config_exits_one_but_uploads_the_report(app, client, tmp_path):
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Empty\n", encoding="utf-8")

    result = _invoke(app, repo, "--agent", AGENT)

    assert result.exit_code == 1, result.output
    assert client.files.stored.keys() == {f"{AGENT}/discovery.md"}
    front = read_front_matter(client.files.stored[f"{AGENT}/discovery.md"])
    assert front["runnable"] is False
    assert front["config_path"] is None
    assert front["run_command"] is None
    assert "harbor job start" not in result.output
    assert result.output.rstrip().endswith("Final overview: Discovery failed with 1 failure and 2 warnings.")


def test_rejected_config_exits_one_and_uploads_its_report(app, client, tmp_path):
    repo = tmp_path / "rejected-repo"
    config = repo / "configs" / "eval.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("datasets:\n  - invalid\n", encoding="utf-8")

    result = _invoke(app, repo, "--agent", AGENT)

    assert result.exit_code == 1, result.output
    front = read_front_matter(client.files.stored[f"{AGENT}/discovery.md"])
    assert front["runnable"] is False
    assert any(check["name"] == "schema" and check["status"] == "fail" for check in front["checks"])
    assert front["run_command"] is None
    assert result.output.rstrip().endswith("Final overview: Discovery failed with 1 failure and 2 warnings.")


def test_schema_failure_does_not_upload_the_rejected_input_value(app, client, tmp_path):
    secret = "nvapi-secret-value-123456789"
    repo = tmp_path / "secret-rejected-repo"
    config = repo / "configs" / "eval.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(f"datasets:\n  - {secret}\n", encoding="utf-8")

    result = _invoke(app, repo, "--agent", AGENT)

    assert result.exit_code == 1, result.output
    uploaded = client.files.stored[f"{AGENT}/discovery.md"]
    schema_check = next(check for check in read_front_matter(uploaded)["checks"] if check["name"] == "schema")
    assert secret not in schema_check["message"]
    assert secret.encode() not in uploaded
    assert "errors.pydantic.dev" not in schema_check["message"]


def test_dry_run_uploads_nothing_and_prints_the_report(app, client, tmp_path):
    repo = _healthy_repo(tmp_path / "dry-repo")

    result = _invoke(app, repo, "--agent", AGENT, "--dry-run")

    assert result.exit_code == 0, result.output
    assert "Dry run: no files were uploaded." in result.output
    assert "---\nschema_version: 1" in result.output
    assert "runnable: true" in result.output
    assert client.files.uploads == []
    assert result.output.rstrip().endswith("Final overview: Discovery passed with 0 failures and 2 warnings.")


def test_upload_error_exits_one(app, monkeypatch, tmp_path):
    repo = _healthy_repo(tmp_path / "upload-error-repo")
    client = StubClient(files=StubFiles(fail=True))
    monkeypatch.setattr(discovery, "make_client", lambda base_url: client)

    result = _invoke(app, repo, "--agent", AGENT)

    assert result.exit_code == 1, result.output
    assert "Upload failed: RuntimeError: fileset unavailable" in result.output
    assert "harbor job start -c configs/eval.yaml" in result.output
    assert client.files.stored == {}
    assert result.output.rstrip().endswith("Final overview: Discovery failed with 1 failure and 2 warnings.")


def test_agent_name_precedence_uses_explicit_profile_then_directory(app, client, tmp_path):
    explicit = _healthy_repo(tmp_path / "explicit-checkout")
    (explicit / "optimizer.yaml").write_text("agent: ignored\n", encoding="utf-8")
    profiled = _healthy_repo(tmp_path / "profile-checkout")
    (profiled / "optimizer.yaml").write_text("agent: Profile Agent\n", encoding="utf-8")
    defaulted = _healthy_repo(tmp_path / "Directory Agent")

    results = [
        _invoke(app, explicit, "--agent", "explicit-agent"),
        _invoke(app, profiled),
        _invoke(app, defaulted),
    ]

    assert all(result.exit_code == 0 for result in results), [result.output for result in results]
    assert client.files.stored.keys() == {
        "explicit-agent/discovery.md",
        "profile-agent/discovery.md",
        "directory-agent/discovery.md",
    }


def test_explicit_agent_is_slugged_for_traces_and_remote_paths(app, client, tmp_path, monkeypatch):
    repo = _healthy_repo(tmp_path / "explicit-agent-repo")
    trace_probe = AsyncMock(
        return_value=discovery.scan._check("traces", "warn", "No traces exist.", severity="advisory")
    )
    monkeypatch.setattr(discovery.scan, "probe_traces", trace_probe)

    result = _invoke(app, repo, "--agent", "../Ticket Agent#production")

    assert result.exit_code == 0, result.output
    trace_probe.assert_awaited_once_with(client, agent="ticket-agent-production", workspace="default")
    assert client.files.stored.keys() == {"ticket-agent-production/discovery.md"}
    assert (
        read_front_matter(client.files.stored["ticket-agent-production/discovery.md"])["agent"]
        == "ticket-agent-production"
    )


def test_every_invocation_revalidates_the_repository_config(app, client, tmp_path):
    repo = _healthy_repo(tmp_path / "changing-repo")
    config = repo / "configs" / "eval.yaml"

    first = _invoke(app, repo, "--agent", AGENT)
    first_front = read_front_matter(client.files.stored[f"{AGENT}/discovery.md"])
    config.write_text("datasets:\n  - invalid\n", encoding="utf-8")
    second = _invoke(app, repo, "--agent", AGENT)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 1, second.output
    second_front = read_front_matter(client.files.stored[f"{AGENT}/discovery.md"])
    assert second_front["runnable"] is False
    assert any(check["name"] == "schema" and check["status"] == "fail" for check in second_front["checks"])
    assert {
        "discovered_at": second_front["discovered_at"] != first_front["discovered_at"],
        "fingerprint": second_front["fingerprint"] != first_front["fingerprint"],
    } == {"discovered_at": True, "fingerprint": True}
