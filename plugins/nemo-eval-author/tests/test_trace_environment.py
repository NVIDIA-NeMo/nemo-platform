# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the standalone trace-environment boundary helper."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_PLUGIN = Path(__file__).resolve().parents[1]
_SCRIPT = _PLUGIN / "skills" / "eval-author-trace-environment" / "scripts" / "trace_environment.py"
_SUMMARY_SCHEMA = "nemo.eval_author.trace_environment_summary.v2"
_CANDIDATE_SCHEMA = "nemo.eval_author.trace_environment_candidate.v2"
_VALIDATION_SCHEMA = "nemo.eval_author.trace_environment_validation.v2"


def _run(*args: str) -> tuple[int, dict[str, Any]]:
    result = subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True, check=False)
    assert result.stdout, result.stderr
    return result.returncode, json.loads(result.stdout)


def _atif(*, image_only: bool = False) -> dict[str, Any]:
    message: str | list[dict[str, Any]]
    if image_only:
        message = [{"type": "image", "source": {"media_type": "image/png", "path": "screen.png"}}]
    else:
        message = "Repair the fixture for jane@example.com from /home/jane/project."
    return {
        "schema_version": "ATIF-v1.7",
        "session_id": "session-1",
        "trajectory_id": "trace-1",
        "agent": {"name": "coding-agent", "version": "1.0"},
        "steps": [
            {"step_id": 1, "source": "user", "message": message},
            {
                "step_id": 2,
                "source": "agent",
                "message": "Calling 10.2.3.4 with token Bearer abcdefghijklmnop",
                "tool_calls": [
                    {
                        "tool_call_id": "call-1",
                        "function_name": "fixture.read",
                        "arguments": {"phone": "+1 (303) 555-0119", "api_key": "secret-value"},
                    }
                ],
                "observation": {"results": [{"source_call_id": "call-1", "content": "Result for 123-45-6789"}]},
            },
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _workspace(tmp_path: Path, *, image_only: bool = False) -> tuple[Path, Path]:
    root = tmp_path / ".eval-author" / "trace-environments"
    code, result = _run("init", "--root", str(root), "--task-id", "repair-fixture")
    assert code == 0, result
    task_dir = Path(result["task_dir"])
    source = tmp_path / "source.atif.json"
    _write_json(source, _atif(image_only=image_only))
    code, result = _run(
        "prepare",
        "--task-dir",
        str(task_dir),
        "--atif",
        str(source),
        "--source-kind",
        "atif",
    )
    assert code == 0, result
    return task_dir, source


def _candidate(
    task_dir: Path,
    *,
    status: str = "candidate",
    ground_truth: dict[str, Any] | None = None,
    software_requirements: list[dict[str, Any]] | None = None,
) -> None:
    if ground_truth is None:
        ground_truth = {
            "availability": "absent",
            "use": "none",
            "artifacts": [],
            "absence_reason": "No distinct reference artifact was recorded.",
        }
    if software_requirements is None:
        software_requirements = []
    if status == "candidate":
        payload = {
            "schema": _CANDIDATE_SCHEMA,
            "status": "candidate",
            "decision_basis": "safe_atif_only",
            "instruction": "Repair the local fixture.",
            "requirements": [{"description": "The fixture check passes.", "evidence_steps": [1, 2]}],
            "verification_mode": "execution",
            "evidence_steps": [1, 2],
            "uncertainties": [],
            "reason_codes": [],
            "ground_truth": ground_truth,
            "software_requirements": software_requirements,
        }
    else:
        payload = {
            "schema": _CANDIDATE_SCHEMA,
            "status": "no_candidate",
            "decision_basis": "safe_atif_only",
            "instruction": None,
            "requirements": [],
            "verification_mode": None,
            "evidence_steps": [1],
            "uncertainties": ["The expected outcome is absent."],
            "reason_codes": ["missing_outcome"],
            "ground_truth": ground_truth,
            "software_requirements": software_requirements,
        }
    _write_json(task_dir / "candidate.json", payload)


def _review_privacy(task_dir: Path, *, reviewer_kind: str = "agent") -> None:
    code, result = _run(
        "review-privacy",
        "--task-dir",
        str(task_dir),
        "--reviewer-kind",
        reviewer_kind,
        "--note",
        "Reviewed every safe ATIF string and all contextual audit findings.",
    )
    assert code == 0, result


def _ready_environment(
    task_dir: Path,
    *,
    mode: str = "separate",
    nop_reward: float = 0.0,
    oracle_reward: float = 1.0,
    oracle_exception: object | None = None,
) -> None:
    task = task_dir / "task"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "solution").mkdir()
    verifier = f'\n[verifier]\nenvironment_mode = "{mode}"\n'
    if mode == "separate":
        verifier += 'network_mode = "no-network"\n\n[verifier.environment]\nnetwork_mode = "no-network"\n'
    (task / "task.toml").write_text(f'schema_version = "1.1"\n{verifier}', encoding="utf-8")
    (task / "instruction.md").write_text("Repair the fixture.\n", encoding="utf-8")
    (task / "README.md").write_text(
        """# Repair fixture

## Difficulty explanation

The task requires identifying and repairing an invalid local fixture.

## Environment and software requirements

The task uses the tools installed by its container image and has no proprietary dependencies.

## Ground-truth provenance

The expected state is derived from the retained trace evidence cited in the candidate record.

## Solution explanation

The reference solution replaces the invalid fixture with the required state.

## Verification explanation

The test checks the resulting fixture state without inspecting the agent's implementation.

## Relevant experience

The human reviewer confirmed that this fixture accurately represents the recorded workflow.
""",
        encoding="utf-8",
    )
    (task / "tests" / "test.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (task / "solution" / "solve.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    checksum = "a" * 64
    for arm, reward, exception in (
        ("nop", nop_reward, None),
        ("oracle", oracle_reward, oracle_exception),
    ):
        trial = task_dir / "private" / "jobs" / arm / "task__trial"
        trial.mkdir(parents=True)
        _write_json(
            trial / "result.json",
            {
                "task_checksum": checksum,
                "verifier_environment_mode": mode,
                "verifier_result": {"rewards": {"reward": reward}},
                "exception_info": exception,
            },
        )
    code, result = _run(
        "record-validation",
        "--task-dir",
        str(task_dir),
        "--nop-job-dir",
        "private/jobs/nop",
        "--oracle-job-dir",
        "private/jobs/oracle",
        "--harbor-version",
        "0.21.0",
    )
    assert code == 0, result


def test_init_creates_private_gitignored_workspace(tmp_path: Path) -> None:
    root = tmp_path / ".eval-author" / "trace-environments"

    code, result = _run("init", "--root", str(root), "--task-id", "repair-fixture")

    assert code == 0, result
    task_dir = root / "repair-fixture"
    assert result == {"gitignored": True, "status": "pending", "task_dir": str(task_dir)}
    assert (root / ".gitignore").read_text(encoding="utf-8") == "*\n!.gitignore\n"
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["schema"] == _SUMMARY_SCHEMA
    assert summary["status"] == "pending"
    if os.name == "posix":
        assert root.stat().st_mode & 0o777 == 0o700
        assert task_dir.stat().st_mode & 0o777 == 0o700
        assert (task_dir / "summary.json").stat().st_mode & 0o777 == 0o600


def test_init_refuses_to_write_outside_eval_author(tmp_path: Path) -> None:
    code, result = _run("init", "--root", str(tmp_path / "elsewhere"), "--task-id", "repair-fixture")

    assert code == 1
    assert "under a .eval-author directory" in result["error"]
    assert not (tmp_path / "elsewhere").exists()


def test_prepare_preserves_original_and_writes_text_only_redacted_atif(tmp_path: Path) -> None:
    task_dir, source = _workspace(tmp_path)

    private = task_dir / "private" / "source.atif.json"
    safe = task_dir / "safe" / "trace.atif.json"
    privacy = json.loads((task_dir / "safe" / "privacy.json").read_text(encoding="utf-8"))
    safe_text = safe.read_text(encoding="utf-8")
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))

    assert private.read_bytes() == source.read_bytes()
    assert "jane@example.com" not in safe_text
    assert "/home/jane" not in safe_text
    assert "10.2.3.4" not in safe_text
    assert "+1 (303) 555-0119" not in safe_text
    assert "abcdefghijklmnop" not in safe_text
    assert "secret-value" not in safe_text
    assert "123-45-6789" not in safe_text
    assert "session-1" not in safe_text
    assert "call-1" not in safe_text
    assert privacy["contextual_review_required"] is True
    assert privacy["contextual_review_complete"] is False
    assert set(privacy["deterministic_redactions"]) >= {
        "bearer_token",
        "email",
        "home_path",
        "identifier",
        "ipv4",
        "phone",
        "secret_field",
        "ssn",
    }
    assert summary["source"]["original_sha256"] == f"sha256:{hashlib.sha256(private.read_bytes()).hexdigest()}"
    assert summary["source"]["safe_sha256"] == f"sha256:{hashlib.sha256(safe.read_bytes()).hexdigest()}"
    assert (task_dir / "private" / "canonical.atif.json").is_file()
    assert (task_dir / "private" / "privacy-audit.json").is_file()


