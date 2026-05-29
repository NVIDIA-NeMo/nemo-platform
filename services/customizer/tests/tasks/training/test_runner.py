# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for TrainingRunner.

These tests mock all external dependencies (job context, distributed context,
progress reporter, backend) following the platform pattern of mocking at boundaries.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nmp.customizer.app.jobs.context import NMPJobContext
from nmp.customizer.tasks.training.distributed import DistributedContext, DistributedRole
from nmp.customizer.tasks.training.protocol import LibraryConfig
from nmp.customizer.tasks.training.runner import (
    BARRIER_CONFIG_READY,
    BARRIER_TRAINING_COMPLETE,
    TrainingRunner,
)
from nmp.customizer.tasks.training.schemas import (
    CheckpointFormat,
    CheckpointInfo,
    TrainingBackend,
    TrainingMetrics,
    TrainingResult,
)


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Create and return a workspace directory for tests."""
    path = tmp_path / "workspace"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create and return an output directory for tests."""
    path = tmp_path / "output"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    """Create and return a storage directory for tests."""
    path = tmp_path / "storage"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def config_file(workspace_dir: Path) -> Path:
    """Create a minimal training config file."""
    config_path = workspace_dir / "config.json"
    config_data = {
        "backend": "automodel",
        "model": {"path": "/models/test-model", "name": "test/model"},
        "dataset": {"path": "/data/train.jsonl"},
        "training": {"training_type": "sft", "finetuning_type": "lora"},
        "schedule": {"epochs": 1},
        "batch": {"global_batch_size": 8, "micro_batch_size": 1},
        "optimizer": {"learning_rate": 1e-4},
        "parallelism": {"num_nodes": 1, "num_gpus_per_node": 1},
        "output_model": "test-output-model",
        "workspace_path": str(workspace_dir),
        "output_path": str(workspace_dir / "output"),
        "seed": 42,
    }
    config_path.write_text(json.dumps(config_data))
    return config_path


@pytest.fixture
def mock_job_ctx(config_file: Path, storage_dir: Path) -> NMPJobContext:
    """Create a mock job context."""
    return NMPJobContext(
        workspace="test-workspace",
        job_id="test-job-123",
        attempt_id="attempt-1",
        step="training",
        task="train",
        jobs_url="http://jobs:8000",
        files_url="http://files:8000",
        storage_path=storage_dir,
        config_path=config_file,
    )


@pytest.fixture
def mock_dist_ctx_coordinator() -> MagicMock:
    """Create a mock coordinator distributed context."""
    ctx = MagicMock(spec=DistributedContext)
    ctx.role = DistributedRole.COORDINATOR
    ctx.rank = 0
    ctx.world_size = 1
    ctx.is_coordinator = True
    ctx.is_distributed = False
    return ctx


@pytest.fixture
def mock_dist_ctx_worker() -> MagicMock:
    """Create a mock worker distributed context."""
    ctx = MagicMock(spec=DistributedContext)
    ctx.role = DistributedRole.WORKER
    ctx.rank = 1
    ctx.world_size = 2
    ctx.is_coordinator = False
    ctx.is_distributed = True
    return ctx


@pytest.fixture
def mock_backend() -> MagicMock:
    """Create a mock training backend."""
    backend = MagicMock()
    backend.backend_type = TrainingBackend.AUTOMODEL
    backend.compile_config.return_value = {"model": {"path": "/test"}, "training": {"lr": 1e-4}}
    backend.execute_training.return_value = TrainingMetrics(total_steps=100, total_epochs=1, final_loss=0.5)
    backend.find_best_checkpoint.return_value = Path("/checkpoints/best")
    backend.process_checkpoint.return_value = CheckpointInfo(
        path="/output/model",
        format=CheckpointFormat.HF,
        precision=None,
    )
    return backend


@pytest.fixture
def mock_progress() -> MagicMock:
    """Create a mock progress reporter."""
    progress = MagicMock()
    progress.report_running = MagicMock()
    progress.report_completed = MagicMock()
    progress.report_error = MagicMock()
    progress.close = MagicMock()
    return progress


