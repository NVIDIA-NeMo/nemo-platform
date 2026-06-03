# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unified tests for shared MLflow and W&B training integrations."""

from pathlib import Path

import pytest
from nmp.customizer.app.jobs.context import NMPJobContext
from nmp.customizer.tasks.training.integrations import build_mlflow_config, build_wandb_config
from nmp.customizer.tasks.training.schemas import (
    MLflowConfig,
    ModelConfig,
    TrainingBackend,
    TrainingStepConfig,
    TrainingType,
    WandBConfig,
)


@pytest.fixture
def job_ctx_full(tmp_path: Path) -> NMPJobContext:
    """Create a job context with all metadata fields populated."""
    return NMPJobContext(
        workspace="test-workspace",
        job_id="job-123",
        attempt_id="attempt-1",
        step="customization-training-job",
        task="task-abc123",
        jobs_url="http://jobs.example.com",
        files_url="http://files.example.com",
        storage_path=tmp_path / "job-storage",
        config_path=tmp_path / "config.json",
    )


@pytest.fixture
def job_ctx_minimal(tmp_path: Path) -> NMPJobContext:
    """Create a job context without optional metadata tags."""
    return NMPJobContext(
        workspace="",
        job_id="",
        attempt_id="attempt-1",
        step="customization-training-job",
        task="",
        jobs_url="http://jobs.example.com",
        files_url="http://files.example.com",
        storage_path=tmp_path / "job-storage",
        config_path=tmp_path / "config.json",
    )


@pytest.fixture
def training_step_config(tmp_path: Path) -> TrainingStepConfig:
    """Create a minimal real TrainingStepConfig for integrations tests."""
    return TrainingStepConfig(
        backend=TrainingBackend.NEMO_RL,
        model=ModelConfig(path="/models/test-model", name="meta/llama-test"),
        dataset=TrainingStepConfig.DatasetConfig(path="/datasets/train"),
        training=TrainingStepConfig.TrainingConfig(training_type=TrainingType.SFT),
        schedule=TrainingStepConfig.ScheduleConfig(),
        batch=TrainingStepConfig.BatchConfig(),
        optimizer=TrainingStepConfig.OptimizerConfig(),
        parallelism=TrainingStepConfig.ParallelismConfig(),
        output_model="output-model-name",
        workspace_path=str(tmp_path),
    )


class TestBuildMlflowConfig:
    """Tests for shared MLflow integration config builder."""

    def test_returns_none_without_mlflow_integration(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
    ) -> None:
        """Should disable MLflow when integration is not configured."""
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig()

        result = build_mlflow_config(training_step_config, job_ctx_full, framework="automodel")

        assert result is None

    def test_missing_tracking_uri_warns_and_disables(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Should warn and disable MLflow when URI is missing from env and config."""
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            mlflow=MLflowConfig(experiment_name="exp-no-uri"),
        )
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        caplog.set_level("WARNING")

        result = build_mlflow_config(training_step_config, job_ctx_full, framework="automodel")

        assert result is None
        assert "MLflow integration is configured but no tracking URI is set" in caplog.text

    def test_config_tracking_uri_takes_precedence(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should prioritize integration config tracking_uri over environment variable."""
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            mlflow=MLflowConfig(
                tracking_uri="http://config-mlflow.example.com:5000",
                experiment_name="configured-experiment",
                tags={"user_tag": "user_value"},
                description="run-description",
            )
        )
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://env-mlflow.example.com:5000")

        result = build_mlflow_config(training_step_config, job_ctx_full, framework="automodel")

        assert result is not None
        assert result["tracking_uri"] == "http://config-mlflow.example.com:5000"
        assert result["experiment_name"] == "configured-experiment"
        assert result["run_name"] == "job-123"
        assert result["tags"]["service"] == "customizer"
        assert result["tags"]["framework"] == "automodel"
        assert result["tags"]["workspace"] == "test-workspace"
        assert result["tags"]["job"] == "job-123"
        assert result["tags"]["task"] == "task-abc123"
        assert result["tags"]["model_name"] == "meta/llama-test"
        assert result["tags"]["user_tag"] == "user_value"
        assert result["tags"]["mlflow.note.content"] == "run-description"

    def test_env_tracking_uri_used_when_config_uri_missing(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should use MLFLOW_TRACKING_URI env var when config tracking_uri is unset."""
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            mlflow=MLflowConfig(experiment_name="configured-experiment"),
        )
        monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://env-mlflow.example.com:5000")

        result = build_mlflow_config(training_step_config, job_ctx_full, framework="automodel")

        assert result is not None
        assert result["tracking_uri"] == "http://env-mlflow.example.com:5000"

    def test_user_tags_override_defaults(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
    ) -> None:
        """Should allow user tags to override default service/framework tags."""
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            mlflow=MLflowConfig(
                tracking_uri="http://mlflow.example.com:5000",
                tags={"service": "user-service", "framework": "user-framework"},
            )
        )

        result = build_mlflow_config(training_step_config, job_ctx_full, framework="nemo_rl")

        assert result is not None
        assert result["tags"]["service"] == "user-service"
        assert result["tags"]["framework"] == "user-framework"

    def test_omits_optional_tags_and_falls_back_to_defaults(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_minimal: NMPJobContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Should omit optional context/model tags and use default experiment/run names."""
        caplog.set_level("WARNING")
        training_step_config.model.name = None
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            mlflow=MLflowConfig(tracking_uri="http://mlflow.example.com:5000"),
        )

        result = build_mlflow_config(training_step_config, job_ctx_minimal, framework="automodel")

        assert result is not None
        assert result["experiment_name"] == "output-model-name"
        assert result["run_name"] == "default-run"
        assert result["tags"]["service"] == "customizer"
        assert result["tags"]["framework"] == "automodel"
        assert "workspace" not in result["tags"]
        assert "job" not in result["tags"]
        assert "task" not in result["tags"]
        assert "model_name" not in result["tags"]
        assert "mlflow.note.content" not in result["tags"]
        assert "MLflow run_name is not set; using fallback 'default-run'." in caplog.text


