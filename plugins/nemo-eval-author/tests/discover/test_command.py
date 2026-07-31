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
    MENTIONS_REWARD_IN_COMMENT,
    StubClient,
    StubFiles,
    write_dataset,
    write_job_config,
    write_task,
    write_wrapper,
)
from nemo_eval_author_plugin import cli
from nemo_eval_author_plugin.discovery import memory, validate
from nemo_eval_author_plugin.discovery import run as discovery
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


@pytest.fixture
def no_scout(monkeypatch):
    """Fail loudly if a test reaches the LLM scout, which would need real credentials."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("the scout must not run in these tests")

    monkeypatch.setattr(discovery, "_scout", _forbidden)


# Pytest's tmp_path names would be slugged, so tests that assert on a remote path name the
# agent outright. Defaulting is covered on its own below.
AGENT = "ticket-triage"


def _invoke(app, repo, *extra):
    # The scout is opt-in and there is no way to ask for it here, so no test that goes through
    # this helper can reach a model. test_the_scout_is_opt_in pins that default.
    return runner.invoke(app, ["discover", "--repo", str(repo), *extra])


def _invoke_named(app, repo, *extra):
    return _invoke(app, repo, "--agent", AGENT, *extra)


def test_a_healthy_repo_exits_zero_and_records_both_artifacts(app, client, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path)

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "Harbor can run this repo's evals" in result.output
    assert "harbor job start -c harbor-job.yaml" in result.output
    assert sorted(client.files.stored) == [f"{AGENT}/discovery.md", f"{AGENT}/harbor-job.yaml"]


def test_a_repo_that_maintains_its_own_config_keeps_it_and_records_only_the_report(app, client, tmp_path):
    """The repo's file is what Harbor validated, so a copy in the fileset could only drift from it."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_config(tmp_path / "configs" / "eval.yaml", dataset="evals/validation")

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "harbor job start -c configs/eval.yaml" in result.output
    assert client.files.stored.keys() == {f"{AGENT}/discovery.md"}
    assert "Withheld" not in result.output, "nothing was withheld; there was nothing of ours to publish"


def test_a_config_the_scout_adjusted_is_published_instead_of_the_repo_file(app, client, monkeypatch, tmp_path):
    """Once a payload diverges from the file it came from, that file is no longer what to run.

    Stands in for the scout so the ownership branch is exercised without a model: the repo's
    config names a dataset that is not there, and the repair points it at the one that is.
    """
    write_dataset(tmp_path / "evals" / "validation")
    write_job_config(tmp_path / "configs" / "eval.yaml", dataset="evals/missing")

    async def _repair(candidate, outcome, repo_root):
        candidate.data["datasets"] = [{"path": "evals/validation"}]
        candidate.source.adjusted = True
        return candidate, await validate.run_ladder(candidate, repo_root), []

    monkeypatch.setattr(discovery, "_scout", _repair)

    result = runner.invoke(app, ["discover", "--repo", str(tmp_path), "--agent", AGENT, "--dangerously-fix"])

    assert result.exit_code == 0, result.output
    assert "harbor job start -c harbor-job.yaml" in result.output
    assert sorted(client.files.stored) == [f"{AGENT}/discovery.md", f"{AGENT}/harbor-job.yaml"]


def test_a_repo_whose_tasks_never_score_exits_one_and_withholds_the_config(app, client, tmp_path):
    write_dataset(tmp_path / "evals" / "validation", test_script=MENTIONS_REWARD_IN_COMMENT)

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "Harbor cannot run this repo's evals" in result.output
    assert "reward" in result.output
    assert "Withheld harbor-job.yaml" in result.output, "an absent config has to be explained, not just missing"
    # The report still lands, so the failure is documented rather than lost.
    assert sorted(client.files.stored) == [f"{AGENT}/discovery.md"]


def test_the_scout_is_opt_in(app, client, tmp_path, no_scout):
    """A config Harbor rejects must not reach a model unless --dangerously-fix asked for it."""
    write_dataset(tmp_path / "evals" / "validation", test_script=MENTIONS_REWARD_IN_COMMENT)

    result = runner.invoke(app, ["discover", "--repo", str(tmp_path), "--agent", AGENT])

    assert result.exit_code == 1, result.output
    assert "Harbor cannot run this repo's evals" in result.output, "the verdict was reached without a model"


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
    assert "inputs_digest:" in result.output, "the report itself is printed"
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


def test_an_unchanged_repo_is_not_revalidated(app, client, tmp_path, no_scout):
    write_dataset(tmp_path / "evals" / "validation")
    first = _invoke(app, tmp_path)
    assert first.exit_code == 0, first.output

    second = _invoke(app, tmp_path)

    assert second.exit_code == 0, second.output
    assert "Nothing the previous report depended on has changed" in second.output
    assert "validation/schema" not in second.output, "the ladder should not have run again"


