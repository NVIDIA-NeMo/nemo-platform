# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration coverage for real-shaped Eval Author fixture repositories."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest
import yaml

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_DISCOVER = _PLUGIN_ROOT / "skills" / "eval-author-discover" / "scripts" / "discover.py"
_AUDIT_SPEC = _PLUGIN_ROOT / "skills" / "eval-author-audit" / "scripts" / "audit_spec"
_AUDIT_GENERATE = _AUDIT_SPEC / "generate.py"
_AUDIT_VALIDATE = _AUDIT_SPEC / "validate.py"
_AUDIT_MEASURE = _AUDIT_SPEC / "measure.py"
_AUDIT_REPORT = _AUDIT_SPEC / "report.py"


def _fixtures_root() -> Path:
    value = os.environ.get("EVAL_AUTHOR_FIXTURES_ROOT")
    if not value:
        pytest.skip("set EVAL_AUTHOR_FIXTURES_ROOT to the nemo-eval-author-fixtures checkout")
    root = Path(value)
    if not root.is_dir():
        pytest.skip(f"EVAL_AUTHOR_FIXTURES_ROOT is not a directory: {root}")
    return root


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


def _load_cases(root: Path) -> list[dict[str, Any]]:
    manifest = root / "cases.yaml"
    if not manifest.is_file():
        pytest.skip(f"fixture manifest does not exist: {manifest}")
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    return payload["cases"]


def _run_discover(repo: Path, *, pythonpath_repo: bool) -> tuple[int, dict[str, Any]]:
    env = os.environ.copy()
    if pythonpath_repo:
        env["PYTHONPATH"] = str(repo) if not env.get("PYTHONPATH") else f"{repo}{os.pathsep}{env['PYTHONPATH']}"
    result = subprocess.run(
        [sys.executable, str(_DISCOVER), "--repo", str(repo), "--compact"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.stdout, f"discover.py printed nothing for {repo}; stderr:\n{result.stderr}"
    return result.returncode, json.loads(result.stdout)


def _run_json_script(script: Path, *args: str) -> tuple[int, dict[str, Any], str]:
    result = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout, f"{script.name} printed nothing; stderr:\n{result.stderr}"
    return result.returncode, json.loads(result.stdout), result.stderr


def _case_by_name(root: Path, name: str) -> dict[str, Any]:
    for case in _load_cases(root):
        if case["name"] == name:
            return case
    pytest.fail(f"fixture case is missing from cases.yaml: {name}")


def _copy_case_repo(root: Path, name: str, destination: Path) -> Path:
    repo = destination / name
    shutil.copytree(root / "cases" / name / "repo", repo)
    return repo


def _checks_by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {check["name"]: check for check in report["checks"]}


def _measure_frozen_trials_and_report(
    *,
    audit: Path,
    trial_root: Path,
    measurement_dir: Path,
    report_path: Path,
) -> dict[str, Any]:
    trial_dirs = sorted(path for path in trial_root.iterdir() if path.is_dir())
    assert trial_dirs, f"no frozen Harbor trial directories under {trial_root}"
    for trial_dir in trial_dirs:
        measure_code, measure_summary, measure_stderr = _run_json_script(
            _AUDIT_MEASURE,
            "--audit",
            str(audit),
            "--trial-dir",
            str(trial_dir),
            "--out-dir",
            str(measurement_dir),
        )
        assert measure_code == 0, measure_stderr or measure_summary

    report_code, report_summary, report_stderr = _run_json_script(
        _AUDIT_REPORT,
        "--audit",
        str(audit),
        "--coverage-dir",
        str(measurement_dir),
        "--out",
        str(report_path),
    )

    assert report_code == 0, report_stderr or report_summary
    return report_summary


def test_discover_fixture_corpus_matches_manifest_expectations(tmp_path: Path) -> None:
    if find_spec("harbor") is None:
        pytest.skip("Harbor is not installed")
    if not _docker_available():
        pytest.skip("Docker daemon is required for fixture backend validation")

    root = _fixtures_root()
    for case in _load_cases(root):
        expected = case["expected"]
        repo = _copy_case_repo(root, case["name"], tmp_path / "discover")

        code, report = _run_discover(repo, pythonpath_repo=bool(expected.get("pythonpath_repo")))

        assert code == expected["exit_code"], case["name"]
        assert report["proven"] is True, case["name"]
        assert report["runnable"] is expected["runnable"], case["name"]
        assert sorted(report["dataset_paths"]) == sorted(expected["dataset_paths"]), case["name"]

        checks = _checks_by_name(report)
        for check_name in expected["required_check_names_pass"]:
            assert checks[check_name]["status"] == "pass", f"{case['name']}:{check_name}"

        configs_by_path = {config["path"]: config for config in report["configs"]}
        for expected_config in expected["configs"]:
            config = configs_by_path[expected_config["path"]]
            assert config["name"] == expected_config["name"], case["name"]
            assert config["runnable"] is expected_config["runnable"], case["name"]
            assert expected_config["run_command_contains"] in report["run_command"], case["name"]


def test_rho_agent_frozen_audit_measurement_matches_manifest_expectations(tmp_path: Path) -> None:
    if find_spec("harbor") is None:
        pytest.skip("Harbor is not installed")

    root = _fixtures_root()
    case = _case_by_name(root, "rho-agent")
    expected = case["expected"]["audit_measurement"]
    case_root = _copy_case_repo(root, "rho-agent", tmp_path / "audit")
    audit = case_root / ".eval-author" / "audit.md"
    trial_root = case_root / expected["frozen_trial_dir"]
    assert trial_root.is_dir()

    validate_code, validate_summary, validate_stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))
    assert validate_code == 0, validate_stderr or validate_summary
    assert validate_summary["valid"] is True

    report_summary = _measure_frozen_trials_and_report(
        audit=audit,
        trial_root=trial_root,
        measurement_dir=tmp_path / "audit-measurements",
        report_path=tmp_path / "audit-coverage-report.json",
    )

    assert report_summary["measured_kinds"] == [expected["measured_kind"]]
    assert report_summary["covered_count"] == expected["covered_count"]
    assert report_summary["uncovered_count"] == expected["uncovered_count"]