class TestTrainingRunnerInit:
    """Tests for TrainingRunner initialization."""

    def test_runner_uses_injected_backend(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test that runner uses injected backend instead of loading one."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)

            assert runner._backend is mock_backend
            # _load_backend should not have been called
            # (we can't easily verify this, but the backend should be our mock)


class TestLoadConfig:
    """Tests for config loading."""

    def test_load_config_parses_json(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test that _load_config correctly parses the config file."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)

            assert runner._config.backend == TrainingBackend.AUTOMODEL
            assert runner._config.model.path == "/models/test-model"
            assert runner._config.seed == 42


class TestCompileConfigPhase:
    """Tests for config compilation phase."""

    def test_coordinator_compiles_and_writes_config(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
        workspace_dir: Path,
    ):
        """Test that coordinator compiles config, writes to disk, and signals."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)
            library_config = runner._compile_config_phase()

            # Verify backend.compile_config was called
            mock_backend.compile_config.assert_called_once()

            # Verify progress was reported
            mock_progress.report_running.assert_called_with("compiling_config")

            # Verify config was written to disk
            config_path = runner._get_library_config_path()
            assert config_path.exists()

            # Verify barrier was signaled
            mock_dist_ctx_coordinator.signal.assert_called_with(BARRIER_CONFIG_READY)

            # Verify return value
            assert isinstance(library_config, LibraryConfig)
            assert library_config.config_dict == {"model": {"path": "/test"}, "training": {"lr": 1e-4}}

    def test_worker_waits_and_loads_config(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_worker: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
        workspace_dir: Path,
    ):
        """Test that worker waits for coordinator and loads config from disk."""
        # Pre-create the config file that coordinator would have written
        config_path = workspace_dir / f"{TrainingBackend.AUTOMODEL.value}_config.yaml"
        config_path.write_text("model:\n  path: /test\ntraining:\n  lr: 0.0001\n")

        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_worker),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)
            library_config = runner._compile_config_phase()

            # Verify worker waited for coordinator
            mock_dist_ctx_worker.wait_for_coordinator.assert_called_with(BARRIER_CONFIG_READY)

            # Verify backend.compile_config was NOT called (worker doesn't compile)
            mock_backend.compile_config.assert_not_called()

            # Verify config was loaded from disk
            assert isinstance(library_config, LibraryConfig)
            assert library_config.config_dict["model"]["path"] == "/test"


class TestTrainingPhase:
    """Tests for training execution phase."""

    def test_training_phase_calls_backend(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test that training phase delegates to backend."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)
            library_config = LibraryConfig(
                config_dict={"key": "value"},
                config_path=Path("/config.yaml"),
            )

            metrics = runner._training_phase(library_config)

            # Verify backend.execute_training was called
            mock_backend.execute_training.assert_called_once_with(
                runner._config,
                library_config,
                mock_progress,
            )

            # Verify return value
            assert metrics.total_steps == 100
            assert metrics.final_loss == 0.5


class TestPostprocessPhase:
    """Tests for post-processing phase."""

    def test_coordinator_processes_checkpoint(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test that coordinator processes checkpoint (no barrier signal needed)."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)
            metrics = TrainingMetrics(total_steps=100, total_epochs=1)
            library_config = LibraryConfig(config_dict={}, config_path=Path("/config.yaml"))

            result = runner._postprocess_phase(
                gpu_info=None,
                metrics=metrics,
                start_time=0,
                library_config=library_config,
            )

            # Verify backend methods were called
            mock_backend.find_best_checkpoint.assert_called_once()
            mock_backend.process_checkpoint.assert_called_once()

            # Verify progress was reported
            mock_progress.report_running.assert_called_with("processing_checkpoint")
            mock_progress.report_completed.assert_called_with("Training completed")

            # Verify result
            assert result.success is True
            assert result.checkpoint is not None

    def test_worker_returns_immediately(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_worker: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test that worker returns minimal success result without processing any checkpoint."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_worker),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)
            metrics = TrainingMetrics(total_steps=100, total_epochs=1)

            result = runner._postprocess_phase(
                gpu_info=None,
                metrics=metrics,
                start_time=0,
                library_config=LibraryConfig(config_dict={}, config_path=Path("/config.yaml")),
            )

            # Verify backend methods were NOT called
            mock_backend.find_best_checkpoint.assert_not_called()
            mock_backend.process_checkpoint.assert_not_called()

            # Verify result is minimal (success but no checkpoint)
            assert result.success is True
            assert result.checkpoint is None


class TestWriteResult:
    """Tests for result writing."""

    def test_coordinator_writes_result(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
        workspace_dir: Path,
    ):
        """Test that coordinator writes result to disk."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)
            result = TrainingResult(success=True)

            runner._write_result(result)

            # Verify result was written
            from nmp.customizer.app.constants import DEFAULT_TRAINING_RESULT_FILE_NAME

            result_path = workspace_dir / DEFAULT_TRAINING_RESULT_FILE_NAME
            assert result_path.exists()

            # Verify content
            written_result = TrainingResult.model_validate_json(result_path.read_text())
            assert written_result.success is True

    def test_worker_does_not_write_result(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_worker: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
        workspace_dir: Path,
    ):
        """Test that worker does not write result."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_worker),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            runner = TrainingRunner(backend=mock_backend)
            result = TrainingResult(success=True)

            runner._write_result(result)

            # Verify no result was written
            from nmp.customizer.app.constants import DEFAULT_TRAINING_RESULT_FILE_NAME

            result_path = workspace_dir / DEFAULT_TRAINING_RESULT_FILE_NAME
            assert not result_path.exists()


class TestContextManager:
    """Tests for context manager behavior."""

    def test_context_manager_closes_progress(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test that context manager closes progress reporter on exit."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
        ):
            with TrainingRunner(backend=mock_backend):
                pass  # Do nothing, just test cleanup

            mock_progress.close.assert_called_once()


class TestRunFlow:
    """Tests for the full run() flow."""

    def test_run_success_flow(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test successful training run flow."""
        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
            patch("nmp.customizer.tasks.training.runner.get_gpu_info", return_value=None),
        ):
            runner = TrainingRunner(backend=mock_backend)
            result = runner.run()

            # Verify all phases were executed
            mock_backend.compile_config.assert_called_once()
            mock_backend.execute_training.assert_called_once()
            mock_backend.find_best_checkpoint.assert_called_once()
            mock_backend.process_checkpoint.assert_called_once()

            # Verify sync point was called
            mock_dist_ctx_coordinator.sync_point.assert_called_with(BARRIER_TRAINING_COMPLETE)

            # Verify result
            assert result.success is True
            assert result.checkpoint is not None

    def test_run_worker_exits_after_training_sync(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_worker: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
        workspace_dir: Path,
    ):
        """Test that workers return success immediately after training sync without entering postprocessing."""
        # Pre-create the library config that the coordinator would have written
        config_path = workspace_dir / f"{TrainingBackend.AUTOMODEL.value}_config.yaml"
        config_path.write_text("model:\n  path: /test\ntraining:\n  lr: 0.0001\n")

        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_worker),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
            patch("nmp.customizer.tasks.training.runner.get_gpu_info", return_value=None),
        ):
            runner = TrainingRunner(backend=mock_backend)
            result = runner.run()

            # Verify training ran
            mock_backend.execute_training.assert_called_once()

            # Verify sync point was reached
            mock_dist_ctx_worker.sync_point.assert_called_with(BARRIER_TRAINING_COMPLETE)

            # Verify postprocessing was NOT entered
            mock_backend.find_best_checkpoint.assert_not_called()
            mock_backend.process_checkpoint.assert_not_called()

            # Verify result is success (no checkpoint, workers don't produce one)
            assert result.success is True
            assert result.checkpoint is None

    def test_run_handles_exception(
        self,
        mock_job_ctx: NMPJobContext,
        mock_dist_ctx_coordinator: MagicMock,
        mock_backend: MagicMock,
        mock_progress: MagicMock,
    ):
        """Test that run() handles exceptions and reports error."""
        mock_backend.execute_training.side_effect = RuntimeError("Training failed!")

        with (
            patch.object(NMPJobContext, "from_env", return_value=mock_job_ctx),
            patch.object(DistributedContext, "from_env", return_value=mock_dist_ctx_coordinator),
            patch("nmp.customizer.tasks.training.runner.JobsServiceProgressReporter", return_value=mock_progress),
            patch("nmp.customizer.tasks.training.runner.get_gpu_info", return_value=None),
        ):
            runner = TrainingRunner(backend=mock_backend)
            result = runner.run()

            # Verify error was reported with structured error details
            mock_progress.report_error.assert_called_once()
            error_details = mock_progress.report_error.call_args[0][0]
            assert isinstance(error_details, dict)
            assert error_details["type"] == "InternalError"
            assert "Training failed!" in error_details["detail"]

            # Verify result indicates failure
            assert result.success is False
            assert result.error_message is not None
            assert "internal error" in result.error_message.lower()
