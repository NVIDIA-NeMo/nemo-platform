# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import time
from unittest.mock import patch

from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.core.jobs.app.providers import SubprocessExecutionProvider
from nmp.core.jobs.controllers.backends.subprocess import (
    SubprocessJobBackend,
    SubprocessJobExecutionProfileConfig,
    SubprocessProcessKey,
)


def _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config) -> SubprocessJobBackend:
    with patch("nmp.core.jobs.controllers.backends.subprocess.get_platform_config", return_value=mock_platform_config):
        return SubprocessJobBackend(
            mock_nmp_client,
            SubprocessJobExecutionProfileConfig(working_directory=str(tmp_path)),
            profile_name="subprocess",
        )


def _step_with_command(step, command: list[str]):
    updated_step = step.model_copy(deep=True)
    updated_step.step_spec.executor = SubprocessExecutionProvider(
        provider="subprocess", profile="default", command=command
    )
    return updated_step


def _step_with_unvalidated_command(step, command: list[str]):
    updated_step = step.model_copy(deep=True)
    updated_step.step_spec.executor = SubprocessExecutionProvider.model_construct(
        provider="subprocess", profile="default", command=command
    )
    return updated_step


def _step_named(step, name: str):
    updated_step = step.model_copy(deep=True)
    updated_step.id = f"{step.id}-{name}"
    updated_step.name = name
    updated_step.step_spec.name = name
    return updated_step


def _schedule_without_otel_export(backend: SubprocessJobBackend, step):
    with patch("nmp.core.jobs.controllers.backends.subprocess.create_otel_logger", return_value=None):
        return backend.schedule(step.step_spec.executor, step)


def test_schedule_starts_process_and_stages_environment(
    mock_nmp_client, tmp_path, mock_platform_config, test_step_pending
):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_command(test_step_pending, ["/bin/sh", "-c", "printf 'hello local\\n'"])

    update = _schedule_without_otel_export(backend, step)

    assert update.status == PlatformJobStatus.PENDING
    key = SubprocessProcessKey(step.workspace, step.job, str(step.attempt_id), step.name)
    metadata = backend._process_registry.get(key)
    assert metadata is not None
    assert metadata.process.wait(timeout=5) == 0
    assert metadata.work_dir.is_relative_to(tmp_path)
    assert metadata.persistent_dir.is_relative_to(tmp_path)
    mock_nmp_client.jobs.tasks.create_or_update.assert_called()


def test_subprocess_persistent_storage_is_shared_across_job_attempt(
    mock_nmp_client, tmp_path, mock_platform_config, test_step_pending
):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    first_step = _step_with_command(_step_named(test_step_pending, "first-step"), ["/bin/sh", "-c", "true"])
    second_step = _step_with_command(_step_named(test_step_pending, "second-step"), ["/bin/sh", "-c", "true"])

    _schedule_without_otel_export(backend, first_step)
    _schedule_without_otel_export(backend, second_step)

    first_metadata = backend._process_registry.get(
        SubprocessProcessKey(first_step.workspace, first_step.job, str(first_step.attempt_id), first_step.name)
    )
    second_metadata = backend._process_registry.get(
        SubprocessProcessKey(second_step.workspace, second_step.job, str(second_step.attempt_id), second_step.name)
    )
    assert first_metadata is not None
    assert second_metadata is not None
    assert first_metadata.process.wait(timeout=5) == 0
    assert second_metadata.process.wait(timeout=5) == 0
    assert first_metadata.work_dir != second_metadata.work_dir
    assert first_metadata.persistent_dir == second_metadata.persistent_dir
    assert (
        first_metadata.persistent_dir
        == tmp_path / first_step.workspace / first_step.job / str(first_step.attempt_id) / "job-storage"
    )


def test_schedule_uses_allowlisted_host_environment(mock_nmp_client, tmp_path, mock_platform_config, test_step_pending):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_command(
        test_step_pending,
        [
            "/bin/sh",
            "-c",
            (
                'test "$PATH" = "/bin" && '
                'test "$VIRTUAL_ENV" = "/venv" && '
                'test -z "${HOME+x}" && '
                'test -z "${SECRET_TOKEN+x}"'
            ),
        ],
    )

    with (
        patch.dict(
            os.environ,
            {"HOME": "/home/test", "PATH": "/bin", "VIRTUAL_ENV": "/venv", "SECRET_TOKEN": "do-not-leak"},
            clear=True,
        ),
        patch("nmp.core.jobs.controllers.backends.subprocess.create_otel_logger", return_value=None),
    ):
        update = backend.schedule(step.step_spec.executor, step)

    assert update.status == PlatformJobStatus.PENDING
    metadata = backend._process_registry.get(
        SubprocessProcessKey(step.workspace, step.job, str(step.attempt_id), step.name)
    )
    assert metadata is not None
    assert metadata.process.wait(timeout=5) == 0


def test_schedule_terminates_process_when_post_popen_setup_fails(
    mock_nmp_client, tmp_path, mock_platform_config, test_step_pending
):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_command(test_step_pending, ["/bin/sh", "-c", "sleep 30"])

    with (
        patch(
            "nmp.core.jobs.controllers.backends.subprocess.create_otel_logger", side_effect=RuntimeError("otel boom")
        ),
        patch.object(backend, "_terminate_process_group", wraps=backend._terminate_process_group) as mock_terminate,
    ):
        update = backend.schedule(step.step_spec.executor, step)

    assert update.status == PlatformJobStatus.ERROR
    assert "initialize subprocess runtime" in update.error_details["message"]
    mock_terminate.assert_called_once()
    assert backend._process_registry.is_empty()
    assert not any(tmp_path.iterdir())