def test_prepare_reports_non_object_observation(tmp_path: Path) -> None:
    root = tmp_path / ".eval-author" / "trace-environments"
    code, result = _run("init", "--root", str(root), "--task-id", "repair-fixture")
    assert code == 0, result
    task_dir = Path(result["task_dir"])
    source = tmp_path / "source.atif.json"
    payload = _atif()
    payload["steps"][1]["observation"] = "not-an-object"
    _write_json(source, payload)

    code, result = _run(
        "prepare",
        "--task-dir",
        str(task_dir),
        "--atif",
        str(source),
        "--source-kind",
        "atif",
    )

    assert code == 1
    assert result["error"] == "trajectory.steps[1].observation must be an object"


def test_image_only_instruction_blocks_candidate_but_can_be_no_candidate(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path, image_only=True)
    _candidate(task_dir)
    _review_privacy(task_dir)

    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "candidate",
    )

    assert code == 1
    assert "unresolved non-text evidence" in result["error"]
    privacy = json.loads((task_dir / "safe" / "privacy.json").read_text(encoding="utf-8"))
    assert privacy["contextual_review_complete"] is True

    _candidate(task_dir, status="no_candidate")
    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "no_candidate")
    assert code == 0, result


def test_no_candidate_summary_records_reasons_and_lessons(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir, status="no_candidate")

    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "no_candidate",
        "--worked-well",
        "The instruction was recoverable.",
        "--did-not-work",
        "The expected outcome was absent.",
    )

    assert code == 0, result
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "no_candidate"
    assert summary["reasons"] == ["missing_outcome"]
    assert summary["worked_well"] == ["The instruction was recoverable."]
    assert summary["did_not_work"] == ["The expected outcome was absent."]
    assert "`no_candidate`" in (task_dir / "summary.md").read_text(encoding="utf-8")
    code, check = _run("check", "--task-dir", str(task_dir))
    assert code == 0, check
    assert check["valid"] is True


