# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The persisted artifacts: portable, machine-readable, and honest about what failed.

Two properties carry the weight. The front matter has to survive a round trip, because a
later agent reads it instead of redoing the work. And the config has to be free of this
machine: absolute paths, a frozen job name, or a real API key in the file would each make
the artifact wrong somewhere other than where it was produced.
"""

from datetime import UTC, datetime

import yaml
from harbor.models.job.config import JobConfig
from harbor_fixtures import write_dataset
from nemo_eval_author_plugin.discovery import memory, report
from nemo_eval_author_plugin.discovery.models import (
    CandidateConfig,
    ConfigSource,
    Finding,
    RequiredEnvVar,
)


def _record(tmp_path, findings=(), env_vars=(), inputs=(), candidate=None):
    return report.build_report(
        agent="ticket-triage",
        workspace="default",
        repo_root=tmp_path,
        candidate=candidate
        or CandidateConfig(data={}, source=ConfigSource(kind="config_file", detail="declared at configs/eval.yaml")),
        findings=list(findings),
        required_env_vars=list(env_vars),
        inputs=list(inputs),
    )


def test_front_matter_survives_a_round_trip(tmp_path):
    record = _record(
        tmp_path,
        findings=[Finding(name="schema", group="validation", status="pass", message="ok", harbor_call="x")],
        env_vars=[RequiredEnvVar(name="HF_TOKEN", declared_in=tmp_path / "evals/task-0/task.toml")],
        inputs=report.fingerprint_inputs([_write(tmp_path / "ETHOS.md", "# Ethos\n")], tmp_path),
    )

    front = memory.parse_front_matter(report.render_markdown(record))

    assert front is not None
    assert front["runnable"] is True
    assert front["agent"] == "ticket-triage"
    assert front["validation"] == {"schema": "pass"}
    assert front["inputs_digest"] == record.inputs_digest
    assert front["harbor_version"] == report.harbor_version()
    # Recorded relative, so the artifact means the same thing on another machine.
    assert front["required_env_vars"][0]["declared_in"] == "evals/task-0/task.toml"
    assert front["inputs"] == [{"path": "ETHOS.md", "sha256": record.inputs[0].sha256}]


def test_the_digest_is_stable_and_notices_a_changed_input(tmp_path):
    path = _write(tmp_path / "task.toml", 'version = "1.0"\n')
    first = _record(tmp_path, inputs=report.fingerprint_inputs([path], tmp_path))
    again = _record(tmp_path, inputs=report.fingerprint_inputs([path], tmp_path))
    assert first.inputs_digest == again.inputs_digest

    _write(path, 'version = "1.0"\n# edited\n')
    changed = _record(tmp_path, inputs=report.fingerprint_inputs([path], tmp_path))
    assert changed.inputs_digest != first.inputs_digest


def test_the_digest_ignores_the_order_inputs_were_collected_in(tmp_path):
    first = _write(tmp_path / "a.md", "a\n")
    second = _write(tmp_path / "b.md", "b\n")

    forward = _record(tmp_path, inputs=report.fingerprint_inputs([first, second], tmp_path))
    backward = _record(tmp_path, inputs=report.fingerprint_inputs([second, first], tmp_path))

    assert forward.inputs_digest == backward.inputs_digest


def test_the_persisted_config_carries_no_absolute_paths(tmp_path):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    config = JobConfig.model_validate({"datasets": [{"path": str(dataset)}]})

    rendered = report.render_job_config(config, tmp_path)

    assert yaml.safe_load(rendered)["datasets"] == [{"path": "evals/validation"}]
    assert str(tmp_path) not in rendered


def test_a_path_outside_the_repo_is_left_absolute(tmp_path):
    """Relativizing it would silently point the run at a directory that is not there."""
    outside = tmp_path.parent / "elsewhere"
    config = JobConfig.model_validate({"datasets": [{"path": str(outside)}]})

    rendered = report.render_job_config(config, tmp_path)

    assert yaml.safe_load(rendered)["datasets"] == [{"path": str(outside)}]


def test_a_generated_job_name_is_dropped_and_a_declared_one_is_kept(tmp_path):
    generated = JobConfig.model_validate({"datasets": [{"path": "evals"}]})
    assert "job_name" not in yaml.safe_load(report.render_job_config(generated, tmp_path))

    declared = JobConfig.model_validate({"datasets": [{"path": "evals"}], "job_name": "nightly-triage"})
    assert yaml.safe_load(report.render_job_config(declared, tmp_path))["job_name"] == "nightly-triage"


def test_a_secret_in_the_agent_env_is_templated_rather_than_written(tmp_path):
    """Harbor's own serializer does this; the test pins the behavior we rely on."""
    config = JobConfig.model_validate(
        {
            "agents": [{"name": "oracle", "env": {"OPENAI_API_KEY": "sk-do-not-persist-me"}}],
            "datasets": [{"path": "evals"}],
        }
    )

    rendered = report.render_job_config(config, tmp_path)

    assert "sk-do-not-persist-me" not in rendered


def test_an_unrunnable_report_says_what_blocks_it_and_offers_no_command(tmp_path):
    record = _record(
        tmp_path,
        findings=[
            Finding(
                name="reward",
                group="validation",
                status="fail",
                message="1 task(s) have a test script that never writes a reward file",
                harbor_call="TaskPaths.discovered_test_path_for",
            )
        ],
    )

    markdown = report.render_markdown(record)

    assert record.runnable is False
    assert "cannot run" in markdown
    assert "never writes a reward file" in markdown
    assert "harbor job start" not in markdown, "an unrunnable report must not hand out a run command"


def test_a_report_with_no_config_at_all_says_where_to_start(tmp_path):
    record = report.build_report(
        agent="ticket-triage",
        workspace="default",
        repo_root=tmp_path,
        candidate=None,
        findings=[],
        required_env_vars=[],
        inputs=[],
    )

    markdown = report.render_markdown(record)

    assert record.runnable is False
    assert "harbor job init" in markdown


def test_restamping_moves_the_stamp_and_leaves_the_narrative_alone(tmp_path):
    record = _record(tmp_path, inputs=report.fingerprint_inputs([_write(tmp_path / "a.md", "a\n")], tmp_path))
    original = report.render_markdown(record)
    later = datetime(2027, 1, 1, tzinfo=UTC)

    restamped = memory.restamp(original, when=later, harbor_version="9.9.9")

    assert restamped is not None
    front = memory.parse_front_matter(restamped)
    assert front is not None
    assert front["last_validated_at"] == later.isoformat()
    assert front["harbor_version"] == "9.9.9"
    assert front["discovered_at"] == record.discovered_at.isoformat(), "discovery time is history, not a stamp"
    assert front["inputs_digest"] == record.inputs_digest
    assert original.split("\n---\n", 1)[1] == restamped.split("\n---\n", 1)[1]


def test_restamping_declines_a_file_without_front_matter():
    assert memory.restamp("# just markdown\n", when=datetime.now(UTC), harbor_version="1.0") is None


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
