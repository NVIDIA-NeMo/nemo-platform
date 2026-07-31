# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job API tests with a deterministic runner and no Docker."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    EvaluationResult,
    ResourceRef,
    TrialResult,
)
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    create_directory_archive,
    extract_directory_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import (
    ArchiveReference,
    EnvelopeTask,
    EvaluationEnvelope,
    EvaluationSubmission,
)
from nemo_experimentalist_plugin.harbor_bridge.envelopes import (
    RegisteredEnvelope,
    register_dataset_envelope,
    transport_tree_digest,
)
from nemo_experimentalist_plugin.harbor_bridge.service import (
    HarborBridgeSettings,
    RunProfile,
    create_app,
)

_TOKEN = "bridge-token-long-enough"


def _source_dataset(tmp_path: Path) -> RegisteredEnvelope:
    dataset = tmp_path / "source"
    task = dataset / "base-task"
    (task / "environment").mkdir(parents=True)
    (task / "task.toml").write_text(
        '[task]\nname = "fixture/base-task"\n[environment]\ntype = "docker"\n[verifier]\n',
        encoding="utf-8",
    )
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return register_dataset_envelope(dataset, catalog_root=tmp_path / "catalog", name="fixture")


def _request_parts(tmp_path: Path, registered) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "main.py").write_text("print('answer')\n", encoding="utf-8")
    archive = tmp_path / "candidate.tar.gz"
    create_directory_archive(candidate, archive)
    metadata = EvaluationSubmission(
        request_id="candidate-001",
        envelope=EvaluationEnvelope(
            id=registered.manifest.envelope_id,
            digest=registered.manifest.envelope_digest,
            tasks=[EnvelopeTask(task_id="trial-task", base_task_id="base-task")],
        ),
        candidate=ArchiveReference(digest=transport_tree_digest(candidate)),
        run_profile="smoke",
    )
    return (
        {"metadata": metadata.model_dump_json()},
        {"candidate": ("candidate.tar.gz", archive.read_bytes(), "application/gzip")},
    )


def _wait_terminal(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(
            f"/v1/evaluations/{job_id}",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        payload = response.json()
        if payload["state"] not in ("pending", "running"):
            return payload
        time.sleep(0.01)
    raise AssertionError("bridge job did not finish")


class RecordingRunner:
    def __init__(self, *, fail_with: str | None = None) -> None:
        self.fail_with = fail_with
        self.profile: RunProfile | None = None
        self.candidate_dir: Path | None = None
        self.dataset_dir: Path | None = None

    async def run(self, *, submission, profile, candidate_dir, dataset_dir, work_dir) -> EvaluationResult:
        del submission
        self.profile = profile
        self.candidate_dir = candidate_dir
        self.dataset_dir = dataset_dir
        if self.fail_with is not None:
            raise RuntimeError(self.fail_with)
        return EvaluationResult(
            id="result",
            metadata={
                "work_dir": str(work_dir),
                "token": _TOKEN,
            },
            trials=[],
        )


class ArtifactRunner:
    async def run(self, *, submission, profile, candidate_dir, dataset_dir, work_dir) -> EvaluationResult:
        del submission, profile, candidate_dir, dataset_dir
        trace = work_dir / "results" / "trace.jsonl"
        trace.parent.mkdir()
        trace.write_text('{"resourceSpans":[]}\n', encoding="utf-8")
        return EvaluationResult(
            id="artifact-result",
            trials=[
                TrialResult(
                    id="trial-task__0",
                    task_id="trial-task",
                    attempt=0,
                    status="completed",
                    trace=ResourceRef(uri=trace.as_uri(), description="trace"),
                    resources={"outside": ResourceRef(uri=Path("/etc/hosts").as_uri(), description="must not escape")},
                )
            ],
        )


def _client(tmp_path: Path, runner: RecordingRunner) -> TestClient:
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=tmp_path / "jobs",
            catalog_root=tmp_path / "catalog",
            token=_TOKEN,
            sensitive_values=(_TOKEN,),
        ),
        runner=runner,
    )
    return TestClient(app)