def test_rho_agent_demo_ready_generates_audit_and_coverage_from_frozen_traces(tmp_path: Path) -> None:
    if find_spec("harbor") is None:
        pytest.skip("Harbor is not installed")

    root = _fixtures_root()
    case = _case_by_name(root, "rho-agent-demo-ready")
    expected = case["expected"]["audit_bootstrap"]
    case_root = _copy_case_repo(root, "rho-agent-demo-ready", tmp_path / "demo")
    audit_dir = case_root / ".eval-author"
    audit = case_root / expected["audit_path"]
    items = audit_dir / "audit-items.yaml"
    trial_root = case_root / expected["frozen_trial_dir"]
    report_path = tmp_path / "demo-audit-coverage-report.json"

    assert (case_root / expected["ethos_path"]).is_file()
    assert trial_root.is_dir()
    assert not audit.exists()
    assert not items.exists()

    shutil.copyfile(root / expected["reference_items_path"], items)

    generate_code, generate_summary, generate_stderr = _run_json_script(
        _AUDIT_GENERATE,
        "--ethos",
        str(case_root / expected["ethos_path"]),
        "--items",
        str(items),
        "--items-mode",
        "full",
        "--out",
        str(audit),
    )
    assert generate_code == 0, generate_stderr or generate_summary
    assert generate_summary["written"] is True
    assert generate_summary["action"] == "create"
    assert audit.is_file()

    validate_code, validate_summary, validate_stderr = _run_json_script(_AUDIT_VALIDATE, "--audit", str(audit))
    assert validate_code == 0, validate_stderr or validate_summary
    assert validate_summary["valid"] is True

    report_summary = _measure_frozen_trials_and_report(
        audit=audit,
        trial_root=trial_root,
        measurement_dir=tmp_path / "demo-audit-measurements",
        report_path=report_path,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_summary["measured_kinds"] == [expected["measured_kind"]]
    assert report_summary["covered_count"] == expected["covered_count"]
    assert report_summary["uncovered_count"] == expected["uncovered_count"]
    assert report["uncovered_items"]
    assert all(gap["generation"]["focus"] for gap in report["uncovered_items"])
    assert all("needed_tools" in gap["generation"] for gap in report["uncovered_items"])
    assert all("evidence_required" in gap["generation"] for gap in report["uncovered_items"])
