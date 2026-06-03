"""E2E tests for real platform jobs.

These focus on the live jobs API and container execution path, including logs,
config injection, inter-step storage, secrets, and lifecycle controls.
"""

from collections.abc import Callable
from uuid import uuid4

import pytest
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    PlatformJobSpec,
    PlatformJobStep,
)
from nmp.testing.e2e import wait_for_job_logs, wait_for_platform_job

JOB_SOURCE = "e2e-test-jobs"

pytestmark = [pytest.mark.timeout(600)]


def _single_step_job(
    *,
    image: str,
    name: str,
    command: list[str],
    entrypoint: list[str] | None = None,
    config: dict[str, object] | None = None,
    environment: list[EnvironmentVariable] | None = None,
) -> PlatformJobSpec:
    container = (
        ContainerSpec(image=image, command=command, entrypoint=entrypoint)
        if entrypoint is not None
        else ContainerSpec(image=image, command=command)
    )

    executor = CPUExecutionProviderSpec(provider="cpu", container=container)
    if config is not None and environment is not None:
        step = PlatformJobStep(name=name, executor=executor, config=config, environment=environment)
    elif config is not None:
        step = PlatformJobStep(name=name, executor=executor, config=config)
    elif environment is not None:
        step = PlatformJobStep(name=name, executor=executor, environment=environment)
    else:
        step = PlatformJobStep(name=name, executor=executor)

    return PlatformJobSpec(steps=[step])


def _job_diagnostic_message(sdk: NeMoPlatform, job_name: str, workspace: str, prefix: str) -> str:
    parts = [prefix]
    try:
        job = sdk.jobs.retrieve(job_name, workspace=workspace)
        parts.append(f"Job status: {job.status}")
        parts.append(f"Job status details: {job.status_details}")
        parts.append(f"Job error details: {job.error_details}")
    except Exception as exc:
        parts.append(f"Could not retrieve job: {exc}")

    try:
        steps = list(sdk.jobs.steps.list(job_name, workspace=workspace))
        if steps:
            parts.append("Steps:")
            for step in steps:
                parts.append(
                    f"  - {step.name}: status={step.status} status_details={step.status_details} error_details={step.error_details}"
                )
                tasks_response = sdk.jobs.tasks.list(step.name, job=job_name, workspace=workspace)
                for task in tasks_response.data:
                    parts.append(
                        f"    task {task.name}: status={task.status} status_details={task.status_details} error_details={task.error_details} error_stack={task.error_stack}"
                    )
    except Exception as exc:
        parts.append(f"Could not list steps/tasks: {exc}")

    try:
        logs = sdk.jobs.get_logs(workspace=workspace, name=job_name)
        if logs.data:
            parts.append("Logs:")
            for entry in logs.data:
                parts.append(f"  - {entry.message}")
    except Exception as exc:
        parts.append(f"Could not fetch logs: {exc}")

    return "\n".join(parts)


def test_basic_platform_job_lifecycle(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "basic"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="echo-step",
            command=["echo", "Hello from e2e test!"],
        ),
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed"

    logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=1, timeout=240)
    assert "Hello from e2e test!" in " ".join(log.message for log in logs.data)


def test_job_logs_across_multiple_batches(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    num_logs = 5
    delay_seconds = 2
    log_command = "; ".join(
        [f'echo "Log message {i} of {num_logs}"; sleep {delay_seconds}' for i in range(1, num_logs + 1)]
    )

    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "multi-batch-logs"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="multi-log-step",
            command=["sh", "-c", log_command],
        ),
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace, timeout=120)
    assert completed_job.status == "completed"

    logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=num_logs, timeout=120)
    assert len(logs.data) == num_logs
    for i in range(1, num_logs + 1):
        assert f"Log message {i} of {num_logs}" in logs.data[i - 1].message


def test_job_config_is_readable(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "config"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="config-step",
            command=["sh", "-c", "echo 'Step config:'; cat \"$NEMO_JOB_STEP_CONFIG_FILE_PATH\";"],
            config={"message": "Hello from job config!"},
        ),
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed"

    logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=2, timeout=60)
    assert "Hello from job config!" in " ".join(log.message for log in logs.data)