def test_job_api_maps_profile_server_side_and_sanitizes_metadata(tmp_path: Path) -> None:
    registered = _source_dataset(tmp_path)
    data, files = _request_parts(tmp_path, registered)
    runner = RecordingRunner()
    with _client(tmp_path, runner) as client:
        response = client.post(
            "/v1/evaluations",
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert response.status_code == 202
        assert response.json()["state"] == "pending"
        payload = _wait_terminal(client, response.json()["job_id"])

    assert payload["state"] == "completed"
    assert payload["result"]["metadata"] == {
        "work_dir": "[HOST_PATH_REDACTED]",
        "token": "[REDACTED]",
    }
    assert runner.profile is not None
    assert runner.profile.attempts == 1
    assert runner.profile.concurrency == 1
    assert runner.candidate_dir is not None and (runner.candidate_dir / "main.py").is_file()
    assert runner.dataset_dir is not None and (runner.dataset_dir / "trial-task" / "task.toml").is_file()


def test_job_api_exports_only_job_owned_artifacts(tmp_path: Path) -> None:
    registered = _source_dataset(tmp_path)
    data, files = _request_parts(tmp_path, registered)
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=tmp_path / "jobs",
            catalog_root=tmp_path / "catalog",
            token=_TOKEN,
        ),
        runner=ArtifactRunner(),
    )
    auth = {"Authorization": f"Bearer {_TOKEN}"}
    with TestClient(app) as client:
        response = client.post("/v1/evaluations", data=data, files=files, headers=auth)
        payload = _wait_terminal(client, response.json()["job_id"])
        artifact_response = client.get(
            f"/v1/evaluations/{response.json()['job_id']}/artifacts",
            headers=auth,
        )

    trial = payload["result"]["trials"][0]
    assert trial["trace"]["uri"].startswith("nemo-harbor-bridge:///artifacts/")
    assert trial["resources"]["outside"]["uri"].startswith("nemo-harbor-bridge:///unavailable/")
    assert str(tmp_path) not in str(payload)
    assert artifact_response.status_code == 200
    assert artifact_response.headers["X-Nemo-Artifact-Digest"].startswith("sha256:")
    archive = tmp_path / "downloaded-artifacts.tar.gz"
    archive.write_bytes(artifact_response.content)
    extracted = tmp_path / "downloaded-artifacts"
    extract_directory_archive(archive, extracted)
    assert next(extracted.rglob("trace.jsonl")).read_text(encoding="utf-8") == '{"resourceSpans":[]}\n'


@pytest.mark.parametrize(
    "field,value",
    [
        ("image", "attacker/image:latest"),
        ("mounts", ["/Users/ryan:/host"]),
        ("env", {"NVIDIA_API_KEY": "secret"}),
        ("agent_import_path", "candidate.module:Agent"),
        ("verifier_mode", "shared"),
        ("docker", {"privileged": True}),
    ],
)
def test_job_api_returns_422_for_unknown_authority(tmp_path: Path, field: str, value: object) -> None:
    registered = _source_dataset(tmp_path)
    data, files = _request_parts(tmp_path, registered)
    metadata = EvaluationSubmission.model_validate_json(data["metadata"]).model_dump()
    metadata[field] = value
    with _client(tmp_path, RecordingRunner()) as client:
        response = client.post(
            "/v1/evaluations",
            data={"metadata": __import__("json").dumps(metadata)},
            files=files,
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
    assert response.status_code == 422


def test_job_api_rejects_unexpected_multipart_authority(tmp_path: Path) -> None:
    registered = _source_dataset(tmp_path)
    data, files = _request_parts(tmp_path, registered)
    files["docker"] = ("config.json", b"{}", "application/json")
    with _client(tmp_path, RecordingRunner()) as client:
        response = client.post(
            "/v1/evaluations",
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
    assert response.status_code == 422


def test_job_api_rejects_digest_mismatch(tmp_path: Path) -> None:
    registered = _source_dataset(tmp_path)
    data, files = _request_parts(tmp_path, registered)
    metadata = EvaluationSubmission.model_validate_json(data["metadata"])
    data["metadata"] = metadata.model_copy(
        update={"candidate": ArchiveReference(digest=f"sha256:{'0' * 64}")}
    ).model_dump_json()
    with _client(tmp_path, RecordingRunner()) as client:
        response = client.post(
            "/v1/evaluations",
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
    assert response.status_code == 422


def test_job_error_does_not_expose_secret_or_host_path(tmp_path: Path) -> None:
    registered = _source_dataset(tmp_path)
    data, files = _request_parts(tmp_path, registered)
    sensitive = f"{_TOKEN} {tmp_path}"
    with _client(tmp_path, RecordingRunner(fail_with=sensitive)) as client:
        response = client.post(
            "/v1/evaluations",
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        payload = _wait_terminal(client, response.json()["job_id"])
    assert payload["state"] == "failed"
    assert _TOKEN not in payload["error"]
    assert str(tmp_path) not in payload["error"]


def test_job_api_requires_authentication(tmp_path: Path) -> None:
    _source_dataset(tmp_path)
    app = create_app(
        settings=HarborBridgeSettings(
            storage_root=tmp_path / "jobs",
            catalog_root=tmp_path / "catalog",
            token=_TOKEN,
        ),
        runner=RecordingRunner(),
    )
    with TestClient(app) as client:
        assert client.get("/v1/evaluations/missing").status_code == 401