def test_summary_captures_ground_truth_and_proprietary_software(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    expected = task_dir / "private" / "ground-truth" / "expected.json"
    _write_json(expected, {"fixture": "repaired"})
    expected.chmod(0o600)
    _candidate(
        task_dir,
        status="no_candidate",
        ground_truth={
            "availability": "available",
            "use": "comparison_only",
            "artifacts": [
                {
                    "kind": "expected_output",
                    "path": "private/ground-truth/expected.json",
                    "sha256": f"sha256:{hashlib.sha256(expected.read_bytes()).hexdigest()}",
                    "provenance": {
                        "kind": "external",
                        "step_ids": [],
                        "uri": "https://example.test/fixtures/expected.json",
                        "revision": "abc123",
                        "source_id": None,
                    },
                    "notes": "The trace records this expected fixture state.",
                }
            ],
            "absence_reason": None,
        },
        software_requirements=[
            {
                "name": "ExampleCAD",
                "category": "desktop_application",
                "required": True,
                "version": "2026",
                "license": "proprietary",
                "availability": "unavailable",
                "redistributable": False,
                "provenance": {
                    "kind": "atif_step",
                    "step_ids": [1, 2],
                    "uri": None,
                    "revision": None,
                    "source_id": None,
                },
                "notes": "The workflow requires its native file format and runtime.",
            }
        ],
    )

    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "no_candidate")

    assert code == 0, result
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["candidate"]["ground_truth"]["availability"] == "available"
    assert summary["candidate"]["ground_truth"]["artifacts"][0]["kind"] == "expected_output"
    assert summary["candidate"]["software_requirements"][0]["license"] == "proprietary"
    markdown = (task_dir / "summary.md").read_text(encoding="utf-8")
    assert "Retained artifacts: 1" in markdown
    assert "ExampleCAD (desktop_application)" in markdown
    assert "license=proprietary" in markdown
    assert "availability=unavailable" in markdown


