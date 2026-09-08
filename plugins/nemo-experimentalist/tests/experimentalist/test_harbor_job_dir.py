# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""No-Docker coverage for canonical Harbor TrialResult dumps."""

from __future__ import annotations

from pathlib import Path

import pytest
from harbor_job_dir import assert_comparable_trials_dump, canonical_trials_json
from nemo_experimentalist_plugin.entities import MetricResult, MetricSpec, ResourceRef, TrialResult


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _trial(
    job_dir: Path,
    *,
    folder: str,
    task_id: str,
    attempt: int | None = None,
    extra_resources: dict[str, ResourceRef] | None = None,
    dataset_ref: ResourceRef | None = None,
) -> TrialResult:
    trial_dir = job_dir / folder
    spec_ref = dataset_ref or ResourceRef(uri=_file_uri(trial_dir / "verifier" / "reward.json"), description="reward")
    resources = {
        "trial_dir": ResourceRef(uri=_file_uri(trial_dir), description="Harbor trial output directory"),
        "result": ResourceRef(uri=_file_uri(trial_dir / "result.json"), description="result"),
    }
    if extra_resources:
        resources.update(extra_resources)
    return TrialResult(
        id=folder,
        task_id=task_id,
        attempt=attempt,
        status="completed",
        trace=ResourceRef(uri=_file_uri(trial_dir / "artifacts" / "traces" / "agent.jsonl"), description="trace"),
        outputs={"blob": ResourceRef(uri=_file_uri(trial_dir / "out.txt"), description="output")},
        resources=resources,
        metrics={
            "reward": MetricResult(
                name="reward",
                value=1,
                spec=MetricSpec(name="reward", description="reward", ref=spec_ref),
            )
        },
        metadata={"n_input_tokens": 7, "n_output_tokens": 3, "n_cache_tokens": 1},
    )


def test_canonical_dump_matches_across_ids_uris_and_numeric_attempt(tmp_path: Path) -> None:
    native_job = tmp_path / "native experiment" / "jobs" / "agent-validation"
    sdk_job = tmp_path / "sdk-experiment" / "jobs" / "agent-validation"
    dataset_ref = ResourceRef(uri=_file_uri(tmp_path / "dataset" / "task" / "tests"), description="dataset verifier")
    native = _trial(
        native_job,
        folder="completed-correct-answer__1234567",
        task_id="completed-correct-answer",
        attempt=1234567,
        dataset_ref=dataset_ref,
    )
    sdk = _trial(
        sdk_job,
        folder="completed-correct-answer__xyz9876",
        task_id="completed-correct-answer",
        attempt=None,
        dataset_ref=dataset_ref,
    )

    assert_comparable_trials_dump([native], [sdk])

    dumped = canonical_trials_json([native])
    assert '"id":"completed-correct-answer"' in dumped, "Harbor trial_name must be replaced with the stable task_id"
    assert '"attempt":null' in dumped, (
        "n_attempts=1 dumps must force attempt=None even when the ShortUUID suffix is all digits"
    )
    assert "$JOB_DIR/completed-correct-answer/artifacts/traces/agent.jsonl" in dumped, (
        "trial-local trace URIs must be rewritten under $JOB_DIR/<task_id>"
    )
    assert "$JOB_DIR/completed-correct-answer/out.txt" in dumped, (
        "trial-local output ResourceRef URIs must be rewritten under $JOB_DIR/<task_id>"
    )
    assert "$JOB_DIR/completed-correct-answer/verifier/reward.json" not in dumped, (
        "MetricSpec.ref pointing at the shared dataset verifier must stay a dataset URI, not a trial path"
    )
    assert dataset_ref.uri in dumped, (
        "dataset-fixture ResourceRef URIs must be left unchanged when they are not under the trial dir"
    )
    assert "1234567" not in dumped, "all-digit Harbor trial suffix must not leak into id, attempt, or rewritten URIs"
    assert "native experiment" not in dumped, "absolute job-dir path segments must be replaced by $JOB_DIR"
    assert "%20" not in dumped, "percent-encoded spaces from file:// job-dir URIs must not survive rewriting"

    local_spec = canonical_trials_json(
        [_trial(native_job, folder="completed-correct-answer__1234567", task_id="completed-correct-answer")]
    )
    assert "$JOB_DIR/completed-correct-answer/verifier/reward.json" in local_spec, (
        "MetricSpec.ref under the trial dir must be rewritten like other trial-local ResourceRefs"
    )


def test_canonical_dump_matches_job_local_metric_spec_refs(tmp_path: Path) -> None:
    native = _trial(
        tmp_path / "native-experiment" / "jobs" / "agent-validation",
        folder="task__native",
        task_id="task",
    )
    sdk = _trial(
        tmp_path / "sdk-experiment" / "jobs" / "agent-validation",
        folder="task__sdk",
        task_id="task",
    )

    native_ref = native.metrics["reward"].spec
    sdk_ref = sdk.metrics["reward"].spec
    assert native_ref is not None and native_ref.ref is not None, "native trial must carry a MetricSpec.ref"
    assert sdk_ref is not None and sdk_ref.ref is not None, "sdk trial must carry a MetricSpec.ref"
    assert native_ref.ref.uri != sdk_ref.ref.uri, (
        "precondition: job-local metric spec URIs must differ so the dump rewrite is what makes them comparable"
    )

    assert_comparable_trials_dump([native], [sdk])


def test_canonical_dump_fails_on_extra_resource_key(tmp_path: Path) -> None:
    job = tmp_path / "jobs" / "agent-validation"
    left = _trial(job, folder="task__aaa", task_id="task")
    right = _trial(
        job,
        folder="task__bbb",
        task_id="task",
        extra_resources={"log:trial.log": ResourceRef(uri=_file_uri(job / "task__bbb" / "trial.log"))},
    )

    with pytest.raises(AssertionError, match="Canonical trial dump differs for task_id task"):
        assert_comparable_trials_dump([left], [right])


def test_canonical_dump_rejects_duplicate_task_id(tmp_path: Path) -> None:
    job = tmp_path / "jobs" / "agent-validation"
    first = _trial(job, folder="task__aaa", task_id="task")
    second = _trial(job, folder="task__bbb", task_id="task")

    with pytest.raises(ValueError, match="Duplicate canonical trial task_id 'task'"):
        canonical_trials_json([first, second])


def test_canonical_dump_requires_trial_dir() -> None:
    trial = TrialResult(id="x", task_id="task", status="completed")

    with pytest.raises(ValueError, match="missing resources\\['trial_dir'\\]"):
        canonical_trials_json([trial])


def test_canonical_dump_rejects_unparseable_trial_dir() -> None:
    trial = TrialResult(
        id="x",
        task_id="task",
        status="completed",
        resources={"trial_dir": ResourceRef(uri="https://example.invalid/trial")},
    )

    with pytest.raises(ValueError, match="unparseable trial_dir URI"):
        canonical_trials_json([trial])
