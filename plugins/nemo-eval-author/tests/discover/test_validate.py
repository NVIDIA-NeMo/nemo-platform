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

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import ClassVar

from harbor_fixtures import (
    MENTIONS_REWARD_IN_COMMENT,
    WRITES_REWARD,
    write_dataset,
    write_task,
    write_wrapper,
)
from nemo_eval_author_plugin.discovery import sources, validate
from nemo_eval_author_plugin.discovery.models import CandidateConfig, ConfigSource


def _candidate(data: dict, agent_search_path: str | None = None) -> CandidateConfig:
    return CandidateConfig(
        data=data,
        source=ConfigSource(kind="config_file", detail="test fixture"),
        agent_search_path=agent_search_path,
    )


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


async def test_only_a_verdict_harbor_returned_claims_a_harbor_call(tmp_path):
    """``harbor_call`` is what tells a reader a finding is as true as the run would be.

    The reward advisory reads the test scripts itself, so it must not carry one. Naming a
    Harbor API there would dress a text search up as something Harbor vouched for.
    """
    write_dataset(tmp_path / "evals" / "validation", count=1)
    candidate = _candidate({"datasets": [{"path": str(tmp_path / "evals/validation")}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "reward").harbor_call is None
    judged_by_harbor = [item for item in outcome.findings if item.name != "reward"]
    assert judged_by_harbor and all(item.harbor_call for item in judged_by_harbor)


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


async def test_a_harbor_that_stopped_exposing_its_resolved_tasks_does_not_blame_the_repo(tmp_path, monkeypatch):
    """``Job._task_configs`` is private, so a Harbor upgrade is allowed to rename it.

    Reading an absent attribute as zero tasks would report "the config resolves to zero tasks"
    under a hint quoting a Harbor error Harbor never raised, about a repo whose tasks are fine.
    An incompatibility of ours has to read as ours.
    """
    write_dataset(tmp_path / "evals" / "validation", count=1)
    candidate = _candidate({"datasets": [{"path": str(tmp_path / "evals/validation")}]})

    class _JobWithoutTaskConfigs:
        @classmethod
        async def create(cls, config):
            return cls()

    monkeypatch.setattr(validate, "Job", _JobWithoutTaskConfigs)

    outcome = await validate.run_ladder(candidate, tmp_path)

    compatibility = _finding(outcome, "compatibility")
    assert compatibility.status == "fail"
    assert "Job._task_configs" in compatibility.message
    assert not any(item.name == "tasks" for item in outcome.findings), "no verdict on tasks was available"
    assert not any("zero tasks" in item.message for item in outcome.findings)


async def test_a_config_that_really_resolves_no_tasks_is_still_the_repo_s_failure(tmp_path, monkeypatch):
    """The companion case: present but empty is a repo Harbor found nothing in, and it must still fail.

    Absent and empty mean opposite things, so this pins the distinction from the side that
    would be lost if the attribute check were ever relaxed back to a falsy one.
    """
    candidate = _candidate({"datasets": [{"path": str(write_dataset(tmp_path / "evals" / "validation", count=1))}]})

    class _JobWithNoTasks:
        _task_configs: ClassVar[list] = []

        @classmethod
        async def create(cls, config):
            return cls()

    monkeypatch.setattr(validate, "Job", _JobWithNoTasks)

    outcome = await validate.run_ladder(candidate, tmp_path)

    tasks = _finding(outcome, "tasks")
    assert tasks.status == "fail"
    assert "zero tasks" in tasks.message
    assert not any(item.name == "compatibility" for item in outcome.findings)


async def test_a_task_harbor_silently_skips_is_reported(tmp_path):
    """Harbor drops a directory it cannot parse without raising.

    Nothing else in the ladder catches this: the tasks rung only sees what Harbor
    resolved, so it reports one of one valid while the repo holds two. The run would then
    score half the suite and look complete doing it.
    """
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0")
    write_task(dataset / "task-1", instruction=None)
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "tasks").message.startswith("1 of 1"), "the tasks rung cannot see the dropped one"
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


async def test_a_scaffolded_task_that_never_names_a_reward_is_flagged_without_blocking(tmp_path):
    """Harbor's own template mentions the reward file only in a comment.

    Worth saying, because the trial would run and then raise. Not worth failing over: the
    check is a text search, and a script that builds the path in a variable looks identical
    to one that writes nothing.
    """
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1, test_script=MENTIONS_REWARD_IN_COMMENT)
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    reward = _finding(outcome, "reward")
    assert reward.status == "warn"
    assert _repo_failures(outcome) == [], "a heuristic must not block a repo Harbor accepted"
    assert _finding(outcome, "tasks").status == "pass", "the task is structurally fine; only its scoring is doubtful"
    assert reward.hint is not None and "RewardFileNotFoundError" in reward.hint