def test_a_runnable_flag_that_is_not_a_boolean_does_not_switch_off_revalidation(app, client, tmp_path):
    """Reuse skips the entire ladder, so only a real YAML ``true`` may switch revalidation off.

    The string ``"false"`` is the cruel case: it is truthy, and a reused record carries no
    findings, so the command would exit zero having validated nothing and claiming a verdict
    the stored report explicitly denies.
    """
    write_dataset(tmp_path / "evals" / "validation")
    assert _invoke_named(app, tmp_path).exit_code == 0
    stored = client.files.stored[memory.remote_report_path(AGENT)].decode("utf-8")
    assert "runnable: true" in stored
    client.files.stored[memory.remote_report_path(AGENT)] = stored.replace(
        "runnable: true", "runnable: 'false'"
    ).encode("utf-8")

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "validation/schema" in result.output, "the ladder had to run again"
    assert "Nothing the previous report depended on has changed" not in result.output


def test_a_wrapper_copy_inside_a_virtualenv_is_not_fingerprinted(app, client, tmp_path):
    """The digest decides whether a later run may skip the ladder, so it covers the repo's own source only.

    A vendored module whose basename matches the agent's import path would otherwise tie this
    report's freshness to a dependency: reinstalling the package invalidates a verdict that
    still holds, and the digest quietly covers bytes the repo does not own.
    """
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path)
    vendored = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages"
    vendored.mkdir(parents=True)
    write_wrapper(vendored, class_name="VendoredAgent")

    assert _invoke_named(app, tmp_path).exit_code == 0

    front = memory.parse_front_matter(client.files.stored[memory.remote_report_path(AGENT)].decode("utf-8"))
    assert front is not None
    recorded = [item["path"] for item in front["inputs"]]
    assert "harbor_wrapper.py" in recorded, "the repo's own wrapper shaped the verdict, so it is an input"
    assert [path for path in recorded if path.startswith(".venv")] == []


def test_a_reused_report_still_names_the_host_variables_a_run_needs(app, client, tmp_path):
    """A repeat run is the common case, so losing ``Needs:`` there hides it nearly always.

    Harbor raises on an unresolved template at trial start. A record that stops naming
    ``HF_TOKEN`` hands out a run command that cannot work and says nothing about why.
    """
    write_task(
        tmp_path / "evals" / "validation" / "task-0",
        task_toml='\n[environment.env]\nHF_TOKEN = "${HF_TOKEN}"\n',
    )
    first = _invoke_named(app, tmp_path)
    assert first.exit_code == 0, first.output
    assert "Needs: HF_TOKEN" in first.output

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 0, result.output
    assert "Nothing the previous report depended on has changed" in result.output
    assert "Needs: HF_TOKEN" in result.output


def test_a_reused_report_that_cannot_be_reuploaded_says_what_went_wrong(app, client, monkeypatch, tmp_path):
    """The exit code says the record was not written; only the finding says why.

    This branch prints almost nothing by design, but the upload warning carries the exception,
    the fileset and the remote path — the whole diagnosis, and it is on every other path.
    """
    write_dataset(tmp_path / "evals" / "validation")
    assert _invoke_named(app, tmp_path).exit_code == 0
    offline = StubClient(files=StubFiles(client.files.stored, fail=True))
    monkeypatch.setattr(discovery, "make_client", lambda base_url: offline)

    result = _invoke_named(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "Nothing the previous report depended on has changed" in result.output, "this is the reuse path"
    assert "Could not upload discovery.md" in result.output
    assert "fileset unavailable" in result.output
    assert "could not be recorded" in result.output


def test_refresh_forces_the_ladder_to_run_again(app, client, tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    assert _invoke(app, tmp_path).exit_code == 0

    result = _invoke(app, tmp_path, "--refresh")

    assert result.exit_code == 0, result.output
    assert "validation/schema" in result.output


def test_an_edited_task_is_revalidated(app, client, tmp_path):
    dataset = write_dataset(tmp_path / "evals" / "validation")
    assert _invoke(app, tmp_path).exit_code == 0

    # Break the reward contract; the digest moves, so the prior verdict cannot be reused.
    (dataset / "task-0" / "tests" / "test.sh").write_text(MENTIONS_REWARD_IN_COMMENT)
    result = _invoke(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "never writes a reward file" in result.output


def test_a_previously_failing_repo_is_always_revalidated(app, client, tmp_path, no_scout):
    """A failure may have been the machine's fault, so it is never taken on trust."""
    write_dataset(tmp_path / "evals" / "validation", test_script=MENTIONS_REWARD_IN_COMMENT)
    assert _invoke(app, tmp_path).exit_code == 1

    result = _invoke(app, tmp_path)

    assert result.exit_code == 1, result.output
    assert "validation/reward" in result.output


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

    stored = client.files.stored[memory.remote_report_path(AGENT)].decode("utf-8")
    front = memory.parse_front_matter(stored)
    assert front is not None
    assert front["runnable"] is True
    assert front["config_source"]["kind"] == "convention"
