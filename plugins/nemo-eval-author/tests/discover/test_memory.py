# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""What reaches the fileset, and what deliberately does not.

The invariant worth defending: a ``harbor-job.yaml`` in the fileset is always a config
Harbor accepted. A later agent is told to run whatever it finds there, so a config uploaded
alongside a failing report would be an instruction to run something broken.
"""

from harbor_fixtures import StubClient, StubFiles
from nemo_eval_author_plugin.discovery import memory, report


async def test_both_artifacts_are_uploaded_under_the_agent_prefix():
    client = StubClient()

    ok, findings = await memory.persist(
        client, agent="ticket-triage", workspace="default", markdown="# report\n", job_config="datasets: []\n"
    )

    assert ok is True
    assert [item["remote_path"] for item in client.files.uploads] == [
        "ticket-triage/discovery.md",
        "ticket-triage/harbor-job.yaml",
    ]
    assert all(item["fileset"] == memory.FILESET_NAME for item in client.files.uploads)
    assert all(item["fileset_auto_create"] is True for item in client.files.uploads)
    assert all(item.status == "pass" for item in findings)


async def test_the_config_is_withheld_when_harbor_never_accepted_one():
    client = StubClient()

    ok, findings = await memory.persist(
        client, agent="ticket-triage", workspace="default", markdown="# report\n", job_config=None
    )

    assert ok is True, "the report still has to land, so the failure is documented"
    assert [item["remote_path"] for item in client.files.uploads] == ["ticket-triage/discovery.md"]
    withheld = next(item for item in findings if "Withheld" in item.message)
    assert withheld.status == "warn"
    assert withheld.hint is not None and "always one Harbor could load" in withheld.hint


async def test_an_upload_failure_is_reported_without_claiming_the_config_is_broken():
    client = StubClient(files=StubFiles(fail=True))

    ok, findings = await memory.persist(
        client, agent="ticket-triage", workspace="default", markdown="# report\n", job_config="datasets: []\n"
    )

    assert ok is False
    # A fileset outage says nothing about whether Harbor can run the config, so these are
    # warnings; run.DiscoverResult.ok folds the False into the exit code instead.
    assert all(item.status == "warn" for item in findings)
    assert any("fileset unavailable" in item.message for item in findings)


async def test_a_previous_report_is_read_back_for_comparison(tmp_path):
    record = report.build_report(
        agent="ticket-triage",
        workspace="default",
        repo_root=tmp_path,
        candidate=None,
        findings=[],
        required_env_vars=[],
        inputs=report.fingerprint_inputs([_write(tmp_path / "a.md", "a\n")], tmp_path),
    )
    markdown = report.render_markdown(record)
    client = StubClient(files=StubFiles({"ticket-triage/discovery.md": markdown.encode("utf-8")}))

    prior = await memory.load_previous(client, agent="ticket-triage", workspace="default")

    assert prior is not None
    assert prior.inputs_digest == record.inputs_digest
    assert [item.path for item in prior.inputs] == ["a.md"]
    assert prior.text == markdown


async def test_a_missing_or_unreachable_report_just_means_rediscover():
    empty = await memory.load_previous(StubClient(), agent="ticket-triage", workspace="default")
    assert empty is None

    unusable = StubClient(files=StubFiles({"ticket-triage/discovery.md": b"not a report"}))
    assert await memory.load_previous(unusable, agent="ticket-triage", workspace="default") is None


def test_rehashing_prior_inputs_notices_an_edited_file(tmp_path):
    path = _write(tmp_path / "task.toml", 'version = "1.0"\n')
    inputs = report.fingerprint_inputs([path], tmp_path)
    prior = memory.PriorRecord(inputs=inputs, inputs_digest="sha256:whatever", runnable=True)

    assert memory.rehash_prior_inputs(prior, tmp_path) == inputs

    _write(path, 'version = "1.0"\n# edited\n')
    assert memory.rehash_prior_inputs(prior, tmp_path) != inputs


def test_a_deleted_input_changes_the_digest(tmp_path):
    """A report derived from a file someone removed must not read as still valid."""
    path = _write(tmp_path / "task.toml", 'version = "1.0"\n')
    prior = memory.PriorRecord(
        inputs=report.fingerprint_inputs([path], tmp_path), inputs_digest="sha256:whatever", runnable=True
    )
    path.unlink()

    assert memory.rehash_prior_inputs(prior, tmp_path) == []


async def test_rerunning_overwrites_rather_than_accumulating():
    """Agent-scoped fixed paths mean the fileset holds the latest answer, not a pile."""
    client = StubClient()

    for body in ("# first\n", "# second\n"):
        await memory.persist(
            client, agent="ticket-triage", workspace="default", markdown=body, job_config="datasets: []\n"
        )

    assert len(client.files.uploads) == 4
    assert sorted(client.files.stored) == ["ticket-triage/discovery.md", "ticket-triage/harbor-job.yaml"]
    assert client.files.stored["ticket-triage/discovery.md"] == b"# second\n"


async def test_two_agents_do_not_share_a_path():
    client = StubClient()

    for agent in ("ticket-triage", "invoice-parser"):
        await memory.persist(client, agent=agent, workspace="default", markdown="# report\n", job_config=None)

    assert sorted(client.files.stored) == ["invoice-parser/discovery.md", "ticket-triage/discovery.md"]


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
