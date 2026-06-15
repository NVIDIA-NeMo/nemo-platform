"""E2E tests for platform jobs.

These tests submit jobs with CPUExecutionProviderSpec (container + command).
The container image is omitted so that:
- On subprocess mode, the cpu→subprocess translation discards it anyway.
- On Kubernetes/Docker, the execution profile's default_task_image is used.

Ported from Platform-Deploy e2e/test_jobs.py, adapted for the SDK's TypedDict
param types and filtered to tests that work without Docker.
"""

import uuid

import pytest
from nemo_platform import NeMoPlatform
from nmp.testing.e2e import wait_for_job_logs, wait_for_platform_job

JOB_SOURCE = "e2e-test-jobs"

pytestmark = [pytest.mark.timeout(600)]


def _job_diagnostic_message(sdk: NeMoPlatform, job, workspace: str, prefix: str) -> str:
    """Build a diagnostic message with job error details and logs for assertion failures."""
    parts = [prefix]
    if job.status_details:
        parts.append(f"Status details: {job.status_details}")
    if job.error_details:
        parts.append(f"Error details: {job.error_details}")
    try:
        logs = sdk.jobs.get_logs(workspace=workspace, name=job.name)
        if logs.data:
            parts.append(f"Job logs ({len(logs.data)} entries):")
            for entry in logs.data:
                parts.append(f"  - {entry.message}")
    except Exception as log_err:
        parts.append(f"Could not fetch job logs: {log_err}")
    return "\n".join(parts)


def test_basic_platform_job_lifecycle(sdk: NeMoPlatform, workspace: str):
    """Test a basic platform job lifecycle: create, run, complete.

    Verifies the platform jobs system works end-to-end:
    1. Create a job with a simple command
    2. Wait for the job to complete
    3. Verify job reaches completed status
    4. Retrieve and check step logs
    """
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "echo-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["echo", "Hello from e2e test!"],
                        },
                    },
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed", _job_diagnostic_message(
        sdk, completed_job, workspace, f"Job failed with status: {completed_job.status}"
    )

    step_logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=1, timeout=240)
    all_messages = " ".join(log.message for log in step_logs.data)
    assert "Hello from e2e test!" in all_messages, "Step logs do not contain expected output"


def test_job_logs_across_multiple_batches(sdk: NeMoPlatform, workspace: str):
    """Test that logs spanning multiple OTLP batches are correctly stored and retrieved.

    The OTLP BatchProcessor batches logs before sending, so logs output with
    delays between them will end up in different batches (and potentially
    different parquet files).
    """
    num_logs = 5
    delay_seconds = 2

    log_command = "; ".join(
        [f'echo "Log message {i} of {num_logs}"; sleep {delay_seconds}' for i in range(1, num_logs + 1)]
    )

    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "multi-batch-logs"},
        platform_spec={
            "steps": [
                {
                    "name": "multi-log-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", log_command],
                        },
                    },
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace, timeout=120)
    assert completed_job.status == "completed", _job_diagnostic_message(
        sdk, completed_job, workspace, f"Job failed with status: {completed_job.status}"
    )

    step_logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=num_logs, timeout=120)

    assert len(step_logs.data) >= num_logs, f"Expected at least {num_logs} logs, got {len(step_logs.data)}"

    # Verify all log messages are present and in order
    for i in range(1, num_logs + 1):
        expected_message = f"Log message {i} of {num_logs}"
        assert expected_message in step_logs.data[i - 1].message, (
            f"Log {i} not found at expected position. "
            f"Expected '{expected_message}', got '{step_logs.data[i - 1].message}'"
        )