async def test_a_reward_written_through_a_variable_is_not_called_a_failure(tmp_path):
    """The false negative that makes this check unfit to gate on: the script does score."""
    dataset = write_dataset(
        tmp_path / "evals" / "validation",
        count=1,
        test_script='#!/bin/bash\nOUT=/logs/verifier\nprintf 1 > "$OUT/reward.$(echo txt)"\n',
    )
    candidate = _candidate({"datasets": [{"path": str(dataset)}]})

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "reward").status == "warn"
    assert _repo_failures(outcome) == []


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
    assert _finding(outcome, "reward").status == "warn"


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
    assert _finding(outcome, "reward").status == "pass", "an image-graded task ships no host script to read"


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
        },
        agent_search_path=".",
    )
    before = list(sys.path)

    outcome = await validate.run_ladder(candidate, tmp_path)

    agent = _finding(outcome, "agent")
    assert agent.status == "pass"
    assert "TicketTriageAgent" in agent.message
    assert sys.path == before, "the wrapper's directory must not be left on sys.path"


async def test_the_agent_rung_imports_only_from_the_search_path_the_artifact_records(tmp_path):
    """The rung has to fail wherever the recorded command would.

    Harbor imports through ``importlib`` and adds nothing to ``sys.path``, so a bare
    ``harbor_wrapper:...`` resolves only from the directory the artifact tells a run to
    export. A rung that goes looking for the file itself passes for a reason
    ``harbor job start -c`` will not have, and that is precisely how an unimportable config
    came to be published as runnable.
    """
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    write_wrapper(tmp_path / "src" / "myagent")
    data = {"agents": [{"import_path": "harbor_wrapper:WrappedAgent"}], "datasets": [{"path": str(dataset)}]}

    reachable = await validate.run_ladder(_candidate(data, agent_search_path="src/myagent"), tmp_path)
    assert _finding(reachable, "agent").status == "pass"

    unreachable = await validate.run_ladder(_candidate(data, agent_search_path="."), tmp_path)
    agent = _finding(unreachable, "agent")
    assert agent.status == "fail"
    assert "No module named 'harbor_wrapper'" in agent.message
    # The directory that would work is named, since the whole point is to be actionable.
    assert agent.hint is not None and "PYTHONPATH=src/myagent" in agent.hint


async def test_an_agent_import_with_no_recorded_search_path_gets_no_help_finding_it(tmp_path):
    """A config the repo maintains is validated with the environment a bare ``harbor`` has.

    Nothing about that config says where its module lives, so an import that only works
    because discovery went hunting for the file is a verdict about this process rather than
    about the run.
    """
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    write_wrapper(tmp_path)
    candidate = _candidate(
        {"agents": [{"import_path": "harbor_wrapper:WrappedAgent"}], "datasets": [{"path": str(dataset)}]}
    )

    outcome = await validate.run_ladder(candidate, tmp_path)

    agent = _finding(outcome, "agent")
    assert agent.status == "fail"
    assert agent.hint is not None and "PYTHONPATH=." in agent.hint


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
            },
            agent_search_path=".",
        )
        outcome = await validate.run_ladder(candidate, repo)
        assert _finding(outcome, "agent").status == "pass", f"{class_name} was shadowed by a cached module"


async def test_a_module_left_in_sys_modules_cannot_stand_in_for_a_missing_one(tmp_path):
    """Eviction is what keeps the rung honest once nothing is added to the path.

    With the search path narrowed to one directory, a stale ``harbor_wrapper`` from an earlier
    repo is the only way an unimportable config could still pass — the exact false verdict
    this rung exists to prevent.
    """
    first, second = tmp_path / "first", tmp_path / "second"
    for repo in (first, second):
        write_dataset(repo / "evals" / "validation", count=1)
    write_wrapper(first)

    def candidate(repo):
        return _candidate(
            {
                "agents": [{"import_path": "harbor_wrapper:WrappedAgent"}],
                "datasets": [{"path": str(repo / "evals/validation")}],
            },
            agent_search_path=".",
        )

    assert _finding(await validate.run_ladder(candidate(first), first), "agent").status == "pass"

    outcome = await validate.run_ladder(candidate(second), second)

    assert _finding(outcome, "agent").status == "fail", "the first repo's module answered for the second"
    assert "harbor_wrapper" not in sys.modules