class TestBuildWandbConfig:
    """Tests for shared W&B integration config builder."""

    def test_returns_none_without_wandb_integration(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
    ) -> None:
        """Should disable W&B when integration is not configured."""
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig()

        result = build_wandb_config(training_step_config, job_ctx_full, framework="automodel")

        assert result is None

    def test_missing_base_url_and_api_key_warns_and_disables(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Should disable W&B with warning when both base_url and API key are missing."""
        monkeypatch.delenv("WANDB_API_KEY", raising=False)
        monkeypatch.delenv("WANDB_BASE_URL", raising=False)
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            wandb=WandBConfig(project="proj"),
        )
        caplog.set_level("WARNING")

        result = build_wandb_config(training_step_config, job_ctx_full, framework="automodel")

        assert result is None
        assert "no base_url is provided, skipping WandB integration" in caplog.text

    def test_builds_config_from_api_key_and_optional_fields(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should build full W&B config and include optional fields when provided."""
        monkeypatch.setenv("WANDB_API_KEY", "test-api-key")
        training_step_config.workspace_path = str(tmp_path)
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            wandb=WandBConfig(
                project="project-name",
                name="explicit-run-name",
                entity="test-entity",
                tags=["tag1", "tag2"],
                notes="test-notes",
            ),
        )

        result = build_wandb_config(training_step_config, job_ctx_full, framework="nemo_rl")

        assert result is not None
        assert result["project"] == "project-name"
        assert result["name"] == "explicit-run-name"
        assert result["dir"] == str(tmp_path / "wandb")
        assert result["entity"] == "test-entity"
        assert result["notes"] == "test-notes"
        assert result["tags"][:2] == ["service:customizer", "framework:nemo_rl"]
        assert "workspace:test-workspace" in result["tags"]
        assert "job:job-123" in result["tags"]
        assert "task:task-abc123" in result["tags"]
        assert "model:meta/llama-test" in result["tags"]
        assert "tag1" in result["tags"]
        assert "tag2" in result["tags"]

    def test_base_url_without_api_key_enables_and_sets_settings(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_full: NMPJobContext,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should enable W&B when base_url is configured even without API key."""
        monkeypatch.delenv("WANDB_API_KEY", raising=False)
        training_step_config.workspace_path = str(tmp_path)
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            wandb=WandBConfig(base_url="https://custom-wandb.example.com"),
        )

        result = build_wandb_config(training_step_config, job_ctx_full, framework="automodel")

        assert result is not None
        assert result["project"] == "output-model-name"
        assert result["name"] == "job-123"
        assert result["dir"] == str(tmp_path / "wandb")
        assert "framework:automodel" in result["tags"]
        assert result["settings"] == {"base_url": "https://custom-wandb.example.com"}

    def test_omits_optional_fields_and_context_tags_when_absent(
        self,
        training_step_config: TrainingStepConfig,
        job_ctx_minimal: NMPJobContext,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should omit optional keys and context/model tags when values are absent."""
        monkeypatch.setenv("WANDB_API_KEY", "test-api-key")
        training_step_config.model.name = None
        training_step_config.workspace_path = str(tmp_path)
        training_step_config.integrations = TrainingStepConfig.IntegrationsConfig(
            wandb=WandBConfig(project=None, entity=None, notes=None),
        )

        result = build_wandb_config(training_step_config, job_ctx_minimal, framework="automodel")

        assert result is not None
        assert result["project"] == "output-model-name"
        assert result["name"] == "default-run"
        assert "entity" not in result
        assert "notes" not in result
        assert result["tags"] == ["service:customizer", "framework:automodel"]