def test_job_config_is_readable(sdk: NeMoPlatform, workspace: str):
    """Test that a job can read its configuration via $NEMO_JOB_STEP_CONFIG_FILE_PATH."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "config-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", "echo 'Step config:'; cat $NEMO_JOB_STEP_CONFIG_FILE_PATH;"],
                        },
                    },
                    "config": {
                        "message": "Hello from job config!",
                    },
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed", _job_diagnostic_message(
        sdk, completed_job, workspace, f"Job failed with status: {completed_job.status}"
    )

    step_logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=2, timeout=60)
    all_messages = " ".join(log.message for log in step_logs.data)
    assert "Hello from job config!" in all_messages, "Step logs do not show config was read"


def test_job_passing_data_between_steps(sdk: NeMoPlatform, workspace: str):
    """Test that data can be passed between job steps via persistent storage."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "generate-data-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": [
                                "sh",
                                "-c",
                                "echo 'Data from first step' > $NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH/data.txt",
                            ],
                        },
                    },
                },
                {
                    "name": "consume-data-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": [
                                "sh",
                                "-c",
                                "echo 'Consuming data:'; cat $NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH/data.txt",
                            ],
                        },
                    },
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed", _job_diagnostic_message(
        sdk, completed_job, workspace, f"Job failed with status: {completed_job.status}"
    )

    step_logs = sdk.jobs.get_logs(workspace=workspace, name=job.name)
    all_messages = " ".join(log.message for log in step_logs.data)
    assert "Data from first step" in all_messages, "Second step did not receive data from first step"


def test_job_using_secret_environment_variable(sdk: NeMoPlatform, workspace: str):
    """Test that a job can use secret environment variables."""
    secret_name = f"e2e-secret-{uuid.uuid4().hex[:8]}"
    secret_value = "s3cret-val"

    secret = sdk.secrets.create(workspace=workspace, name=secret_name, value=secret_value)
    assert secret.name is not None, "Failed to create platform secret"

    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "secret-envvar-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", 'echo "Secret value is: $SECRET_ENV_VAR"'],
                        },
                    },
                    "environment": [
                        {
                            "name": "SECRET_ENV_VAR",
                            "from_secret": {"name": secret.name},
                        },
                    ],
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed", _job_diagnostic_message(
        sdk, completed_job, workspace, f"Job failed with status: {completed_job.status}"
    )

    step_logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=1, timeout=120)
    all_messages = " ".join(log.message for log in step_logs.data)
    assert secret_value in all_messages, "Step logs do not show secret environment variable was used"


def test_job_with_expected_failure(sdk: NeMoPlatform, workspace: str):
    """Test that a job correctly reports failure when a step exits non-zero."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "failing-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", "echo 'This step will fail'; exit 1;"],
                        },
                    },
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "error", f"Job should have failed but has status: {completed_job.status}"

    step_logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=1, timeout=30)
    assert len(step_logs.data) == 1, "Expected one step log"
    assert "This step will fail" in step_logs.data[0].message, "Step logs do not contain expected output"


def test_job_cancel_immediately(sdk: NeMoPlatform, workspace: str):
    """Test that a job can be created and then cancelled immediately."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "long-running-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", "sleep 60"],
                        },
                    },
                },
            ],
        },
    )

    sdk.jobs.cancel(workspace=workspace, name=job.name)

    cancelled_job = wait_for_platform_job(sdk, job.name, workspace)
    assert cancelled_job.status == "cancelled", _job_diagnostic_message(
        sdk, cancelled_job, workspace, f"Job should have been cancelled but has status: {cancelled_job.status}"
    )


