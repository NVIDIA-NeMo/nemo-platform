# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discovery report contract tests."""

import shlex
from datetime import UTC, datetime

from harbor_fixtures import read_front_matter
from nemo_eval_author_plugin.discovery import report, scan, validate
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


_TRACE_CHECK = scan._check("traces", "pass", "Trace sessions exist.", severity="advisory")


def _config(
    root,
    *,
    path: str = "configs/eval.yaml",
    name: str = "evaluation",
    checks: list[CheckResult] | None = None,
):
    root = root.resolve()
    return report.ConfigReport(
        name=name,
        path=root / path,
        required_env_vars=[
            RequiredEnvVar(name="HF_TOKEN", default=None, declared_in=root / "evals" / "validation" / "task.toml")
        ],
        checks=checks if checks is not None else [_check()],
    )


def _record(tmp_path, *, configs=None, repository_checks: list[CheckResult] | None = None):
    root = tmp_path.resolve()
    return report.DiscoveryReport(
        agent="ticket-triage",
        workspace="default",
        repo_root=root,
        configs=[_config(root)] if configs is None else configs,
        dataset_paths=[root / "evals" / "validation"],
        ethos_path="ETHOS.md",
        harbor_version="0.18.0",
        discovered_at=datetime(2026, 8, 10, 15, tzinfo=UTC),
        fingerprint="sha256:abc123",
        input_file_count=4,
        repository_checks=repository_checks or [],
        trace_check=_TRACE_CHECK,
    )


def test_front_matter_records_the_complete_repository_contract(tmp_path):
    check = _check()
    record = _record(tmp_path, configs=[_config(tmp_path, checks=[check])])

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front == {
        "schema_version": 1,
        "agent": "ticket-triage",
        "workspace": "default",
        "repo_root": str(tmp_path.resolve()),
        "runnable": True,
        "configs": [{"name": "evaluation", "path": "configs/eval.yaml"}],
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
        "checks": [check.model_dump(mode="json"), _TRACE_CHECK.model_dump(mode="json")],
    }
    assert format_report([check]) in markdown


def test_a_rejected_config_is_blocked_and_has_no_command(tmp_path):
    failure = _check("resolution", "fail", "Harbor could not resolve the job.")
    record = _record(tmp_path, configs=[_config(tmp_path, checks=[_check(), failure])])

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front["runnable"] is False
    assert front["run_command"] is None
    assert "harbor job start" not in markdown
    assert failure.message in markdown


def test_a_report_without_a_repository_config_is_not_runnable(tmp_path):
    record = _record(
        tmp_path,
        configs=[],
        repository_checks=[_check("config", "fail", "No repository-owned Harbor config file exists.")],
    )

    front = read_front_matter(report.render_markdown(record))

    assert front["runnable"] is False
    assert front["config_path"] is None
    assert front["run_command"] is None


def test_the_run_command_changes_to_the_repo_and_quotes_shell_paths(tmp_path):
    repo = tmp_path / "repo $(touch unsafe); name"
    record = _record(
        repo,
        configs=[_config(repo, path="configs/eval $(touch unsafe); suite.yaml")],
    )

    cd_command, harbor_command = record.run_command.split(" && ")
    assert shlex.split(cd_command) == ["cd", str(repo.resolve())]
    assert shlex.split(harbor_command) == [
        "harbor",
        "job",
        "start",
        "-c",
        "configs/eval $(touch unsafe); suite.yaml",
    ]


def test_multi_config_report_uses_names_paths_stable_sections_and_one_command_each(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    candidates = [
        scan.ConfigCandidate(root / "a.yaml", {"job_name": "shared", "tasks": ["a"]}),
        scan.ConfigCandidate(root / "nested" / "b.yml", {"job_name": "shared", "tasks": ["b"]}),
        scan.ConfigCandidate(root / "nested" / "fallback.json", {"job_name": "  ", "tasks": ["c"]}),
    ]
    scan_result = scan.RepositoryScan(
        configs=candidates,
        dataset_paths=[],
        ethos_path=None,
        fingerprint="abc123",
        input_file_count=3,
        checks=[_check("config", "pass", "Found 3 repository-owned Harbor config files.")],
    )
    validations = [
        validate.ValidationOutcome(checks=[_check("schema", "pass", f"Schema {index} passed.")]) for index in range(3)
    ]
    trace_check = scan._check("traces", "warn", "No traces exist.", severity="advisory")
    monkeypatch.setattr(report, "harbor_version", lambda: "0.18.0")

    record = report.build_report(
        agent="ticket-triage",
        workspace="default",
        repo_root=root,
        scan_result=scan_result,
        validations=validations,
        trace_check=trace_check,
    )
    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert front["configs"] == [
        {"name": "shared", "path": "a.yaml"},
        {"name": "shared", "path": "nested/b.yml"},
        {"name": "fallback.json", "path": "nested/fallback.json"},
    ]
    assert (front["runnable"], front["config_path"], front["run_command"]) == (True, None, None)
    headings = [
        "### `shared` (`a.yaml`)",
        "### `shared` (`nested/b.yml`)",
        "### `fallback.json` (`nested/fallback.json`)",
    ]
    positions = [markdown.index(heading) for heading in headings]
    assert positions == sorted(positions)
    for index, (position, candidate) in enumerate(zip(positions, candidates, strict=True)):
        end = positions[index + 1] if index + 1 < len(positions) else len(markdown)
        section = markdown[position:end]
        assert f"Schema {index} passed." in section
        assert f"harbor job start -c {candidate.path.relative_to(root).as_posix()}" in section
    assert markdown.count("harbor job start -c") == 3


def test_multi_config_report_is_not_runnable_when_one_config_fails(tmp_path):
    failure = _check("schema", "fail", "Harbor rejected one config.")
    record = _record(
        tmp_path,
        configs=[
            _config(tmp_path, path="first.yaml", name="first", checks=[failure]),
            _config(tmp_path, path="second.yaml", name="second"),
        ],
    )

    markdown = report.render_markdown(record)
    front = read_front_matter(markdown)

    assert (front["runnable"], front["config_path"], front["run_command"]) == (False, None, None)
    assert "harbor job start -c first.yaml" not in markdown
    assert "harbor job start -c second.yaml" in markdown
