# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End to end through the CLI, with the platform stubbed out.

Every test passes ``--repo`` explicitly and replaces ``make_client``. Without both, the
command defaults to the current directory and uploads to whatever platform the developer
happens to have running, which is how a unit test quietly becomes a network call.

The exit code is the contract these pin down: this command is meant to be usable as a gate,
so exit 0 has to mean a config was validated *and* recorded, and nothing else.

Named for the command rather than ``test_cli.py`` because ``tests/test_cli.py`` already
covers the plugin's command surface. Running the plugin's suite on its own picks up the
plugin's pytest config, which leaves the default prepend import mode in place, and two test
files sharing a basename abort collection there.
"""

import pytest
import typer
from harbor_fixtures import (
    StubClient,
    StubFiles,
    read_front_matter,
    write_dataset,
    write_job_config,
    write_task,
    write_wrapper,
)
from nemo_eval_author_plugin import cli
from nemo_eval_author_plugin.discovery import memory
from nemo_eval_author_plugin.discovery import run as discovery
from nemo_eval_author_plugin.discovery.models import JOB_CONFIG_FILENAME
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    return cli.EvalAuthorCLI().get_cli()


@pytest.fixture
def client(monkeypatch) -> StubClient:
    """A stub platform, installed where ``run`` looks it up."""
    stub = StubClient()
    monkeypatch.setattr(discovery, "make_client", lambda base_url: stub)
    return stub


@pytest.fixture(autouse=True)
def workspace(monkeypatch, tmp_path):
    """Pin the workspace, which the command reads from the platform context rather than a flag.

    Both variables are needed. ``NMP_WORKSPACE`` fixes the value, but resolving a context still
    reads the config file and raises on a dangling cluster or user reference, so this points the
    platform at an empty one. Empty rather than absent, because an explicit ``NMP_CONFIG_FILE``
    that does not exist is an error rather than a fallback.
    """
    config = tmp_path / "nmp-config.yaml"
    config.touch()
    monkeypatch.setenv("NMP_WORKSPACE", "default")
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config))


# Pytest's tmp_path names would be slugged, so tests that assert on a remote path name the
# agent outright. Defaulting is covered on its own below.
AGENT = "ticket-triage"


def _invoke(app, repo, *extra):
    return runner.invoke(app, ["discover", "--repo", str(repo), *extra])


def _invoke_named(app, repo, *extra):
    return _invoke(app, repo, "--agent", AGENT, *extra)


def test_a_healthy_repo_exits_zero_and_records_both_artifacts(app, client, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path)

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "Harbor can run this repo's evals" in result.output
    assert "PYTHONPATH=. harbor job start -c harbor-job.yaml" in result.output
    assert sorted(client.files.stored) == [f"{AGENT}/discovery.md", f"{AGENT}/harbor-job.yaml"]


def test_the_command_printed_for_a_nested_wrapper_can_actually_import_it(app, client, tmp_path):
    """The command is the deliverable, so it has to name the directory the module is in.

    ``harbor job start -c harbor-job.yaml`` against a config naming ``harbor_wrapper`` fails
    with ``No module named 'harbor_wrapper'``; Harbor's importer never looks in the working
    directory. The printed command and the recorded one both have to carry the fix, and
    they have to agree.
    """
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path / "src" / "myagent")

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "PYTHONPATH=src/myagent harbor job start -c harbor-job.yaml" in result.output
    front = read_front_matter(client.files.stored[memory.remote_report_path(AGENT)])
    assert front["run_config"]["pythonpath"] == "src/myagent"
    # The config itself is a Harbor JobConfig and has nowhere to say this.
    assert "PYTHONPATH" not in client.files.stored[f"{AGENT}/{JOB_CONFIG_FILENAME}"].decode()


def test_a_repo_that_maintains_its_own_config_keeps_it_and_records_only_the_report(app, client, tmp_path):
    """The repo's file is what Harbor validated, so a copy in the fileset could only drift from it."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_config(tmp_path / "configs" / "eval.yaml", dataset="evals/validation")

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "harbor job start -c configs/eval.yaml" in result.output
    assert client.files.stored.keys() == {f"{AGENT}/discovery.md"}
    assert "Withheld" not in result.output, "nothing was withheld; there was nothing of ours to publish"


