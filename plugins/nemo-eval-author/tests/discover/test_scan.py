# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repository scan contract tests."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from nemo_eval_author_plugin.discovery import scan


def _config(path: Path, text: str = "datasets:\n- path: evals\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _task(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "task.toml").write_text('version = "1.0"\n', encoding="utf-8")


def test_selects_the_first_config_and_warns_about_extras(tmp_path):
    first = _config(tmp_path / "configs" / "a.yaml")
    _config(tmp_path / "harbor" / "b.yaml")

    result = scan.scan_repository(tmp_path)

    assert result.config is not None
    assert result.config.path == first
    assert {check.status for check in result.checks if check.name == "config"} == {"pass", "warn"}
    assert any(check.name == "ethos" and check.status == "warn" for check in result.checks)


def test_reads_yaml_yml_and_json_configs(tmp_path):
    for suffix, text in (
        (".yaml", "datasets:\n- path: evals\n"),
        (".yml", "datasets:\n- path: evals\n"),
        (".json", '{"datasets": [{"path": "evals"}]}'),
    ):
        repo = tmp_path / suffix[1:]
        expected = _config(repo / "configs" / f"job{suffix}", text)

        result = scan.scan_repository(repo)

        assert result.config is not None and result.config.path == expected


def test_rejects_a_config_symlink_that_resolves_outside_the_repository(tmp_path):
    repo = tmp_path / "repo"
    outside = _config(tmp_path / "outside.yaml")
    link = repo / "configs" / "eval.yaml"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    result = scan.scan_repository(repo)

    assert result.config is None
    assert next(check for check in result.checks if check.name == "config").status == "fail"


def test_profile_prior_job_and_task_layout_never_become_config_candidates(tmp_path):
    (tmp_path / "optimizer.yaml").write_text(
        "agent: ticket-triage\ndatasets:\n  validation: evals/validation\n",
        encoding="utf-8",
    )
    prior_job = tmp_path / "jobs" / "run-1"
    _config(prior_job / "config.json", '{"datasets": [{"path": "evals/validation"}]}')
    (prior_job / "lock.json").write_text('{"harbor_version": "0.18.0"}\n', encoding="utf-8")
    dataset = tmp_path / "evals" / "validation"
    _task(dataset / "task-0")

    result = scan.scan_repository(tmp_path)

    assert (result.config, result.dataset_paths) == (None, [dataset])


def test_uses_only_ethos_for_the_doctrine_contract(tmp_path):
    _config(tmp_path / "harbor-job.yaml")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "AGENT-SPEC.md").write_text("# Old\n", encoding="utf-8")

    without_ethos = scan.scan_repository(tmp_path)
    assert without_ethos.ethos_path is None
    assert any(check.name == "ethos" and check.status == "warn" for check in without_ethos.checks)

    ethos = tmp_path / "ETHOS.md"
    ethos.write_text("# Agent doctrine\n", encoding="utf-8")
    with_ethos = scan.scan_repository(tmp_path)

    assert with_ethos.ethos_path == "ETHOS.md"
    assert any(check.name == "ethos" and check.status == "pass" for check in with_ethos.checks)


def test_discovers_local_datasets_and_prunes_generated_trees(tmp_path):
    _config(tmp_path / "harbor-job.yaml")
    _task(tmp_path)
    _task(tmp_path / "evals" / "suite" / "task-one")
    _task(tmp_path / "evals" / "suite" / "task_template")
    _task(tmp_path / ".nemo-optimizer" / "output" / "task-two")
    _task(tmp_path / "node_modules" / "package" / "task-three")
    _task(tmp_path / "vendor" / "package" / "task-four")
    _task(tmp_path / "cache" / "package" / "task-five")

    result = scan.scan_repository(tmp_path)

    assert result.dataset_paths == [tmp_path / "evals" / "suite"]
    assert result.input_file_count == 3


def test_fingerprint_covers_config_ethos_optimizer_and_dataset_files(tmp_path):
    config = _config(tmp_path / "harbor-job.yaml")
    ethos = tmp_path / "ETHOS.md"
    optimizer = tmp_path / "optimizer.yaml"
    ethos.write_text("# One\n", encoding="utf-8")
    optimizer.write_text("model: one\n", encoding="utf-8")
    task = tmp_path / "evals" / "suite" / "task-one"
    _task(task)
    dataset_file = task / "notes.txt"
    dataset_file.write_text("one\n", encoding="utf-8")

    first = scan.scan_repository(tmp_path)

    assert first.input_file_count == 5
    assert first.config is not None and first.config.path == config
    for path, replacement in (
        (config, "datasets:\n- path: another-evals\n"),
        (ethos, "# Two\n"),
        (optimizer, "model: two\n"),
        (task / "task.toml", 'version = "2.0"\n'),
        (dataset_file, "two\n"),
    ):
        original = path.read_text(encoding="utf-8")
        path.write_text(replacement, encoding="utf-8")
        assert scan.scan_repository(tmp_path).fingerprint != first.fingerprint
        path.write_text(original, encoding="utf-8")


async def test_trace_probe_handles_exception_empty_and_positive_totals():
    for total, status in ((None, "warn"), (0, "warn"), (2, "pass")):
        list_groups = (
            AsyncMock(side_effect=RuntimeError("intake unavailable"))
            if total is None
            else AsyncMock(return_value=SimpleNamespace(pagination=SimpleNamespace(total_results=total)))
        )
        client = SimpleNamespace(
            intake=SimpleNamespace(spans=SimpleNamespace(groups=SimpleNamespace(list=list_groups)))
        )

        finding = await scan.probe_traces(client, agent="ticket-triage", workspace="default")

        assert (finding.status, finding.severity) == (status, "advisory")
