# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Focused Harbor preflight contract tests."""

import subprocess
import sys
from pathlib import Path

import pytest
from harbor.utils.logger import logger as harbor_logger
from harbor_fixtures import write_dataset, write_task, write_wrapper
from nemo_eval_author_plugin.discovery import scan, validate


def _candidate(path: Path, data: dict) -> scan.ConfigCandidate:
    return scan.ConfigCandidate(path=path, data=data)


def _check(outcome: validate.ValidationOutcome, name: str):
    matches = [item for item in outcome.checks if item.name == name]
    assert matches, f"no {name!r} check in {[item.name for item in outcome.checks]}"
    return matches[0]


def _patch_external_preflight(monkeypatch) -> None:
    monkeypatch.setattr(validate.EnvironmentFactory, "run_preflight", lambda *args: None)
    monkeypatch.setattr(
        validate,
        "check_config_file",
        lambda path, root: validate._check("round-trip", "pass", "The config file loads through the Harbor CLI"),
    )


async def test_a_well_formed_repo_passes_the_ladder(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation")
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml", {"agents": [{"name": "oracle"}], "datasets": [{"path": str(dataset)}]}
        ),
        tmp_path,
    )

    assert not [check for check in outcome.checks if check.status == "fail"]
    assert {check.name for check in outcome.checks} == {
        "schema",
        "resolution",
        "agent",
        "backend",
        "round-trip",
        "tasks",
        "coverage",
        "credentials",
    }
    assert _check(outcome, "tasks").message.startswith("2 of 2")
    assert _check(outcome, "coverage").status == "pass"


async def test_ladder_closes_added_harbor_logger_handlers(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation")
    _patch_external_preflight(monkeypatch)
    handlers_before = tuple(harbor_logger.handlers)

    await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"agents": [{"name": "oracle"}], "datasets": [{"path": str(dataset)}]},
        ),
        tmp_path,
    )

    assert tuple(harbor_logger.handlers) == handlers_before


async def test_schema_failure_stops_the_ladder(tmp_path):
    outcome = await validate.run_ladder(_candidate(tmp_path / "harbor-job.yaml", {"datasets": "not-a-list"}), tmp_path)

    assert _check(outcome, "schema").status == "fail"
    assert [item.name for item in outcome.checks] == ["schema"]


async def test_resolution_failure_reports_the_real_error(tmp_path, monkeypatch):
    _patch_external_preflight(monkeypatch)
    outcome = await validate.run_ladder(
        _candidate(tmp_path / "harbor-job.yaml", {"datasets": [{"path": str(tmp_path / "nope")}]}), tmp_path
    )

    finding = _check(outcome, "resolution")
    assert finding.status == "fail"
    assert "nope" in finding.message


async def test_missing_resolved_task_attribute_is_a_compatibility_failure(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    _patch_external_preflight(monkeypatch)

    class _JobWithoutTaskConfigs:
        @classmethod
        async def create(cls, _config):
            return cls()

        def _close_logger_handlers(self):
            pass

    monkeypatch.setattr(validate, "Job", _JobWithoutTaskConfigs)
    outcome = await validate.run_ladder(
        _candidate(tmp_path / "harbor-job.yaml", {"datasets": [{"path": str(dataset)}]}), tmp_path
    )

    assert _check(outcome, "compatibility").status == "fail"
    assert "Job._task_configs" in _check(outcome, "compatibility").message


async def test_invalid_resolved_task_fails_tasks_check(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    _patch_external_preflight(monkeypatch)
    create_job = validate.Job.create

    async def resolve_then_invalidate(config):
        job = await create_job(config)
        monkeypatch.setattr(validate.Task, "is_valid_dir", lambda _path: False)
        return job

    monkeypatch.setattr(validate.Job, "create", staticmethod(resolve_then_invalidate))

    outcome = await validate.run_ladder(
        _candidate(tmp_path / "harbor-job.yaml", {"datasets": [{"path": str(dataset)}]}), tmp_path
    )

    assert _check(outcome, "tasks").status == "fail"


async def test_silent_task_drop_fails_concrete_coverage(tmp_path, monkeypatch):
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0")
    write_task(dataset / "task-1", instruction=None)
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(tmp_path / "harbor-job.yaml", {"datasets": [{"path": str(dataset)}]}), tmp_path
    )

    assert _check(outcome, "coverage").status == "fail"
    assert "task-1" in _check(outcome, "coverage").message


async def test_empty_task_names_does_not_make_a_dropped_task_advisory(tmp_path, monkeypatch):
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0")
    write_task(dataset / "task-1", instruction=None)
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"datasets": [{"path": str(dataset), "task_names": []}]},
        ),
        tmp_path,
    )

    coverage = _check(outcome, "coverage")
    assert (coverage.status, coverage.severity) == ("fail", "required")
    assert "task-1" in coverage.message
    assert coverage.hint == "Harbor skips these task dirs silently."