def test_a_repo_harbor_rejects_exits_one_and_withholds_the_config(app, client, tmp_path):
    """The config names a dataset that is not there, so Harbor cannot resolve the job."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_config(tmp_path / "configs" / "eval.yaml", dataset="evals/missing")

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "Harbor cannot run this repo's evals" in result.output
    assert "resolution" in result.output
    # The report still lands, so the failure is documented rather than lost.
    assert sorted(client.files.stored) == [f"{AGENT}/discovery.md"]


def test_a_config_harbor_rejects_is_never_published(app, client, tmp_path):
    """A config in this fileset is always one Harbor could run, so an absent one is explained."""
    write_task(tmp_path / "evals" / "validation" / "task-0", task_toml='\n[[steps]]\nname = "nowhere"\n')

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "Withheld harbor-job.yaml" in result.output, "an absent config has to be explained, not just missing"
    assert sorted(client.files.stored) == [f"{AGENT}/discovery.md"]


def test_a_repo_with_no_harbor_setup_at_all_exits_one(app, client, tmp_path):
    (tmp_path / "README.md").write_text("# Just a repo\n")

    result = _invoke(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "No Harbor job config could be assembled" in result.output


def test_dry_run_prints_the_artifacts_and_uploads_nothing(app, client, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")

    result = _invoke(app, tmp_path, "--dry-run")

    assert result.exit_code == 0, result.output
    assert "Dry run: nothing was uploaded." in result.output
    assert "runnable: true" in result.output, "the report itself is printed"
    assert client.files.uploads == []


def test_the_agent_name_defaults_to_the_repo_directory(app, client, tmp_path):
    repo = tmp_path / "Ticket Triage Agent"
    write_dataset(repo / "evals" / "validation")

    result = _invoke(app, repo)

    assert result.exit_code == 0, result.output
    assert "ticket-triage-agent/discovery.md" in client.files.stored


def test_the_name_declared_in_the_profile_beats_the_directory(app, client, tmp_path):
    """The name is the fileset path, so guessing it wrong hides the artifacts from ASE-675."""
    repo = tmp_path / "some-checkout-dir"
    write_dataset(repo / "evals" / "validation")
    (repo / "optimizer.yaml").write_text(
        "agent: Ticket Triage\ntask_template: evals/template\ndatasets:\n  validation: evals/validation\n"
    )

    result = _invoke(app, repo)

    assert result.exit_code == 0, result.output
    assert "ticket-triage/discovery.md" in client.files.stored


def test_a_profile_written_for_a_newer_experimentalist_still_names_the_directory(app, client, tmp_path):
    """A profile we cannot parse costs the name, not the run."""
    repo = tmp_path / "invoice-parser"
    write_dataset(repo / "evals" / "validation")
    (repo / "optimizer.yaml").write_text("agent:\n  name: Ticket Triage\n  version: 2\n")

    result = _invoke(app, repo)

    assert result.exit_code == 0, result.output
    assert "invoice-parser/discovery.md" in client.files.stored


def test_an_explicit_agent_name_wins(app, client, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    (tmp_path / "optimizer.yaml").write_text("agent: ignored\ndatasets:\n  validation: evals/validation\n")

    result = _invoke(app, tmp_path, "--agent", "invoice-parser")

    assert result.exit_code == 0, result.output
    assert "invoice-parser/discovery.md" in client.files.stored


def test_a_run_that_needs_host_variables_names_them(app, client, tmp_path):
    """Harbor raises on an unresolved template at trial start, so a run command that does
    not name ``HF_TOKEN`` cannot work and says nothing about why."""
    write_task(
        tmp_path / "evals" / "validation" / "task-0",
        task_toml='\n[environment.env]\nHF_TOKEN = "${HF_TOKEN}"\n',
    )

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "Needs: HF_TOKEN" in result.output


def test_every_run_revalidates_from_scratch(app, client, tmp_path):
    """No verdict is taken on trust from a previous run: the repo may have moved under it."""
    dataset = write_dataset(tmp_path / "evals" / "validation")
    assert _invoke(app, tmp_path).exit_code == 0

    # A task Harbor cannot parse at all, added after the first run recorded a clean verdict.
    (dataset / "task-1" / "task.toml").write_text("not = [valid\n")
    result = _invoke(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "validation/schema" in result.output, "the ladder ran again"


def test_an_unwritable_fileset_exits_one_even_though_harbor_is_happy(app, monkeypatch, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    monkeypatch.setattr(discovery, "make_client", lambda base_url: StubClient(files=StubFiles(fail=True)))

    result = _invoke(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "Harbor can run this repo's evals" in result.output
    assert "could not be recorded" in result.output


def test_traces_are_reported_without_blocking_a_run(app, monkeypatch, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    monkeypatch.setattr(discovery, "make_client", lambda base_url: StubClient(trace_total=None))

    result = _invoke(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "repo/traces" in result.output


def test_nothing_is_written_into_the_repo_being_inspected(app, client, tmp_path):
    """The ladder runs with cwd inside the repo, so a Harbor side effect would land here."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_config(tmp_path / "configs" / "eval.yaml", dataset="evals/validation")
    before = {path.name for path in tmp_path.rglob("*")}

    assert _invoke_named(app, tmp_path).exit_code == 0

    assert {path.name for path in tmp_path.rglob("*")} == before


def test_the_platform_client_is_closed(app, client, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")

    _invoke(app, tmp_path)

    assert client.closed is True


def test_a_nonexistent_repo_is_rejected_by_the_flag(app, client, tmp_path):
    result = runner.invoke(app, ["discover", "--repo", str(tmp_path / "nope")])

    assert result.exit_code != 0
    assert client.files.uploads == []


def test_the_uploaded_report_carries_the_verdict_that_was_printed(app, client, tmp_path):
    """A later agent reads the fileset copy, so it has to be the copy that was verified."""
    write_dataset(tmp_path / "evals" / "validation")

    assert _invoke_named(app, tmp_path).exit_code == 0

    front = read_front_matter(client.files.stored[memory.remote_report_path(AGENT)])
    assert front["runnable"] is True
    assert front["config_source"]["kind"] == "convention"
    assert front["run_config"] == {
        "location": "fileset",
        "path": f"{AGENT}/{JOB_CONFIG_FILENAME}",
        "pythonpath": None,
    }