def test_sync_completed_closes_logs(mock_nmp_client, tmp_path, mock_platform_config, test_step_pending):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_command(test_step_pending, ["/bin/sh", "-c", "printf 'hello logs\\n'"])

    update = _schedule_without_otel_export(backend, step)
    assert update.status == PlatformJobStatus.PENDING
    key = SubprocessProcessKey(step.workspace, step.job, str(step.attempt_id), step.name)
    metadata = backend._process_registry.get(key)
    assert metadata is not None
    metadata.process.wait(timeout=5)

    update = backend.sync(step)

    assert update.status == PlatformJobStatus.COMPLETED
    assert metadata.closed_logs is True
    assert "hello logs" in metadata.log_path.read_text(encoding="utf-8")
    last_call = mock_nmp_client.jobs.tasks.create_or_update.call_args
    assert last_call.kwargs["status"] == PlatformJobStatus.COMPLETED.value


def test_shutdown_finishes_logs(mock_nmp_client, tmp_path, mock_platform_config, test_step_pending):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_command(test_step_pending, ["/bin/sh", "-c", "sleep 30"])
    _schedule_without_otel_export(backend, step)
    metadata = backend._process_registry.get(
        SubprocessProcessKey(step.workspace, step.job, str(step.attempt_id), step.name)
    )
    assert metadata is not None

    backend.shutdown()

    assert metadata.process.poll() is not None
    assert metadata.closed_logs is True


def test_sync_nonzero_exit_sets_error(mock_nmp_client, tmp_path, mock_platform_config, test_step_pending):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_command(test_step_pending, ["/bin/sh", "-c", "printf 'bad\\n' >&2; exit 7"])

    _schedule_without_otel_export(backend, step)
    key = SubprocessProcessKey(step.workspace, step.job, str(step.attempt_id), step.name)
    metadata = backend._process_registry.get(key)
    assert metadata is not None
    metadata.process.wait(timeout=5)

    update = backend.sync(step)

    assert update.status == PlatformJobStatus.ERROR
    assert update.error_details == {"message": "Job exited with code 7"}


def test_missing_command_fails_without_process(mock_nmp_client, tmp_path, mock_platform_config, test_step_pending):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_unvalidated_command(test_step_pending, [])

    update = backend.schedule(step.step_spec.executor, step)

    assert update.status == PlatformJobStatus.ERROR
    assert update.error_details is not None
    assert "subprocess requires" in update.error_details["message"]
    assert backend._process_registry.is_empty()


def test_build_command_uses_current_interpreter_for_python_module_commands() -> None:
    executor = SubprocessExecutionProvider(
        provider="subprocess",
        profile="default",
        command=["python", "-m", "nmp.evaluator.tasks.evaluate_metric"],
    )

    assert SubprocessJobBackend._build_command(executor, None) == [
        sys.executable,
        "-m",
        "nmp.evaluator.tasks.evaluate_metric",
    ]


def test_build_command_uses_current_interpreter_for_python3_commands() -> None:
    executor = SubprocessExecutionProvider(
        provider="subprocess",
        profile="default",
        command=["python3", "-m", "nmp.evaluator.tasks.evaluate_metric"],
    )

    assert SubprocessJobBackend._build_command(executor, None) == [
        sys.executable,
        "-m",
        "nmp.evaluator.tasks.evaluate_metric",
    ]


def test_build_command_prefers_virtual_env_python(tmp_path) -> None:
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    venv_python.chmod(0o755)
    executor = SubprocessExecutionProvider(
        provider="subprocess",
        profile="default",
        command=["python", "-m", "nmp.evaluator.tasks.evaluate_metric"],
    )

    assert SubprocessJobBackend._build_command(executor, str(tmp_path / "venv")) == [
        str(venv_python),
        "-m",
        "nmp.evaluator.tasks.evaluate_metric",
    ]


def test_schedule_python_command_does_not_depend_on_runtime_path(
    mock_nmp_client, tmp_path, mock_platform_config, test_step_pending
):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    step = _step_with_command(
        test_step_pending,
        ["python", "-c", f"import os; assert os.environ['PATH'] == {str(empty_path)!r}"],
    )

    with (
        patch.dict(os.environ, {"PATH": str(empty_path)}, clear=True),
        patch("nmp.core.jobs.controllers.backends.subprocess.create_otel_logger", return_value=None),
    ):
        update = backend.schedule(step.step_spec.executor, step)

    assert update.status == PlatformJobStatus.PENDING
    metadata = backend._process_registry.get(
        SubprocessProcessKey(step.workspace, step.job, str(step.attempt_id), step.name)
    )
    assert metadata is not None
    assert metadata.process.args[0] == sys.executable
    assert metadata.process.wait(timeout=5) == 0


def test_cancelling_terminates_running_process(mock_nmp_client, tmp_path, mock_platform_config, test_step_cancelling):
    backend = _subprocess_backend(mock_nmp_client, tmp_path, mock_platform_config)
    step = _step_with_command(test_step_cancelling, ["/bin/sh", "-c", "sleep 10"])

    _schedule_without_otel_export(backend, step)
    key = SubprocessProcessKey(step.workspace, step.job, str(step.attempt_id), step.name)
    metadata = backend._process_registry.get(key)
    assert metadata is not None
    assert metadata.process.poll() is None

    update = backend.sync(step)

    assert update.status in {PlatformJobStatus.CANCELLING, PlatformJobStatus.CANCELLED}
    for _ in range(20):
        if metadata.process.poll() is not None:
            break
        time.sleep(0.05)
    assert metadata.process.poll() is not None