def test_job_cancel_once_active(sdk: NeMoPlatform, workspace: str):
    """Test that an active job can be cancelled."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "long-running-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", "sleep 300"],
                        },
                    },
                },
            ],
        },
    )

    active_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="active")
    assert active_job.status == "active", _job_diagnostic_message(
        sdk, active_job, workspace, f"Job did not become active, status: {active_job.status}"
    )

    sdk.jobs.cancel(workspace=workspace, name=job.name)

    cancelled_job = wait_for_platform_job(sdk, job.name, workspace)
    assert cancelled_job.status == "cancelled", _job_diagnostic_message(
        sdk, cancelled_job, workspace, f"Job should have been cancelled but has status: {cancelled_job.status}"
    )


# ---------------------------------------------------------------------------
# Tests that require Docker backend
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Subprocess backend does not support pause/resume (no SIGSTOP/SIGCONT handling)")
def test_job_pause_resume(sdk: NeMoPlatform, workspace: str):
    """Test that a job can be paused and then resumed after being paused."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "long-running-step-pause-resume",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", "sleep 300"],
                        },
                    },
                },
            ],
        },
    )

    active_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="active")
    assert active_job.status == "active", f"Job did not become active, status: {active_job.status}"

    sdk.jobs.pause(workspace=workspace, name=job.name)

    paused_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="paused")
    assert paused_job.status == "paused", f"Job should have been paused but has status: {paused_job.status}"

    sdk.jobs.resume(workspace=workspace, name=job.name)

    resumed_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="active")
    assert resumed_job.status in ("active", "completed"), (
        f"Job should have been resumed but has status: {resumed_job.status}"
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed", f"Job failed with status: {completed_job.status}"


@pytest.mark.skip(reason="Subprocess backend does not support pause/resume (no SIGSTOP/SIGCONT handling)")
def test_job_pause_and_cancel(sdk: NeMoPlatform, workspace: str):
    """Test that a job can be paused and then cancelled after being paused."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "long-running-step-pause-cancel",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": ["sh", "-c", "sleep 300"],
                        },
                    },
                },
            ],
        },
    )

    active_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="active")
    assert active_job.status == "active", f"Job did not become active, status: {active_job.status}"

    sdk.jobs.pause(workspace=workspace, name=job.name)

    paused_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="paused")
    assert paused_job.status == "paused", f"Job should have been paused but has status: {paused_job.status}"

    sdk.jobs.cancel(workspace=workspace, name=job.name)

    cancelled_job = wait_for_platform_job(sdk, job.name, workspace)
    assert cancelled_job.status == "cancelled", f"Job should have been cancelled but has status: {cancelled_job.status}"


@pytest.mark.skip(reason="Docker-only: additional volumes require container volume mounts")
def test_job_using_additional_volume(sdk: NeMoPlatform, workspace: str):
    """Test that a job can use an additional volume to store data between steps."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "data-between-steps"},
        platform_spec={
            "steps": [
                {
                    "name": "write-data",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": [
                                "sh",
                                "-c",
                                "echo 'Hello, World!' > /mnt/additional_storage/shared_data.txt; "
                                "echo 'Successfully wrote data to persistent storage';",
                            ],
                        },
                    },
                },
                {
                    "name": "read-data",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "command": [
                                "sh",
                                "-c",
                                "cat /mnt/additional_storage/shared_data.txt; "
                                "echo 'Successfully read data from persistent storage';",
                            ],
                        },
                    },
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed", f"Job failed with status: {completed_job.status}"

    step_logs = sdk.jobs.get_logs(workspace=workspace, name=job.name)
    assert len(step_logs.data) == 3, "Expected three step logs"
    assert "Successfully wrote data to persistent storage" in step_logs.data[0].message
    assert "Hello, World!" in step_logs.data[1].message
    assert "Successfully read data from persistent storage" in step_logs.data[2].message


@pytest.mark.skip(
    reason="Docker-only: image validation is bypassed in subprocess mode "
    "(cpu→subprocess translation discards the container image)"
)
@pytest.mark.parametrize("bad_image", ["__invalid_ubuntu:image", "ubuntu:does-not-exist-1234"])
def test_job_invalid_image_format(sdk: NeMoPlatform, workspace: str, bad_image: str):
    """Test that a job with a bad image fails appropriately."""
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "value"},
        platform_spec={
            "steps": [
                {
                    "name": "bad-image-step",
                    "executor": {
                        "provider": "cpu",
                        "container": {
                            "image": bad_image,
                            "command": ["echo", "This should not run"],
                        },
                    },
                },
            ],
        },
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "error", f"Job should have failed but has status: {completed_job.status}"

    job_status = sdk.jobs.get_status(workspace=workspace, name=job.name)
    assert job_status.steps[0].status == "error", "Step should have failed"
