# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The validation ladder, against real Harbor task directories.

Every fixture here is a layout Harbor itself accepts or rejects, so these tests assert
against Harbor's validators rather than against our reading of them. That matters most for
the shapes a hand-rolled "does tests/test.sh exist" check gets wrong: a multi-step task, a
Windows task, a task graded from a separate verifier image, and a task that names a
prebuilt image instead of shipping a Dockerfile. Each of those is legitimate, and each one
a naive check would fail.

The backend rung is excluded from pass assertions because it runs Docker's preflight, and
whether a daemon is up is a fact about the machine rather than about the repo under test.
Tests that care about the backend assert on that finding directly.
"""

import sys

from discovery_fixtures import (
    MENTIONS_REWARD_IN_COMMENT,
    WRITES_REWARD,
    write_dataset,
    write_task,
    write_wrapper,
)
from nemo_eval_author_plugin.discovery import sources, validate
from nemo_eval_author_plugin.discovery.models import CandidateConfig, ConfigSource


def _candidate(data: dict) -> CandidateConfig:
    return CandidateConfig(data=data, source=ConfigSource(kind="config_file", detail="test fixture"))


def _finding(outcome, name):
    matches = [item for item in outcome.findings if item.name == name]
    assert matches, f"no {name!r} finding in {[item.name for item in outcome.findings]}"
    return matches[0]


def _repo_failures(outcome):
    """Failures the repo is responsible for, so Docker's absence does not fail a test."""
    return [item for item in outcome.findings if item.status == "fail" and item.name != "backend"]