async def test_malformed_explicit_task_name_fails_coverage(tmp_path, monkeypatch):
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0")
    write_task(dataset / "task-1", instruction=None)
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"datasets": [{"path": str(dataset), "task_names": ["task-0", "task-1"]}]},
        ),
        tmp_path,
    )

    assert (_check(outcome, "coverage").status, _check(outcome, "coverage").severity) == ("fail", "required")
    assert "task-1" in _check(outcome, "coverage").message


async def test_excluded_task_drop_is_advisory(tmp_path, monkeypatch):
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0")
    write_task(dataset / "task-1", instruction=None)
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"datasets": [{"path": str(dataset), "exclude_task_names": ["task-1"]}]},
        ),
        tmp_path,
    )

    assert (_check(outcome, "coverage").status, _check(outcome, "coverage").severity) == ("warn", "advisory")


async def test_non_excluded_invalid_task_fails_coverage_with_exclude_filter(tmp_path, monkeypatch):
    dataset = tmp_path / "evals" / "validation"
    write_task(dataset / "task-0")
    write_task(dataset / "task-excluded")
    write_task(dataset / "task-invalid", instruction=None)
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"datasets": [{"path": str(dataset), "exclude_task_names": ["task-excluded"]}]},
        ),
        tmp_path,
    )

    coverage = _check(outcome, "coverage")
    assert (coverage.status, coverage.severity) == ("fail", "required")
    assert "task-invalid" in coverage.message
    assert "task-excluded" not in coverage.message
    assert coverage.hint == "Harbor skipped a task selected by the dataset filters."


async def test_n_tasks_subset_drop_is_advisory(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation")
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"datasets": [{"path": str(dataset), "n_tasks": 1}]},
        ),
        tmp_path,
    )

    assert (_check(outcome, "coverage").status, _check(outcome, "coverage").severity) == ("warn", "advisory")


async def test_required_host_variables_are_recorded(tmp_path, monkeypatch):
    dataset = tmp_path / "evals" / "validation"
    write_task(
        dataset / "task-0",
        task_toml='\n[environment.env]\nHF_TOKEN = "${HF_TOKEN}"\nREGION = "${AWS_REGION:-us-west-2}"\n',
    )
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(tmp_path / "harbor-job.yaml", {"datasets": [{"path": str(dataset)}]}), tmp_path
    )

    assert {item.name: item.default for item in outcome.required_env_vars} == {
        "HF_TOKEN": None,
        "AWS_REGION": "us-west-2",
    }
    assert _check(outcome, "credentials").status == "pass"


async def test_missing_custom_agent_import_is_recorded(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    write_wrapper(tmp_path)
    monkeypatch.setattr(sys, "path", [path for path in sys.path if path not in {"", str(tmp_path)}])
    monkeypatch.delitem(sys.modules, "harbor_wrapper", raising=False)
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"agents": [{"import_path": "harbor_wrapper:WrappedAgent"}], "datasets": [{"path": str(dataset)}]},
        ),
        tmp_path,
    )

    assert _check(outcome, "agent").status == "fail"