def test_candidate_rejects_required_unavailable_software(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(
        task_dir,
        software_requirements=[
            {
                "name": "ExampleCAD",
                "category": "desktop_application",
                "required": True,
                "version": None,
                "license": "commercial",
                "availability": "unavailable",
                "redistributable": False,
                "provenance": {
                    "kind": "atif_step",
                    "step_ids": [1],
                    "uri": None,
                    "revision": None,
                    "source_id": None,
                },
                "notes": "No licensed runtime is available in the task environment.",
            }
        ],
    )

    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "candidate",
    )

    assert code == 1
    assert "candidate requires unavailable software: ExampleCAD" in result["error"]


def test_ground_truth_digest_must_match_retained_artifact(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    expected = task_dir / "private" / "ground-truth" / "expected.json"
    _write_json(expected, {"fixture": "repaired"})
    expected.chmod(0o600)
    _candidate(
        task_dir,
        status="no_candidate",
        ground_truth={
            "availability": "available",
            "use": "verification",
            "artifacts": [
                {
                    "kind": "expected_output",
                    "path": "private/ground-truth/expected.json",
                    "sha256": f"sha256:{'0' * 64}",
                    "provenance": {
                        "kind": "atif_step",
                        "step_ids": [2],
                        "uri": None,
                        "revision": None,
                        "source_id": None,
                    },
                    "notes": "The trace records this expected fixture state.",
                }
            ],
            "absence_reason": None,
        },
    )

    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "no_candidate")

    assert code == 1
    assert "sha256 does not match the retained artifact" in result["error"]


def test_ground_truth_path_cannot_escape_private_directory(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    outside = task_dir / "private" / "outside.json"
    _write_json(outside, {"fixture": "repaired"})
    outside.chmod(0o600)
    _candidate(
        task_dir,
        status="no_candidate",
        ground_truth={
            "availability": "available",
            "use": "verification",
            "artifacts": [
                {
                    "kind": "expected_output",
                    "path": "private/ground-truth/../outside.json",
                    "sha256": f"sha256:{hashlib.sha256(outside.read_bytes()).hexdigest()}",
                    "provenance": {
                        "kind": "atif_step",
                        "step_ids": [2],
                        "uri": None,
                        "revision": None,
                        "source_id": None,
                    },
                    "notes": "The trace records this expected fixture state.",
                }
            ],
            "absence_reason": None,
        },
    )

    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "no_candidate")

    assert code == 1
    assert "path escapes private/ground-truth/" in result["error"]


def test_ready_candidate_requires_privacy_review_and_both_harbor_arms(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir)

    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "candidate",
    )
    assert code == 1
    assert "review-privacy" in result["error"]

    _review_privacy(task_dir, reviewer_kind="human")
    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "candidate",
        "--human-reviewed",
        "--worked-well",
        "NOP and Oracle produced the required rewards.",
    )

    assert code == 0, result
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "candidate"
    assert summary["environment"] == {
        "path": "task",
        "status": "ready",
        "technical_status": "passed",
        "review_status": "human_reviewed",
        "validation": "validation.json",
        "verifier_environment_mode": "separate",
        "isolation_status": "isolated",
    }
    assert summary["privacy"]["contextual_review_complete"] is True
    code, check = _run("check", "--task-dir", str(task_dir))
    assert code == 0, check