async def test_a_well_formed_repo_passes_every_rung(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    candidate = _candidate({"agents": [{"name": "oracle"}], "datasets": [{"path": str(tmp_path / "evals/validation")}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _repo_failures(outcome) == []
    assert _finding(outcome, "tasks").message.startswith("2 of 2")
    assert _finding(outcome, "schema").harbor_call == "JobConfig.model_validate"
    assert _finding(outcome, "resolution").harbor_call == "Job.create"
    # Every verdict must be attributable to Harbor, or the artifact is not trustworthy.
    assert all(item.provenance == "harbor" for item in outcome.findings)


async def test_schema_failure_names_the_harbor_validator(tmp_path):
    outcome = await validate.run_ladder(_candidate({"datasets": "not-a-list"}), tmp_path)

    schema = _finding(outcome, "schema")
    assert schema.status == "fail"
    assert schema.harbor_call == "JobConfig.model_validate"
    # Nothing downstream can be judged once the schema is wrong.
    assert [item.name for item in outcome.findings] == ["schema"]
    assert outcome.config is None


async def test_resolution_failure_reports_the_error_a_real_run_would_hit(tmp_path):
    candidate = _candidate({"datasets": [{"path": str(tmp_path / "nope")}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    resolution = _finding(outcome, "resolution")
    assert resolution.status == "fail"
    assert resolution.harbor_call == "Job.create"
    assert resolution.hint is not None and "before starting any container" in resolution.hint


async def test_a_task_harbor_silently_skips_is_reported(tmp_path):
    """Harbor drops a directory it cannot parse without raising, so a run would score fewer
    tasks than the repo holds and nothing about the result would look incomplete."""
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0")
    write_task(dataset / "task-1", instruction=None)
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    # Harbor resolved only the good one, so the tasks rung sees nothing wrong.
    assert _finding(outcome, "tasks").message.startswith("1 of 1")
    coverage = _finding(outcome, "coverage")
    assert coverage.status == "fail"
    assert "task-1" in coverage.message
    assert "instruction.md" in coverage.message
    assert coverage.hint is not None and "silently" in coverage.hint


async def test_a_dataset_that_selects_a_subset_is_not_accused_of_dropping_tasks(tmp_path):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=3)
    candidate = _candidate({"datasets": [{"path": str(dataset), "task_names": ["task-0"]}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    coverage = _finding(outcome, "coverage")
    assert coverage.status == "warn"
    assert coverage.hint is not None and "selects a subset" in coverage.hint
    assert _repo_failures(outcome) == []


async def test_a_scaffolded_task_that_never_writes_a_reward_is_caught(tmp_path):
    """Harbor's own template mentions the reward file only in a comment."""
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1, test_script=MENTIONS_REWARD_IN_COMMENT)
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    reward = _finding(outcome, "reward")
    assert reward.status == "fail"
    assert _finding(outcome, "tasks").status == "pass", "the task is structurally fine; only its scoring is broken"
    assert reward.hint is not None and "RewardFileNotFoundError" in reward.hint


async def test_a_multi_step_task_is_valid_without_a_root_instruction(tmp_path):
    dataset = tmp_path / "evals" / "validation"
    write_task(
        dataset / "task-0",
        task_toml='\n[[steps]]\nname = "first"\n\n[[steps]]\nname = "second"\n',
        instruction=None,
        steps={"first": {"instruction": "Step one.\n"}, "second": {"instruction": "Step two.\n"}},
    )
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "tasks").status == "pass"
    assert _repo_failures(outcome) == []


async def test_a_multi_step_task_is_checked_for_a_reward_in_every_step(tmp_path):
    """A shared script covers a step with none of its own; a step's own script must score."""
    dataset = tmp_path / "evals" / "validation"
    write_task(
        dataset / "task-0",
        task_toml='\n[[steps]]\nname = "first"\n\n[[steps]]\nname = "second"\n',
        instruction=None,
        test_script=WRITES_REWARD,
        steps={
            "first": {"instruction": "Step one.\n"},
            "second": {"instruction": "Step two.\n", "test": MENTIONS_REWARD_IN_COMMENT},
        },
    )
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "tasks").status == "pass"
    assert _finding(outcome, "reward").status == "fail"


async def test_a_windows_task_needing_test_bat_is_not_a_failure(tmp_path):
    dataset = tmp_path / "evals" / "validation"
    write_task(
        dataset / "task-0",
        task_toml='\n[environment]\nos = "windows"\n',
        test_script="@echo off\r\necho 1 > /logs/verifier/reward.txt\r\n",
        test_name="test.bat",
    )
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "tasks").status == "pass"
    assert _finding(outcome, "reward").status == "pass"


async def test_a_task_graded_in_a_separate_verifier_image_needs_no_host_script(tmp_path):
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0", task_toml='\n[verifier]\nenvironment_mode = "separate"\n', test_script=None)
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "tasks").status == "pass"
    reward = _finding(outcome, "reward")
    assert reward.status == "pass"
    assert "separate verifier image" in reward.message


async def test_a_task_naming_a_prebuilt_image_needs_no_dockerfile(tmp_path):
    dataset = tmp_path / "evals" / "validation"
    task = write_task(dataset / "task-0", task_toml='\n[environment]\ndocker_image = "ubuntu:24.04"\n')
    (task / "environment" / "Dockerfile").unlink()
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "tasks").status == "pass"


async def test_required_host_variables_are_recorded_with_their_defaults(tmp_path):
    dataset = tmp_path / "evals" / "validation"
    write_task(
        dataset / "task-0",
        task_toml='\n[environment.env]\nHF_TOKEN = "${HF_TOKEN}"\nREGION = "${AWS_REGION:-us-west-2}"\n',
    )
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    recorded = {item.name: item.default for item in outcome.required_env_vars}
    assert recorded == {"HF_TOKEN": None, "AWS_REGION": "us-west-2"}
    # Discover records what the repo demands; whether this host has it is doctor's job.
    assert _finding(outcome, "credentials").status == "pass"


async def test_a_repo_wrapper_is_imported_and_sys_path_is_left_alone(tmp_path):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    write_wrapper(tmp_path, class_name="TicketTriageAgent")
    candidate = _candidate(
        {
            "agents": [{"import_path": "harbor_wrapper:TicketTriageAgent"}],
            "datasets": [{"path": str(dataset)}],
        }
    )
    before = list(sys.path)

    outcome = await validate.run_ladder(candidate, tmp_path)

    agent = _finding(outcome, "agent")
    assert agent.status == "pass"
    assert "subclasses BaseAgent" in agent.message
    assert sys.path == before, "the wrapper's directory must not be left on sys.path"


async def test_a_second_repos_wrapper_is_not_shadowed_by_the_first(tmp_path):
    """``harbor_wrapper`` is a convention, so two repos claim the same module name."""
    first, second = tmp_path / "first", tmp_path / "second"
    for repo, class_name in ((first, "FirstAgent"), (second, "SecondAgent")):
        write_dataset(repo / "evals" / "validation", count=1)
        write_wrapper(repo, class_name=class_name)

    for repo, class_name in ((first, "FirstAgent"), (second, "SecondAgent")):
        candidate = _candidate(
            {
                "agents": [{"import_path": f"harbor_wrapper:{class_name}"}],
                "datasets": [{"path": str(repo / "evals/validation")}],
            }
        )
        outcome = await validate.run_ladder(candidate, repo)
        assert _finding(outcome, "agent").status == "pass", f"{class_name} was shadowed by a cached module"


async def test_a_wrapper_that_is_not_an_agent_fails_the_agent_rung(tmp_path):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    (tmp_path / "harbor_wrapper.py").write_text("class NotAnAgent:\n    pass\n")
    candidate = _candidate(
        {"agents": [{"import_path": "harbor_wrapper:NotAnAgent"}], "datasets": [{"path": str(dataset)}]}
    )

    outcome = await validate.run_ladder(candidate, tmp_path)

    agent = _finding(outcome, "agent")
    assert agent.status == "fail"
    assert agent.harbor_call == "import_class"


async def test_an_unknown_builtin_agent_name_lists_the_valid_ones(tmp_path):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    candidate = _candidate({"agents": [{"name": "not-an-agent"}], "datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    agent = _finding(outcome, "agent")
    assert agent.status == "fail"
    assert agent.hint is not None and "oracle" in agent.hint


async def test_the_persisted_config_is_checked_through_the_harbor_cli(tmp_path):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    config_path = tmp_path / "harbor-job.yaml"
    config_path.write_text(f"datasets:\n- path: {dataset}\n")

    finding = validate.check_persisted_config(config_path, tmp_path)

    assert finding.status in {"pass", "warn"}
    if finding.status == "pass":
        assert finding.harbor_call == "harbor job start --print-config"


async def test_a_config_the_cli_rejects_fails_the_round_trip(tmp_path):
    config_path = tmp_path / "harbor-job.yaml"
    config_path.write_text("datasets: not-a-list\n")

    finding = validate.check_persisted_config(config_path, tmp_path)

    if finding.status != "warn":  # warn means no harbor executable on PATH
        assert finding.status == "fail"
        assert finding.path == config_path


async def test_the_full_pipeline_agrees_with_the_source_it_chose(tmp_path):
    """Sources and the ladder have to compose: what was assembled is what gets validated."""
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path)

    candidate, _ = sources.find_candidate(tmp_path, env_backend="docker")
    assert candidate is not None
    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _repo_failures(outcome) == []
    assert outcome.config is not None
    assert outcome.config.agents[0].import_path == "harbor_wrapper:WrappedAgent"