async def test_non_class_custom_agent_import_is_recorded(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    (tmp_path / "invalid_wrapper.py").write_text("def not_a_class():\n    return None\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    _patch_external_preflight(monkeypatch)

    outcome = await validate.run_ladder(
        _candidate(
            tmp_path / "harbor-job.yaml",
            {"agents": [{"import_path": "invalid_wrapper:not_a_class"}], "datasets": [{"path": str(dataset)}]},
        ),
        tmp_path,
    )

    assert _check(outcome, "agent").status == "fail"


def test_custom_agent_import_system_exit_is_recorded(monkeypatch):
    config = validate.JobConfig.model_validate({"agents": [{"import_path": "agent_module:Agent"}]})
    outcome = validate.ValidationOutcome()

    def exit_import(*_args, **_kwargs):
        raise SystemExit("agent stopped")

    monkeypatch.setattr(validate, "import_class", exit_import)

    validate._check_agent(config, outcome)

    assert (_check(outcome, "agent").status, _check(outcome, "agent").message) == (
        "fail",
        "Cannot import agent agent_module:Agent: SystemExit: agent stopped",
    )


def test_custom_agent_import_keyboard_interrupt_propagates(monkeypatch):
    config = validate.JobConfig.model_validate({"agents": [{"import_path": "agent_module:Agent"}]})
    outcome = validate.ValidationOutcome()

    def interrupt_import(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(validate, "import_class", interrupt_import)

    with pytest.raises(KeyboardInterrupt):
        validate._check_agent(config, outcome)


async def test_custom_agent_import_does_not_reuse_another_repositorys_module(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    _patch_external_preflight(monkeypatch)
    for repo, class_name in ((first, "FirstAgent"), (second, "SecondAgent")):
        dataset = write_dataset(repo / "evals" / "validation", count=1)
        write_wrapper(repo, class_name=class_name)
        monkeypatch.syspath_prepend(str(repo))
        outcome = await validate.run_ladder(
            _candidate(
                repo / "harbor-job.yaml",
                {
                    "agents": [{"import_path": f"harbor_wrapper:{class_name}"}],
                    "datasets": [{"path": str(dataset)}],
                },
            ),
            repo,
        )
        assert _check(outcome, "agent").status == "pass"


async def test_backend_failure_is_recorded(tmp_path, monkeypatch):
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1)
    _patch_external_preflight(monkeypatch)
    monkeypatch.setattr(
        validate.EnvironmentFactory,
        "run_preflight",
        lambda *args: (_ for _ in ()).throw(RuntimeError("no Docker")),
    )

    outcome = await validate.run_ladder(
        _candidate(tmp_path / "harbor-job.yaml", {"datasets": [{"path": str(dataset)}]}), tmp_path
    )

    assert _check(outcome, "backend").status == "fail"


def test_config_file_round_trip_runs_harbor_cli(tmp_path, monkeypatch):
    config_path = tmp_path / "harbor-job.yaml"
    config_path.write_text("datasets: []\n", encoding="utf-8")
    monkeypatch.setattr(validate, "_harbor_executable", lambda: "harbor")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs["cwd"]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)

    assert validate.check_config_file(config_path, tmp_path).status == "pass"
    assert calls == [(["harbor", "job", "start", "--print-config", "-c", str(config_path)], tmp_path)]


def test_config_file_round_trip_reports_harbor_rejection(tmp_path, monkeypatch):
    config_path = tmp_path / "harbor-job.yaml"
    config_path.write_text("datasets: []\n", encoding="utf-8")
    monkeypatch.setattr(validate, "_harbor_executable", lambda: "harbor")

    def reject(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "invalid config\n")

    monkeypatch.setattr(subprocess, "run", reject)

    finding = validate.check_config_file(config_path, tmp_path)

    assert (finding.status, finding.message) == ("fail", "The Harbor CLI rejected the config: invalid config.")