@pytest.mark.flaky(reruns=2, reruns_delay=5)
def test_job_passing_data_between_steps(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "step-data"},
        platform_spec=PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="generate-data-step",
                    executor=CPUExecutionProviderSpec(
                        provider="cpu",
                        container=ContainerSpec(
                            image=image("nmp-cpu-tasks"),
                            command=[
                                "sh",
                                "-c",
                                "echo 'Data from first step' > \"$NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH/data.txt\"",
                            ],
                        ),
                    ),
                    environment=[
                        EnvironmentVariable(
                            name="NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH",
                            value="/mnt/persistent_storage",
                        )
                    ],
                ),
                PlatformJobStep(
                    name="consume-data-step",
                    executor=CPUExecutionProviderSpec(
                        provider="cpu",
                        container=ContainerSpec(
                            image=image("nmp-cpu-tasks"),
                            command=[
                                "sh",
                                "-c",
                                "echo 'Consuming data:'; cat \"$NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH/data.txt\"",
                            ],
                        ),
                    ),
                    environment=[
                        EnvironmentVariable(
                            name="NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH",
                            value="/mnt/persistent_storage",
                        )
                    ],
                ),
            ]
        ),
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed", _job_diagnostic_message(
        sdk,
        job.name,
        workspace,
        "Expected shared persistent storage to work across steps.",
    )

    logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=2, timeout=60)
    assert "Data from first step" in logs.data[-1].message


def test_job_using_secret_environment_variable(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    secret_name = f"e2e-secret-{uuid4().hex[:8]}"
    secret = sdk.secrets.create(
        workspace=workspace,
        name=secret_name,
        value="3",
    )

    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "secret-env"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="secret-envvar-step",
            command=["sh", "-c", 'test "$SECRET_ENV_VAR" = "3" && echo "Secret env var was injected"'],
            environment=[
                EnvironmentVariable(
                    name="SECRET_ENV_VAR",
                    from_secret=EnvironmentVariableFromSecret(name=secret.name),
                )
            ],
        ),
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed"

    logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=1, timeout=120)
    log_text = " ".join(log.message for log in logs.data)
    assert "Secret env var was injected" in log_text
    assert "3" not in log_text


@pytest.mark.flaky(reruns=2, reruns_delay=5)
def test_job_with_expected_failure(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "expected-failure"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="failing-step",
            command=["sh", "-c", "echo 'This step will fail'; exit 1;"],
        ),
    )

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "error"

    logs = wait_for_job_logs(sdk, job.name, workspace, min_log_count=1, timeout=30)
    assert "This step will fail" in logs.data[0].message


def test_job_cancel_immediately(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "cancel-immediate"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="cancel-immediate-step",
            command=["sh", "-c", "sleep 60"],
        ),
    )

    sdk.jobs.cancel(workspace=workspace, name=job.name)

    cancelled_job = wait_for_platform_job(sdk, job.name, workspace)
    assert cancelled_job.status == "cancelled"


@pytest.mark.flaky(reruns=2, reruns_delay=5)
def test_job_cancel_once_active(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "cancel-active"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="cancel-active-step",
            entrypoint=["nemo-platform"],
            command=["run", "task", "--task", "nmp.hello_world.tasks.hello_world"],
        ),
    )

    active_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="active")
    assert active_job.status == "active"

    sdk.jobs.cancel(workspace=workspace, name=job.name)

    cancelled_job = wait_for_platform_job(sdk, job.name, workspace)
    assert cancelled_job.status == "cancelled"


@pytest.mark.flaky(reruns=3, reruns_delay=5)
def test_job_pause_resume(sdk: NeMoPlatform, workspace: str, image: Callable[[str], str]):
    job = sdk.jobs.create(
        workspace=workspace,
        source=JOB_SOURCE,
        spec={"test": "pause-resume"},
        platform_spec=_single_step_job(
            image=image("nmp-cpu-tasks"),
            name="pause-resume-step",
            entrypoint=["nemo-platform"],
            command=["run", "task", "--task", "nmp.hello_world.tasks.hello_world"],
            environment=[EnvironmentVariable(name="BUSY_LOOP_DURATION_SECONDS", value="120")],
        ),
    )

    active_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="active")
    assert active_job.status == "active"

    sdk.jobs.pause(workspace=workspace, name=job.name)

    paused_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="paused")
    assert paused_job.status == "paused", _job_diagnostic_message(
        sdk,
        job.name,
        workspace,
        "Expected the job to reach paused after pause().",
    )

    sdk.jobs.resume(workspace=workspace, name=job.name)

    resumed_job = wait_for_platform_job(sdk, job.name, workspace, status_to_check="active")
    assert resumed_job.status in ("active", "completed")

    completed_job = wait_for_platform_job(sdk, job.name, workspace)
    assert completed_job.status == "completed"