def test_ready_candidate_rejects_wrong_arm_reward(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir)
    validation_path = task_dir / "validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["nop"]["reward"] = 1
    _write_json(validation_path, validation)
    _review_privacy(task_dir)

    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "candidate",
    )

    assert code == 1
    assert "differs from the retained Harbor result evidence" in result["error"]


def test_ready_candidate_requires_reviewer_facing_readme(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir)
    _review_privacy(task_dir)
    (task_dir / "task" / "README.md").unlink()

    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "candidate",
    )

    assert code == 1
    assert "candidate environment is missing: task/README.md" in result["error"]


def test_ready_candidate_requires_substantive_readme_sections(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir)
    _review_privacy(task_dir)
    readme = task_dir / "task" / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "The test checks the resulting fixture state without inspecting the agent's implementation.", ""
        ),
        encoding="utf-8",
    )

    code, result = _run(
        "finalize",
        "--task-dir",
        str(task_dir),
        "--status",
        "candidate",
    )

    assert code == 1
    assert "Verification explanation" in result["error"]


def test_check_detects_changed_safe_evidence(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir, status="no_candidate")
    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "no_candidate")
    assert code == 0, result
    with (task_dir / "safe" / "trace.atif.json").open("a", encoding="utf-8") as stream:
        stream.write("\n")

    code, result = _run("check", "--task-dir", str(task_dir))

    assert code == 1
    assert result["valid"] is False
    assert "safe_path is missing or its digest changed" in result["errors"]


def test_prepare_narrowly_repairs_provider_redaction_quote(tmp_path: Path) -> None:
    root = tmp_path / ".eval-author" / "trace-environments"
    code, result = _run("init", "--root", str(root), "--task-id", "repair-quote")
    assert code == 0, result
    source = tmp_path / "broken.atif.json"
    source.write_text(
        '{"schema_version":"ATIF-v1.7","agent":{"name":"agent"},"steps":'
        '[{"step_id":1,"source":"user","message":"prefix \\"PASSWORD=<redacted>" suffix"}]}',
        encoding="utf-8",
    )

    code, result = _run(
        "prepare",
        "--task-dir",
        result["task_dir"],
        "--atif",
        str(source),
        "--source-kind",
        "atif",
    )

    assert code == 0, result
    assert result["normalization_count"] == 1
    summary = json.loads((root / "repair-quote" / "summary.json").read_text(encoding="utf-8"))
    assert summary["source"]["normalizations"][0]["kind"] == "escape_provider_redaction_placeholder_quote"
    assert (root / "repair-quote" / "private" / "source.atif.json").read_bytes() == source.read_bytes()


def test_prepare_bounds_string_encoded_images_and_audits_context(tmp_path: Path) -> None:
    root = tmp_path / ".eval-author" / "trace-environments"
    code, result = _run("init", "--root", str(root), "--task-id", "bound-image")
    assert code == 0, result
    task_dir = Path(result["task_dir"])
    source = tmp_path / "image.atif.json"
    payload = _atif()
    payload["steps"][0]["message"] = [
        {
            "type": "text",
            "text": "Use https://api.example.test/path for Example Labs at 123 Main Street and John Smith.",
        },
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "A" * 100_001},
        },
    ]
    payload["steps"][1]["observation"]["results"][0]["content"] = (
        'before {"type":"image","source":{"type":"base64","media_type":"image/png","data":"DATA"}} after'
    )
    payload["steps"][1]["message"] = "Call service.default.svc.cluster.local"
    _write_json(source, payload)

    code, result = _run(
        "prepare",
        "--task-dir",
        str(task_dir),
        "--atif",
        str(source),
        "--source-kind",
        "atif",
    )

    assert code == 0, result
    canonical = json.loads((task_dir / "private" / "canonical.atif.json").read_text(encoding="utf-8"))
    assert canonical["steps"][0]["message"][1]["source"]["data"] == ""
    assert canonical["steps"][1]["observation"]["results"][0]["content"][1]["source"]["data"] == ""
    safe_text = (task_dir / "safe" / "trace.atif.json").read_text(encoding="utf-8")
    assert "svc.cluster.local" not in safe_text
    audit = json.loads((task_dir / "private" / "privacy-audit.json").read_text(encoding="utf-8"))
    assert audit["url_hosts"] == ["api.example.test"]
    assert {finding["kind"] for finding in audit["candidate_findings"]} >= {
        "organization",
        "person_name",
        "street_address",
    }