async def test_a_wrapper_that_is_not_an_agent_is_a_warning_rather_than_a_failure(tmp_path):
    """Harbor's own agent gate passes this, so failing it would block a repo Harbor runs.

    ``harbor/agents/factory.py`` calls ``import_class(import_path, label="agent")`` with no
    ``base`` — strict for verifiers, deliberately not for agents. Still worth saying: the run
    starts and then dies at trial time on a method the class does not have.
    """
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    (tmp_path / "harbor_wrapper.py").write_text("class NotAnAgent:\n    pass\n")
    candidate = _candidate(
        {"agents": [{"import_path": "harbor_wrapper:NotAnAgent"}], "datasets": [{"path": str(dataset)}]},
        agent_search_path=".",
    )

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _finding(outcome, "agent").status == "pass"
    base = _finding(outcome, "agent-base")
    assert base.status == "warn"
    assert base.harbor_call is None, "Harbor does not make this judgement, so it cannot be credited with it"
    assert _repo_failures(outcome) == []


async def test_an_import_path_naming_something_that_is_not_a_class_still_fails(tmp_path):
    """The one thing ``import_class`` enforces without a ``base``, so it stays a failure."""
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    (tmp_path / "harbor_wrapper.py").write_text("def not_a_class():\n    return None\n")
    candidate = _candidate(
        {"agents": [{"import_path": "harbor_wrapper:not_a_class"}], "datasets": [{"path": str(dataset)}]},
        agent_search_path=".",
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

    finding = validate.check_config_file(config_path, tmp_path)

    assert finding.status in {"pass", "warn"}
    if finding.status == "pass":
        assert finding.harbor_call == "harbor job start --print-config"


async def test_a_config_the_cli_rejects_fails_the_round_trip(tmp_path):
    config_path = tmp_path / "harbor-job.yaml"
    config_path.write_text("datasets: not-a-list\n")

    finding = validate.check_config_file(config_path, tmp_path)

    if finding.status != "warn":  # warn means no harbor executable on PATH
        assert finding.status == "fail"
        assert finding.path == config_path


async def test_the_round_trip_uses_the_harbor_that_produced_every_other_verdict(tmp_path):
    """A ``uv tool`` or ``pipx`` install shadows the environment's own console script.

    The report stamps one Harbor version, so a round trip resolved off bare ``PATH`` can
    contradict the rest of the ladder while claiming to agree with it.
    """
    resolved = validate._harbor_executable()

    assert resolved is not None, "the environment running these tests installs harbor"
    assert Path(resolved).parent == Path(sys.executable).parent
    completed = subprocess.run([resolved, "--version"], capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == version("harbor"), "the CLI and the imported package must be one Harbor"


async def test_the_full_pipeline_agrees_with_the_source_it_chose(tmp_path):
    """Sources and the ladder have to compose: what was assembled is what gets validated."""
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path)

    candidate, _ = sources.find_candidate(tmp_path)
    assert candidate is not None
    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _repo_failures(outcome) == []
    assert outcome.config is not None
    assert outcome.config.agents[0].import_path == "harbor_wrapper:WrappedAgent"


async def test_the_full_pipeline_carries_a_nested_wrapper_s_search_path_through_the_ladder(tmp_path):
    """The case the bare import path dropped on the floor.

    ``_find_wrapper`` walks the repo, so the wrapper it finds need not be at the root, and the
    emitted ``harbor_wrapper:WrappedAgent`` says nothing about where it was. Assembly and the
    ladder have to agree on the directory or the ladder is judging a different config.
    """
    write_dataset(tmp_path / "evals" / "validation", count=1)
    write_wrapper(tmp_path / "src" / "myagent")

    candidate, _ = sources.find_candidate(tmp_path)
    assert candidate is not None
    assert candidate.agent_search_path == "src/myagent"

    outcome = await validate.run_ladder(candidate, tmp_path)

    assert _repo_failures(outcome) == []
    assert _finding(outcome, "agent").status == "pass"
