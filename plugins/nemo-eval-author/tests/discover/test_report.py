# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The persisted artifacts: portable, machine-readable, and honest about what failed.

Two properties carry the weight. The front matter has to survive a round trip, because a
later agent reads it instead of redoing the work. And the config has to be free of this
machine: absolute paths, a frozen job name, or a real API key in the file would each make
the artifact wrong somewhere other than where it was produced.
"""

import yaml
from harbor.models.job.config import JobConfig
from harbor_fixtures import read_front_matter, write_dataset
from nemo_eval_author_plugin.discovery import report
from nemo_eval_author_plugin.discovery.models import (
    CandidateConfig,
    ConfigSource,
    Finding,
    RequiredEnvVar,
)


def _record(tmp_path, findings=(), env_vars=(), candidate=None):
    return report.build_report(
        agent="ticket-triage",
        workspace="default",
        repo_root=tmp_path,
        candidate=candidate
        or CandidateConfig(data={}, source=ConfigSource(kind="config_file", detail="declared at configs/eval.yaml")),
        findings=list(findings),
        required_env_vars=list(env_vars),
    )


def _authored(**kwargs):
    return CandidateConfig(
        data={},
        source=ConfigSource(kind="convention", detail="inferred from task dirs under evals/validation"),
        **kwargs,
    )


def test_front_matter_survives_a_round_trip(tmp_path):
    record = _record(
        tmp_path,
        findings=[Finding(name="schema", group="validation", status="pass", message="ok", harbor_call="x")],
        env_vars=[RequiredEnvVar(name="HF_TOKEN", declared_in=tmp_path / "evals/task-0/task.toml")],
    )

    front = read_front_matter(report.render_markdown(record))

    assert front["runnable"] is True
    assert front["agent"] == "ticket-triage"
    assert front["validation"] == {"schema": "pass"}
    assert front["harbor_version"] == report.harbor_version()
    # Recorded relative, so the artifact means the same thing on another machine.
    assert front["required_env_vars"][0]["declared_in"] == "evals/task-0/task.toml"


def _owned_config(tmp_path):
    return CandidateConfig(
        data={},
        source=ConfigSource(
            kind="config_file",
            detail="declared at configs/eval.yaml",
            path=tmp_path / "configs" / "eval.yaml",
        ),
    )


def test_a_repo_that_maintains_its_own_config_is_told_to_run_that_file(tmp_path):
    """Publishing a second copy would leave a config in the fileset that nobody edits."""
    record = _record(tmp_path, candidate=_owned_config(tmp_path))

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front["run_config"] == {"location": "repo", "path": "configs/eval.yaml", "pythonpath": None}
    assert "harbor job start -c configs/eval.yaml" in markdown
    assert "harbor-job.yaml" not in markdown


def test_a_config_discovery_authored_points_at_the_fileset_copy(tmp_path):
    """Nothing in the repo declares a config, so the fileset is the only place it exists."""
    record = _record(tmp_path, candidate=_authored())

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front["run_config"] == {
        "location": "fileset",
        "path": "ticket-triage/harbor-job.yaml",
        "pythonpath": None,
    }
    assert "harbor job start -c harbor-job.yaml" in markdown
    assert "Fetch `ticket-triage/harbor-job.yaml`" in markdown, "the config is not on disk yet"


def test_a_config_whose_agent_is_a_repo_module_records_the_search_path_in_the_command(tmp_path):
    """A Harbor JobConfig cannot carry this, and the run fails without it.

    ``harbor job start -c harbor-job.yaml`` on a config naming ``harbor_wrapper:WrappedAgent``
    raises ``No module named 'harbor_wrapper'``: Harbor imports through ``importlib`` and the
    working directory is not on ``sys.path``. So the search path is part of the contract, in
    the front matter for the agent that reads it and in the command for the human who runs it.
    """
    record = _record(tmp_path, candidate=_authored(agent_search_path="src/myagent"))

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front["run_config"]["pythonpath"] == "src/myagent"
    assert "PYTHONPATH=src/myagent harbor job start -c harbor-job.yaml" in markdown


def test_a_wrapper_at_the_repo_root_records_a_repo_relative_dot(tmp_path):
    """Recorded relative like every other path, so the artifact outlives this machine."""
    record = _record(tmp_path, candidate=_authored(agent_search_path="."))

    markdown = report.render_markdown(record)
    target = report.run_target(record)

    assert read_front_matter(markdown)["run_config"]["pythonpath"] == "."
    assert "PYTHONPATH=. harbor job start -c harbor-job.yaml" in markdown
    assert target is not None and str(tmp_path) not in report.run_command(target)


def test_a_config_naming_a_builtin_agent_asks_for_no_search_path(tmp_path):
    """The oracle is Harbor's own, so there is nothing to put on the path."""
    record = _record(tmp_path, candidate=_authored())

    markdown = report.render_markdown(record)

    assert "PYTHONPATH" not in markdown


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
                name="resolution",
                group="validation",
                status="fail",
                message="Harbor could not resolve the job",
                harbor_call="Job.create",
            )
        ],
    )

    markdown = report.render_markdown(record)

    assert record.runnable is False
    assert "cannot run" in markdown
    assert "could not resolve the job" in markdown
    assert "harbor job start" not in markdown, "an unrunnable report must not hand out a run command"


def test_a_report_with_no_config_at_all_is_not_runnable(tmp_path):
    record = report.build_report(
        agent="ticket-triage",
        workspace="default",
        repo_root=tmp_path,
        candidate=None,
        findings=[],
        required_env_vars=[],
    )

    front = read_front_matter(report.render_markdown(record))

    assert record.runnable is False
    assert front["config_source"] is None
    assert front["run_config"] is None
