"""E2E coverage for the Safe Synthesizer plugin.

Smoke coverage runs in the local subprocess harness and verifies the API,
Files, and job-entity surfaces without requiring the task image to complete.
Full workflow coverage is opt-in and targets a Kubernetes deployment such as
minikube at ``NMP_BASE_URL=http://localhost:30080``.

Examples:

    uv run --frozen pytest e2e/test_safe_synthesizer.py -v --run-e2e

    NMP_BASE_URL=http://localhost:30080 \
      uv run --frozen pytest e2e/test_safe_synthesizer.py -v \
        --run-e2e --run-slow --feature gpu
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient
from nemo_platform_plugin.files.types import CreateFilesetRequest

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.e2e_config(
        "e2e/configs/local-subprocess.yaml",
        {"safe_synthesizer": {"runtime_python": sys.executable}},
    ),
]

TERMINAL_STATUSES = {"completed", "error", "cancelled"}
STARTED_STATUSES = {"pending", "active", "completed", "error", "cancelled"}

INPUT_REMOTE_PATH = "inputs/safe-synthesizer-e2e.csv"
SMOKE_JOB_TIMEOUT_SECONDS = 180.0
K8S_JOB_TIMEOUT_SECONDS = float(os.environ.get("NSS_E2E_JOB_TIMEOUT_SECONDS", "5400"))
POLL_INTERVAL_SECONDS = float(os.environ.get("NSS_E2E_POLL_INTERVAL_SECONDS", "10"))
RESULT_DOWNLOAD_TIMEOUT_SECONDS = float(os.environ.get("NSS_E2E_RESULT_DOWNLOAD_TIMEOUT_SECONDS", "600"))
MODEL_FILESETS_TIMEOUT_SECONDS = float(os.environ.get("NSS_E2E_MODEL_FILESETS_TIMEOUT_SECONDS", "300"))
DELETE_VERIFY_TIMEOUT_SECONDS = float(os.environ.get("NSS_E2E_DELETE_VERIFY_TIMEOUT_SECONDS", "60"))
DEFAULT_INPUT_ROWS = int(os.environ.get("NSS_E2E_INPUT_ROWS", "250"))
DEFAULT_NUM_RECORDS = int(os.environ.get("NSS_E2E_NUM_RECORDS", "250"))

NssJobFactory = Callable[[str, str, dict[str, Any]], dict[str, Any]]


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _string_headers(sdk: NeMoPlatform) -> dict[str, str]:
    return {key: value for key, value in sdk.default_headers.items() if isinstance(value, str)}


def _nss_url(sdk: NeMoPlatform, workspace: str, path: str) -> str:
    return f"{str(sdk.base_url).rstrip('/')}/apis/safe-synthesizer/v2/workspaces/{workspace}/{path.lstrip('/')}"


def _files_client(sdk: NeMoPlatform) -> FilesClient:
    return client_from_platform(sdk, FilesClient)


def _create_fileset(sdk: NeMoPlatform, workspace: str, name: str) -> None:
    _files_client(sdk).create_fileset(
        workspace=workspace,
        body=CreateFilesetRequest(
            name=name,
            description="Safe Synthesizer E2E fileset",
        ),
    )


def _delete_fileset(sdk: NeMoPlatform, workspace: str, name: str) -> None:
    with suppress(Exception):
        _files_client(sdk).delete_fileset(name=name, workspace=workspace)


def _dataset_csv(rows: int = DEFAULT_INPUT_ROWS) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "record_id",
            "name",
            "email",
            "phone_number",
            "city",
            "signup_date",
            "favorite_ice_cream_flavor",
            "review",
            "rating",
        ],
    )
    writer.writeheader()
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]
    flavors = ["Vanilla", "Chocolate", "Strawberry", "Mint Chip", "Coffee"]
    for index in range(1, rows + 1):
        writer.writerow(
            {
                "record_id": str(index),
                "name": f"Customer {index}",
                "email": f"customer{index}@example.com",
                "phone_number": f"415-555-{index % 10000:04d}",
                "city": cities[index % len(cities)],
                "signup_date": f"2024-{(index % 12) + 1:02d}-{(index % 27) + 1:02d}",
                "favorite_ice_cream_flavor": flavors[index % len(flavors)],
                "review": f"Customer {index} asked support to call 415-555-{index % 10000:04d}.",
                "rating": str((index % 5) + 1),
            }
        )
    return output.getvalue()


def _upload_dataset(sdk: NeMoPlatform, workspace: str, *, rows: int = DEFAULT_INPUT_ROWS) -> tuple[str, str]:
    fileset = _unique_name("nss-inputs")
    _create_fileset(sdk, workspace, fileset)
    sdk.files.upload_content(
        fileset=fileset,
        workspace=workspace,
        remote_path=INPUT_REMOTE_PATH,
        content=_dataset_csv(rows),
    )
    return fileset, f"{workspace}/{fileset}#{INPUT_REMOTE_PATH}"


def _job_payload(
    name: str,
    data_source: str,
    config: dict[str, Any],
    *,
    description: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "spec": {
            "data_source": data_source,
            "config": config,
        },
    }
    if description is not None:
        payload["description"] = description
    return payload


def _create_nss_job(
    sdk: NeMoPlatform,
    workspace: str,
    *,
    name: str,
    data_source: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    response = sdk._client.post(
        _nss_url(sdk, workspace, "jobs"),
        json=_job_payload(name, data_source, config),
        headers=_string_headers(sdk),
        timeout=60.0,
    )
    assert response.status_code == 201, f"Failed to create Safe Synthesizer job: {response.text}"
    return response.json()


def _list_nss_jobs(sdk: NeMoPlatform, workspace: str) -> dict[str, Any]:
    response = sdk._client.get(
        _nss_url(sdk, workspace, "jobs"),
        headers=_string_headers(sdk),
        timeout=60.0,
    )
    assert response.status_code == 200, f"Failed to list Safe Synthesizer jobs: {response.text}"
    return response.json()


def _job_names(jobs: dict[str, Any]) -> set[str]:
    return {str(entry["name"]) for entry in jobs.get("data", [])}


def _retrieve_nss_job(sdk: NeMoPlatform, workspace: str, name: str) -> dict[str, Any]:
    response = sdk._client.get(
        _nss_url(sdk, workspace, f"jobs/{name}"),
        headers=_string_headers(sdk),
        timeout=60.0,
    )
    assert response.status_code == 200, f"Failed to retrieve Safe Synthesizer job {name}: {response.text}"
    return response.json()


def _wait_for_job_absent(
    sdk: NeMoPlatform,
    workspace: str,
    name: str,
    *,
    timeout_seconds: float = DELETE_VERIFY_TIMEOUT_SECONDS,
    poll_interval_seconds: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_names: set[str] = set()
    while time.monotonic() < deadline:
        last_names = _job_names(_list_nss_jobs(sdk, workspace))
        if name not in last_names:
            return
        time.sleep(poll_interval_seconds)
    pytest.fail(f"Safe Synthesizer job {name!r} still exists after delete; visible jobs: {sorted(last_names)}")


def _delete_nss_job(sdk: NeMoPlatform, workspace: str, name: str, *, verify: bool = True) -> None:
    response = sdk._client.delete(
        _nss_url(sdk, workspace, f"jobs/{name}"),
        headers=_string_headers(sdk),
        timeout=60.0,
    )
    if response.status_code not in {200, 202, 204, 404}:
        response.raise_for_status()
    if verify:
        _wait_for_job_absent(sdk, workspace, name)


def _cancel_nss_job(sdk: NeMoPlatform, workspace: str, name: str) -> dict[str, Any] | None:
    response = sdk._client.post(
        _nss_url(sdk, workspace, f"jobs/{name}/cancel"),
        headers=_string_headers(sdk),
        timeout=60.0,
    )
    if response.status_code in {404, 409}:
        return None
    assert response.status_code == 200, f"Failed to cancel Safe Synthesizer job {name}: {response.text}"
    return response.json()


def _list_nss_results(sdk: NeMoPlatform, workspace: str, job_name: str) -> dict[str, Any]:
    response = sdk._client.get(
        _nss_url(sdk, workspace, f"jobs/{job_name}/results"),
        headers=_string_headers(sdk),
        timeout=RESULT_DOWNLOAD_TIMEOUT_SECONDS,
    )
    assert response.status_code == 200, f"Failed to list Safe Synthesizer results for {job_name}: {response.text}"
    return response.json()


def _download_nss_result(sdk: NeMoPlatform, workspace: str, job_name: str, result_name: str) -> bytes:
    response = sdk._client.get(
        _nss_url(sdk, workspace, f"jobs/{job_name}/results/{result_name}/download"),
        headers=_string_headers(sdk),
        timeout=RESULT_DOWNLOAD_TIMEOUT_SECONDS,
    )
    assert response.status_code == 200, (
        f"Failed to download Safe Synthesizer result {result_name!r} for {job_name}: {response.text}"
    )
    return response.content


def _result_names(results: dict[str, Any]) -> set[str]:
    return {str(result["name"]) for result in results.get("data", [])}


def _status_details(sdk: NeMoPlatform, workspace: str, job_name: str) -> str:
    details = [f"Safe Synthesizer job {job_name} did not complete successfully."]
    with suppress(Exception):
        job = sdk.jobs.retrieve(job_name, workspace=workspace)
        details.append(f"Job: {job.model_dump_json(indent=2)}")
    with suppress(Exception):
        status = sdk.jobs.get_status(job_name, workspace=workspace)
        details.append(f"Status: {status.model_dump_json(indent=2)}")
    with suppress(Exception):
        logs = sdk.jobs.get_logs(job_name, workspace=workspace)
        tail = logs.data[-30:] if logs.data else []
        details.append("Recent logs:")
        details.extend(f"[{entry.job_step}] {entry.message}" for entry in tail)
    return "\n".join(details)


def _wait_for_status(
    sdk: NeMoPlatform,
    workspace: str,
    job_name: str,
    *,
    target_statuses: set[str] | None = None,
    timeout_seconds: float,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> tuple[str, list[str]]:
    target_statuses = target_statuses or TERMINAL_STATUSES
    deadline = time.monotonic() + timeout_seconds
    history: list[str] = []
    last_error: BaseException | None = None

    while time.monotonic() < deadline:
        try:
            status_info = sdk.jobs.get_status(job_name, workspace=workspace)
            status = str(status_info.status)
            if not history or history[-1] != status:
                history.append(status)
            if status in target_statuses:
                return status, history
        except Exception as exc:
            last_error = exc
        time.sleep(poll_interval_seconds)

    detail = _status_details(sdk, workspace, job_name)
    if last_error is not None:
        detail = f"{detail}\nLast polling error: {last_error!r}"
    raise TimeoutError(
        f"Timed out waiting for {job_name} to reach {sorted(target_statuses)}; history={history}\n{detail}"
    )


def _assert_job_completed(sdk: NeMoPlatform, workspace: str, job_name: str) -> list[str]:
    status, history = _wait_for_status(
        sdk,
        workspace,
        job_name,
        timeout_seconds=K8S_JOB_TIMEOUT_SECONDS,
    )
    assert status == "completed", _status_details(sdk, workspace, job_name)
    assert any(seen in STARTED_STATUSES for seen in history), f"Unexpected job status history: {history}"
    return history


def _assert_csv_rows(content: bytes, *, expected_rows: int | None = None, min_rows: int = 1) -> list[dict[str, str]]:
    text = content.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) >= min_rows, f"Expected at least {min_rows} CSV rows, got {len(rows)}. Content: {text[:500]}"
    if expected_rows is not None:
        assert len(rows) == expected_rows, f"Expected {expected_rows} CSV rows, got {len(rows)}"
    return rows


def _assert_known_pii_replaced(content: bytes) -> None:
    text = content.decode("utf-8")
    for source_value in ("customer1@example.com", "customer250@example.com", "415-555-0001", "415-555-0250"):
        assert source_value not in text


def _process_output_text(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _platform_root() -> Path:
    candidates: list[Path] = []
    if os.environ.get("NMP_PLATFORM_ROOT"):
        candidates.append(Path(os.environ["NMP_PLATFORM_ROOT"]))
    candidates.extend(
        [
            Path(__file__).resolve().parents[1],
            Path.cwd() / "platform",
            Path.cwd(),
        ]
    )
    for candidate in candidates:
        script = candidate / "plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py"
        if script.is_file():
            return candidate
    raise FileNotFoundError("Could not locate plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py")


@pytest.fixture(scope="module")
def nss_model_filesets(sdk: NeMoPlatform) -> None:
    if os.environ.get("NSS_E2E_SKIP_MODEL_FILESETS") == "1":
        return

    platform_root = _platform_root()
    script = platform_root / "plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py"
    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "--project",
                str(platform_root),
                "python",
                str(script),
                "--files-api-url",
                str(sdk.base_url).rstrip("/"),
                "--workspace",
                "default",
            ],
            cwd=platform_root,
            timeout=MODEL_FILESETS_TIMEOUT_SECONDS,
            check=False,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"Timed out after {MODEL_FILESETS_TIMEOUT_SECONDS:g}s registering Safe Synthesizer model filesets\n"
            f"stdout:\n{_process_output_text(exc.stdout)}\n"
            f"stderr:\n{_process_output_text(exc.stderr)}"
        )
    if result.returncode != 0:
        pytest.fail(
            f"Failed to register Safe Synthesizer model filesets\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@pytest.fixture
def nss_dataset(sdk: NeMoPlatform, workspace: str) -> Iterator[tuple[str, str]]:
    fileset, data_source = _upload_dataset(sdk, workspace)
    try:
        yield fileset, data_source
    finally:
        _delete_fileset(sdk, workspace, fileset)


@pytest.fixture
def nss_job(sdk: NeMoPlatform, workspace: str) -> Iterator[NssJobFactory]:
    job_names: list[str] = []

    def create(prefix: str, data_source: str, config: dict[str, Any]) -> dict[str, Any]:
        job_name = _unique_name(prefix)
        job = _create_nss_job(sdk, workspace, name=job_name, data_source=data_source, config=config)
        job_names.append(job_name)
        return job

    try:
        yield create
    finally:
        for job_name in reversed(job_names):
            _cancel_nss_job(sdk, workspace, job_name)
            _delete_nss_job(sdk, workspace, job_name)


def test_safe_synthesizer_api_health(sdk: NeMoPlatform, workspace: str) -> None:
    response = sdk._client.get(
        f"{str(sdk.base_url).rstrip('/')}/status",
        headers=_string_headers(sdk),
        timeout=60.0,
    )
    response.raise_for_status()
    ready_services = response.json().get("services", {}).get("ready", [])
    assert "safe-synthesizer" in ready_services

    jobs = _list_nss_jobs(sdk, workspace)
    assert isinstance(jobs.get("data"), list)


def test_safe_synthesizer_fileset_upload_download_round_trips(
    sdk: NeMoPlatform,
    workspace: str,
    nss_dataset: tuple[str, str],
) -> None:
    fileset, _ = nss_dataset
    downloaded = sdk.files.download_content(
        fileset=fileset,
        workspace=workspace,
        remote_path=INPUT_REMOTE_PATH,
    )

    assert downloaded.decode("utf-8") == _dataset_csv()


def test_safe_synthesizer_job_create_list_retrieve_cancel_delete(
    sdk: NeMoPlatform,
    workspace: str,
    nss_dataset: tuple[str, str],
    nss_job: NssJobFactory,
) -> None:
    _, data_source = nss_dataset

    job = nss_job(
        "nss-smoke",
        data_source,
        {
            "enable_synthesis": False,
            "enable_replace_pii": False,
        },
    )
    job_name = str(job["name"])
    assert job["name"] == job_name

    jobs = _list_nss_jobs(sdk, workspace)
    assert job_name in _job_names(jobs)

    retrieved = _retrieve_nss_job(sdk, workspace, job_name)
    assert retrieved["name"] == job_name
    assert retrieved["spec"]["data_source"] == data_source

    cancel_response = _cancel_nss_job(sdk, workspace, job_name)
    status, _ = _wait_for_status(
        sdk,
        workspace,
        job_name,
        timeout_seconds=SMOKE_JOB_TIMEOUT_SECONDS,
        poll_interval_seconds=2.0,
    )
    assert status != "error"
    if cancel_response is not None:
        assert status == "cancelled"


@pytest.mark.container_only
@pytest.mark.requires_gpu
@pytest.mark.slow
@pytest.mark.timeout(7200)
def test_safe_synthesizer_k8s_job_cancel_transitions(
    sdk: NeMoPlatform,
    workspace: str,
    nss_dataset: tuple[str, str],
    nss_job: NssJobFactory,
    nss_model_filesets: None,
) -> None:
    _, data_source = nss_dataset
    job = nss_job(
        "nss-cancel",
        data_source,
        {
            "enable_synthesis": True,
            "enable_replace_pii": False,
            "generation": {"num_records": DEFAULT_NUM_RECORDS},
            "evaluation": {"enabled": False},
            "privacy": {"dp_enabled": False},
        },
    )
    job_name = str(job["name"])

    _, history = _wait_for_status(
        sdk,
        workspace,
        job_name,
        target_statuses=STARTED_STATUSES,
        timeout_seconds=300,
    )
    assert "error" not in history
    cancel_response = _cancel_nss_job(sdk, workspace, job_name)
    assert cancel_response is not None

    final_status, final_history = _wait_for_status(
        sdk,
        workspace,
        job_name,
        timeout_seconds=600,
    )
    assert final_status == "cancelled"
    assert "cancelled" in final_history


@pytest.mark.container_only
@pytest.mark.requires_gpu
@pytest.mark.slow
@pytest.mark.timeout(7200)
def test_safe_synthesizer_pii_replacement_job_completes(
    sdk: NeMoPlatform,
    workspace: str,
    nss_dataset: tuple[str, str],
    nss_job: NssJobFactory,
    nss_model_filesets: None,
) -> None:
    _, data_source = nss_dataset
    job = nss_job(
        "nss-pii",
        data_source,
        {
            "enable_synthesis": False,
            "enable_replace_pii": True,
        },
    )
    job_name = str(job["name"])

    _assert_job_completed(sdk, workspace, job_name)
    results = _list_nss_results(sdk, workspace, job_name)
    assert {"summary", "synthetic-data"}.issubset(_result_names(results))
    synthetic_content = _download_nss_result(sdk, workspace, job_name, "synthetic-data")
    _assert_csv_rows(
        synthetic_content,
        expected_rows=DEFAULT_INPUT_ROWS,
    )
    _assert_known_pii_replaced(synthetic_content)
    summary = json.loads(_download_nss_result(sdk, workspace, job_name, "summary"))
    assert summary.get("timing") is not None


@pytest.mark.container_only
@pytest.mark.requires_gpu
@pytest.mark.slow
@pytest.mark.timeout(7200)
def test_safe_synthesizer_full_workflow_downloads_artifacts(
    sdk: NeMoPlatform,
    workspace: str,
    nss_dataset: tuple[str, str],
    nss_job: NssJobFactory,
    nss_model_filesets: None,
) -> None:
    _, data_source = nss_dataset
    job = nss_job(
        "nss-full",
        data_source,
        {
            "enable_synthesis": True,
            "enable_replace_pii": True,
            "generation": {"num_records": DEFAULT_NUM_RECORDS},
            "evaluation": {"enabled": True},
            "privacy": {"dp_enabled": False},
        },
    )
    job_name = str(job["name"])

    _assert_job_completed(sdk, workspace, job_name)
    results = _list_nss_results(sdk, workspace, job_name)
    result_names = _result_names(results)
    assert {"summary", "synthetic-data", "evaluation-report", "adapter"}.issubset(result_names)

    synthetic_rows = _assert_csv_rows(
        _download_nss_result(sdk, workspace, job_name, "synthetic-data"),
        expected_rows=DEFAULT_NUM_RECORDS,
    )
    assert set(synthetic_rows[0]) >= {"name", "email", "favorite_ice_cream_flavor"}

    summary = json.loads(_download_nss_result(sdk, workspace, job_name, "summary"))
    timing = summary["timing"]
    assert timing["training_time_sec"] is not None
    assert timing["generation_time_sec"] is not None

    report = _download_nss_result(sdk, workspace, job_name, "evaluation-report")
    assert b"<html" in report.lower() or b"<!doctype html" in report.lower()