def test_shared_verifier_can_pass_technically_but_cannot_be_ready(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir, mode="shared")
    _review_privacy(task_dir, reviewer_kind="human")

    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "candidate", "--human-reviewed")

    assert code == 0, result
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["environment"]["technical_status"] == "passed"
    assert summary["environment"]["status"] == "unproven"
    assert summary["environment"]["isolation_status"] == "shared"


def test_candidate_requires_explicit_verifier_environment_mode(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir, mode="shared")
    task_toml = task_dir / "task" / "task.toml"
    task_toml.write_text(
        task_toml.read_text(encoding="utf-8").replace('environment_mode = "shared"\n', ""),
        encoding="utf-8",
    )
    _review_privacy(task_dir)

    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "candidate")

    assert code == 1
    assert "must explicitly set [verifier].environment_mode" in result["error"]


def test_failed_harbor_proof_is_validated_and_attached(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir, oracle_reward=0.0, oracle_exception={"type": "RuntimeError"})
    _review_privacy(task_dir)

    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "candidate")

    assert code == 0, result
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["environment"]["status"] == "failed"
    assert summary["environment"]["technical_status"] == "failed"
    assert summary["environment"]["validation"] == "validation.json"
    code, check = _run("check", "--task-dir", str(task_dir))
    assert code == 0, check


def test_export_uses_a_strict_publication_whitelist(tmp_path: Path) -> None:
    task_dir, _ = _workspace(tmp_path)
    _candidate(task_dir)
    _ready_environment(task_dir)
    _review_privacy(task_dir, reviewer_kind="human")
    code, result = _run("finalize", "--task-dir", str(task_dir), "--status", "candidate", "--human-reviewed")
    assert code == 0, result
    output = tmp_path / "product"

    code, result = _run("export", "--task-dir", str(task_dir), "--output-dir", str(output))

    assert code == 0, result
    assert (output / "candidate.json").is_file()
    assert (output / "result.json").is_file()
    assert (output / "task").is_dir()
    assert not (output / "validation.json").exists()
    assert not (output / "safe").exists()
    assert not (output / "private").exists()


def test_batch_prepare_is_resumable_and_reports_full_denominator(tmp_path: Path) -> None:
    source_one = tmp_path / "one.json"
    source_two = tmp_path / "two.json"
    _write_json(source_one, _atif())
    _write_json(source_two, _atif())
    manifest = tmp_path / "manifest.json"
    _write_json(
        manifest,
        {
            "schema": "nemo.eval_author.trace_environment_batch.v1",
            "members": [
                {"task_id": "task-one", "atif": "one.json", "source_kind": "atif"},
                {"task_id": "task-two", "atif": "two.json", "source_kind": "atif"},
            ],
        },
    )
    root = tmp_path / ".eval-author" / "trace-environments"

    code, first = _run("batch-prepare", "--root", str(root), "--manifest", str(manifest))
    assert code == 0, first
    assert first["denominator"] == 2
    assert first["counts"] == {"prepared": 2}
    code, second = _run("batch-prepare", "--root", str(root), "--manifest", str(manifest))
    assert code == 0, second
    assert second["counts"] == {"existing": 2}
    code, status = _run("batch-status", "--root", str(root), "--manifest", str(manifest))
    assert code == 0, status
    assert status["denominator"] == 2
    assert status["counts"] == {"pending_prepared": 2}


@pytest.mark.parametrize("task_id", ["Has-Caps", "has spaces", "../escape", ""])
def test_init_rejects_unsafe_task_ids(tmp_path: Path, task_id: str) -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "init", "--root", str(tmp_path / "root"), "--task-id", task_id],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
