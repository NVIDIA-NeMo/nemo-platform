# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discovery report contract tests."""

import shlex
from datetime import UTC, datetime

from harbor_fixtures import read_front_matter
from nemo_eval_author_plugin.discovery import report
from nemo_eval_author_plugin.discovery.validate import RequiredEnvVar
from nemo_insights_plugin.contracts.checks import CheckResult, CheckStatus, format_report


def _check(name: str = "config", status: CheckStatus = "pass", message: str = "Found the config.") -> CheckResult:
    return CheckResult(
        name=name,
        group="repository" if name == "config" else "validation",
        status=status,
        severity="required",
        message=message,
    )


def _record(tmp_path, *, config: bool = True, checks: list[CheckResult] | None = None):
    root = tmp_path.resolve()
    return report.DiscoveryReport(
        agent="ticket-triage",
        workspace="default",
        repo_root=root,
        config_path=root / "configs" / "eval.yaml" if config else None,
        dataset_paths=[root / "evals" / "validation"],
        ethos_path="ETHOS.md",
        harbor_version="0.18.0",
        required_env_vars=[
            RequiredEnvVar(name="HF_TOKEN", default=None, declared_in=root / "evals" / "validation" / "task.toml")
        ],
        discovered_at=datetime(2026, 8, 10, 15, tzinfo=UTC),
        fingerprint="sha256:abc123",
        input_file_count=4,
        checks=checks or [_check()],
    )


def test_front_matter_records_the_complete_repository_contract(tmp_path):
    check = _check()
    record = _record(tmp_path, checks=[check])

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front == {
        "schema_version": 1,
        "agent": "ticket-triage",
        "workspace": "default",
        "repo_root": str(tmp_path.resolve()),
        "runnable": True,
        "config_path": "configs/eval.yaml",
        "dataset_paths": ["evals/validation"],
        "run_command": f"cd {shlex.quote(str(tmp_path.resolve()))} && harbor job start -c configs/eval.yaml",
        "ethos_path": "ETHOS.md",
        "harbor_version": "0.18.0",
        "required_env_vars": [
            {
                "name": "HF_TOKEN",
                "default": None,
                "declared_in": "evals/validation/task.toml",
            }
        ],
        "discovered_at": "2026-08-10T15:00:00+00:00",
        "fingerprint": "sha256:abc123",
        "input_file_count": 4,
        "checks": [check.model_dump(mode="json")],
    }
    assert format_report([check]) in markdown


def test_a_rejected_config_is_blocked_and_has_no_command(tmp_path):
    failure = _check("resolution", "fail", "Harbor could not resolve the job.")
    record = _record(tmp_path, checks=[_check(), failure])

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front["runnable"] is False
    assert front["run_command"] is None
    assert "harbor job start" not in markdown
    assert failure.message in markdown


def test_a_report_without_a_repository_config_is_not_runnable(tmp_path):
    record = _record(
        tmp_path,
        config=False,
        checks=[_check("config", "fail", "No repository-owned Harbor config file exists.")],
    )

    front = read_front_matter(report.render_markdown(record))

    assert front["runnable"] is False
    assert front["config_path"] is None
    assert front["run_command"] is None


def test_the_run_command_changes_to_the_repo_and_quotes_shell_paths(tmp_path):
    repo = tmp_path / "repo $(touch unsafe); name"
    record = _record(repo)
    record.config_path = repo.resolve() / "configs" / "eval $(touch unsafe); suite.yaml"

    cd_command, harbor_command = record.run_command.split(" && ")
    assert shlex.split(cd_command) == ["cd", str(repo.resolve())]
    assert shlex.split(harbor_command) == [
        "harbor",
        "job",
        "start",
        "-c",
        "configs/eval $(touch unsafe); suite.yaml",
    ]
