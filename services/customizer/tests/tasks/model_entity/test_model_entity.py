# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the model_entity task."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from nemo_platform import APIStatusError, ConflictError, NotFoundError
from nmp.customizer.app.jobs.context import NMPJobContext
from nmp.customizer.app.jobs.file_io.schemas import FileSetRef
from nmp.customizer.app.jobs.model_entity.schemas import (
    DeploymentParameters,
    ModelEntityCreationError,
    ModelEntityTaskConfig,
    PEFTConfig,
)
from nmp.customizer.entities.values import FinetuningType
from nmp.customizer.tasks.model_entity.run import ModelEntityRunner, run
from pydantic import ValidationError
from pytest_mock import MockerFixture


@dataclass
class ModelEntityRunnerMocks:
    """Container for ModelEntityRunner mock objects."""

    sdk: MagicMock
    job_ctx: NMPJobContext


@pytest.fixture
def job_ctx(tmp_path: Path) -> NMPJobContext:
    """Fixture providing a NMPJobContext for testing.

    Creates a job context with a temporary storage path.

    Returns:
        NMPJobContext for testing.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    return NMPJobContext(
        workspace="test-workspace",
        job_id="test-job-123",
        attempt_id="attempt-0",
        step="test-step",
        task="test-task",
        jobs_url="http://jobs:8000",
        files_url="http://files:8000",
        storage_path=tmp_path,
        config_path=config_path,
    )


@pytest.fixture
def model_entity_runner_mocks(mocker: MockerFixture, job_ctx: NMPJobContext) -> ModelEntityRunnerMocks:
    """Fixture providing mocked dependencies for ModelEntityRunner.

    Creates mock SDK and job context objects.

    Returns:
        ModelEntityRunnerMocks containing all mock objects needed for ModelEntityRunner tests.
    """
    mock_sdk = mocker.MagicMock()

    return ModelEntityRunnerMocks(
        sdk=mock_sdk,
        job_ctx=job_ctx,
    )


class TestModelEntityTaskConfig:
    """Tests for ModelEntityTaskConfig schema."""

    def test_valid_config_with_all_fields(self):
        """Test creating config with all fields populated."""
        config = ModelEntityTaskConfig(
            name="my-model",
            workspace="default",
            description="A test model",
            fileset=FileSetRef(workspace="test-workspace", name="model-files"),
            model_entity="default/base-llama",
            base_model="default/base-llama",
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=16, rank=8),
        )

        assert config.name == "my-model"
        assert config.description == "A test model"
        assert config.fileset.workspace == "test-workspace"
        assert config.fileset.name == "model-files"
        assert config.base_model == "default/base-llama"
        assert config.peft.type == FinetuningType.LORA
        assert config.peft.alpha == 16

    def test_valid_config_with_minimal_fields(self):
        """Test creating config with only required fields."""
        config = ModelEntityTaskConfig(
            name="minimal-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="output-files"),
        )

        assert config.name == "minimal-model"
        assert config.description is None
        assert config.fileset.workspace is None
        assert config.fileset.name == "output-files"
        assert config.base_model is None
        assert config.peft is None

    def test_config_with_fileset_ref_without_workspace(self):
        """Test config with FileSetRef that has no workspace."""
        config = ModelEntityTaskConfig(
            name="test-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="files"),
        )

        assert config.fileset.workspace is None
        assert config.fileset.name == "files"

    def test_config_serialization(self):
        """Test that config can be serialized to JSON."""
        config = ModelEntityTaskConfig(
            name="serializable-model",
            workspace="default",
            description="Test serialization",
            fileset=FileSetRef(workspace="ws1", name="files"),
            model_entity="default/llama-base",
            base_model="ws1/base",
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
        )

        json_data = config.model_dump(mode="json")

        assert json_data["name"] == "serializable-model"
        assert json_data["description"] == "Test serialization"
        assert json_data["fileset"]["workspace"] == "ws1"
        assert json_data["fileset"]["name"] == "files"
        assert json_data["base_model"] == "ws1/base"
        assert json_data["peft"]["type"] == "lora"

    def test_config_deployment_config_string_ref(self):
        """Test that deployment_config accepts a string reference."""
        config = ModelEntityTaskConfig(
            name="ref-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="files"),
            deployment_config="my-existing-config",
        )

        assert config.deployment_config == "my-existing-config"

    def test_config_deployment_config_inline_params(self):
        """Test that deployment_config accepts inline DeploymentParameters."""
        config = ModelEntityTaskConfig(
            name="inline-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="files"),
            deployment_config=DeploymentParameters(gpu=2, lora_enabled=True),
        )

        assert isinstance(config.deployment_config, DeploymentParameters)
        assert config.deployment_config.gpu == 2

    def test_config_deployment_config_deserialization_from_string(self):
        """Test that JSON string deserializes as a config ref."""
        config = ModelEntityTaskConfig.model_validate(
            {
                "name": "test",
                "workspace": "default",
                "model_entity": "default/llama-base",
                "fileset": {"workspace": None, "name": "files"},
                "deployment_config": "my-config",
            }
        )

        assert config.deployment_config == "my-config"

    def test_config_deployment_config_deserialization_from_object(self):
        """Test that JSON object deserializes as inline DeploymentParameters."""
        config = ModelEntityTaskConfig.model_validate(
            {
                "name": "test",
                "workspace": "default",
                "model_entity": "default/llama-base",
                "fileset": {"workspace": None, "name": "files"},
                "deployment_config": {"gpu": 4, "lora_enabled": False},
            }
        )

        assert isinstance(config.deployment_config, DeploymentParameters)
        assert config.deployment_config.gpu == 4
        assert config.deployment_config.lora_enabled is False

    def test_config_validation_requires_name(self):
        """Test that name is required."""
        with pytest.raises(ValidationError) as exc_info:
            ModelEntityTaskConfig(
                fileset=FileSetRef(workspace=None, name="files"),
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) and e["type"] == "missing" for e in errors)
        assert any(e["loc"] == ("workspace",) and e["type"] == "missing" for e in errors)
        assert any(e["loc"] == ("model_entity",) and e["type"] == "missing" for e in errors)

    def test_config_validation_requires_fileset(self):
        """Test that fileset is required."""
        with pytest.raises(ValidationError) as exc_info:
            ModelEntityTaskConfig(
                name="test-model",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("fileset",) and e["type"] == "missing" for e in errors)


class TestModelEntityRunner:
    """Tests for ModelEntityRunner."""

    def test_create_model_entity_with_minimal_config(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test creating model entity with minimal configuration."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="test-model",
            workspace="default",
            model_entity="default/base-llama",
            fileset=FileSetRef(workspace=None, name="output-fileset"),
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_response = MagicMock()
        mock_response.id = "model-123"
        mock_response.name = "test-model"
        mock_response.workspace = "test-workspace"
        mock_response.model_dump.return_value = {
            "id": "model-123",
            "name": "test-model",
            "workspace": "test-workspace",
        }
        model_entity_runner_mocks.sdk.models.create.return_value = mock_response

        result, deploy_target = runner.create_model_entity(config)

        model_entity_runner_mocks.sdk.models.create.assert_called_once()
        call_kwargs = model_entity_runner_mocks.sdk.models.create.call_args[1]

        assert call_kwargs["workspace"] == "test-workspace"
        assert call_kwargs["name"] == "test-model"
        assert call_kwargs["description"] is None
        assert call_kwargs["fileset"] == "test-workspace/output-fileset"
        assert "base_model" not in call_kwargs
        assert "adapters" not in call_kwargs

        assert result == mock_response.model_dump.return_value
        assert deploy_target == mock_response

    def test_create_model_entity_with_all_fields(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test creating model entity with all fields populated."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-model",
            workspace="default",
            description="A fully configured lora adapter",
            fileset=FileSetRef(workspace="custom-ws", name="model-artifacts"),
            base_model="default/base-model",
            model_entity="default/llama-base",
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=16, rank=32),
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_base_response = MagicMock()
        mock_base_response.id = "model-123"
        mock_base_response.name = "llama-base"
        mock_base_response.workspace = "default"
        mock_base_response.model_dump.return_value = {
            "id": "model-123",
            "name": "llama-base",
            "workspace": "default",
        }
        model_entity_runner_mocks.sdk.models.retrieve.return_value = mock_base_response

        mock_adapter_response = MagicMock()
        mock_adapter_response.id = "model-456"
        mock_adapter_response.name = "lora-model"
        mock_adapter_response.workspace = "test-workspace"
        mock_adapter_response.model_dump.return_value = {
            "id": "model-456",
            "name": "lora-model",
            "workspace": "test-workspace",
        }
        model_entity_runner_mocks.sdk.models.adapters.create.return_value = mock_adapter_response

        result, deploy_target = runner.create_model_entity(config)

        model_entity_runner_mocks.sdk.models.adapters.create.assert_called_once()
        call_kwargs = model_entity_runner_mocks.sdk.models.adapters.create.call_args[1]
        assert call_kwargs["model_name"] == "llama-base"
        assert call_kwargs["workspace"] == "default"
        assert call_kwargs["name"] == "lora-model"
        assert call_kwargs["description"] == "A fully configured lora adapter"
        assert call_kwargs["fileset"] == "custom-ws/model-artifacts"
        assert call_kwargs["lora_config"]["rank"] == 32
        assert call_kwargs["lora_config"]["alpha"] == 16

        assert result == mock_adapter_response.model_dump.return_value
        assert deploy_target == mock_base_response

    def test_create_model_entity_uses_job_workspace_when_fileset_workspace_is_none(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """Test that job workspace is used when fileset workspace is None."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="workspace-test",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="files"),
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_response = MagicMock()
        mock_response.id = "model-789"
        mock_response.name = "workspace-test"
        mock_response.workspace = "test-workspace"
        mock_response.model_dump.return_value = {
            "id": "model-789",
            "name": "workspace-test",
            "workspace": "test-workspace",
        }
        model_entity_runner_mocks.sdk.models.create.return_value = mock_response

        runner.create_model_entity(config)

        call_kwargs = model_entity_runner_mocks.sdk.models.create.call_args[1]
        assert call_kwargs["fileset"] == "test-workspace/files"

    def test_create_model_entity_full_sft_without_peft(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test creating model entity with all_weights."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="peft-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="peft-files"),
            peft=None,
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_response = MagicMock()
        mock_response.id = "model-peft"
        mock_response.name = "peft-model"
        mock_response.workspace = "test-workspace"
        mock_response.model_dump.return_value = {
            "id": "model-peft",
            "name": "peft-model",
            "workspace": "test-workspace",
        }
        model_entity_runner_mocks.sdk.models.create.return_value = mock_response

        runner.create_model_entity(config)

        call_kwargs = model_entity_runner_mocks.sdk.models.create.call_args[1]
        assert call_kwargs["name"] == "peft-model"
        assert call_kwargs["finetuning_type"] == "all_weights"
        assert "fileset" in call_kwargs

    def test_create_model_entity_handles_api_error(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test that API errors are wrapped in ModelEntityCreationError."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="error-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="files"),
        )

        model_entity_runner_mocks.sdk.models.create.side_effect = APIStatusError(
            message="Model creation failed",
            response=MagicMock(status_code=500),
            body=None,
        )

        with pytest.raises(ModelEntityCreationError) as exc_info:
            runner.create_model_entity(config)

        assert "Failed to create model entity" in str(exc_info.value)

    def test_create_model_entity_handles_not_found_error(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test handling of NotFoundError (e.g., fileset doesn't exist)."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="missing-fileset-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="non-existent-fileset"),
        )

        model_entity_runner_mocks.sdk.models.create.side_effect = NotFoundError(
            message="Fileset not found",
            response=MagicMock(status_code=404),
            body=None,
        )

        with pytest.raises(ModelEntityCreationError) as exc_info:
            runner.create_model_entity(config)

        assert "Failed to create model entity" in str(exc_info.value)

    def test_create_model_entity_validates_fileset_exists(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test that fileset existence is validated before creating model entity."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="test-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="nonexistent-fileset"),
        )

        model_entity_runner_mocks.sdk.files.filesets.retrieve.side_effect = NotFoundError(
            message="Fileset not found",
            response=MagicMock(status_code=404),
            body=None,
        )

        with pytest.raises(ModelEntityCreationError) as exc_info:
            runner.create_model_entity(config)

        model_entity_runner_mocks.sdk.files.filesets.retrieve.assert_called_once_with(
            workspace="test-workspace", name="nonexistent-fileset"
        )

        model_entity_runner_mocks.sdk.models.create.assert_not_called()

        assert "fileset" in str(exc_info.value).lower()
        assert "does not exist" in str(exc_info.value).lower()

    def test_create_model_entity_updates_on_conflict(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test that ConflictError triggers an update instead of failing."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="duplicate-model",
            workspace="default",
            model_entity="default/llama-base",
            description="Updated description",
            fileset=FileSetRef(workspace=None, name="files"),
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        model_entity_runner_mocks.sdk.models.create.side_effect = ConflictError(
            message="Model already exists",
            response=MagicMock(status_code=409),
            body=None,
        )

        mock_update_response = MagicMock()
        mock_update_response.id = "model-123"
        mock_update_response.name = "duplicate-model"
        mock_update_response.workspace = "test-workspace"
        mock_update_response.model_dump.return_value = {
            "id": "model-123",
            "name": "duplicate-model",
            "workspace": "test-workspace",
        }
        model_entity_runner_mocks.sdk.models.update.return_value = mock_update_response

        result, deploy_target = runner.create_model_entity(config)

        model_entity_runner_mocks.sdk.files.filesets.retrieve.assert_called_once()
        model_entity_runner_mocks.sdk.models.create.assert_called_once()

        model_entity_runner_mocks.sdk.models.update.assert_called_once()
        update_kwargs = model_entity_runner_mocks.sdk.models.update.call_args[1]
        assert update_kwargs["workspace"] == "test-workspace"
        assert update_kwargs["name"] == "duplicate-model"
        assert update_kwargs["description"] == "Updated description"

        assert result == mock_update_response.model_dump.return_value
        assert deploy_target == mock_update_response

    def test_create_adapter_conflict_falls_back_to_update(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test that ConflictError on adapter create triggers an update with new fileset."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="existing-adapter",
            workspace="default",
            description="Retrained adapter",
            fileset=FileSetRef(workspace="custom-ws", name="new-fileset"),
            model_entity="default/llama-base",
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=16, rank=32),
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_base_response = MagicMock()
        mock_base_response.name = "llama-base"
        mock_base_response.workspace = "default"
        model_entity_runner_mocks.sdk.models.retrieve.return_value = mock_base_response

        model_entity_runner_mocks.sdk.models.adapters.create.side_effect = ConflictError(
            message="Adapter already exists",
            response=MagicMock(status_code=409),
            body=None,
        )

        mock_update_response = MagicMock()
        mock_update_response.model_dump.return_value = {
            "name": "existing-adapter",
            "fileset": "custom-ws/new-fileset",
        }
        model_entity_runner_mocks.sdk.models.adapters.update.return_value = mock_update_response

        result, deploy_target = runner.create_model_entity(config)

        model_entity_runner_mocks.sdk.models.adapters.create.assert_called_once()
        model_entity_runner_mocks.sdk.models.adapters.update.assert_called_once()
        update_kwargs = model_entity_runner_mocks.sdk.models.adapters.update.call_args[1]
        assert update_kwargs["adapter"] == "existing-adapter"
        assert update_kwargs["model_name"] == "llama-base"
        assert update_kwargs["workspace"] == "default"
        assert update_kwargs["fileset"] == "custom-ws/new-fileset"
        assert update_kwargs["description"] == "Retrained adapter"
        assert update_kwargs["enabled"] is True

        assert result == mock_update_response.model_dump.return_value
        assert deploy_target == mock_base_response

    def test_create_adapter_conflict_update_failure_raises(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test that adapter update failure after conflict raises ModelEntityCreationError."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="failing-adapter",
            workspace="default",
            fileset=FileSetRef(workspace="ws", name="files"),
            model_entity="default/llama-base",
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=16, rank=8),
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_base = MagicMock()
        mock_base.name = "llama-base"
        mock_base.workspace = "default"
        model_entity_runner_mocks.sdk.models.retrieve.return_value = mock_base

        model_entity_runner_mocks.sdk.models.adapters.create.side_effect = ConflictError(
            message="Adapter already exists",
            response=MagicMock(status_code=409),
            body=None,
        )
        model_entity_runner_mocks.sdk.models.adapters.update.side_effect = RuntimeError("Update failed")

        with pytest.raises(ModelEntityCreationError, match="already exists but update failed"):
            runner.create_model_entity(config)

    def test_lora_adapter_always_created_with_enabled_true(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Adapters are always created with enabled=True regardless of deployment_config."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="custom-ws", name="model-artifacts"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=16, rank=32),
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_base_response = MagicMock()
        mock_base_response.name = "llama-base"
        mock_base_response.workspace = "default"
        model_entity_runner_mocks.sdk.models.retrieve.return_value = mock_base_response

        mock_adapter_response = MagicMock()
        mock_adapter_response.model_dump.return_value = {"name": "lora-model"}
        model_entity_runner_mocks.sdk.models.adapters.create.return_value = mock_adapter_response

        runner.create_model_entity(config)

        call_kwargs = model_entity_runner_mocks.sdk.models.adapters.create.call_args[1]
        assert call_kwargs["enabled"] is True

    def test_lora_adapter_enabled_true_even_without_deployment_config(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """Adapters are enabled=True even when deployment_config is None."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-no-deploy",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config=None,
        )

        mock_fileset = MagicMock()
        model_entity_runner_mocks.sdk.files.filesets.retrieve.return_value = mock_fileset

        mock_base = MagicMock()
        mock_base.name = "llama-base"
        mock_base.workspace = "default"
        model_entity_runner_mocks.sdk.models.retrieve.return_value = mock_base

        mock_adapter = MagicMock()
        mock_adapter.model_dump.return_value = {"name": "lora-no-deploy"}
        model_entity_runner_mocks.sdk.models.adapters.create.return_value = mock_adapter

        runner.create_model_entity(config)

        call_kwargs = model_entity_runner_mocks.sdk.models.adapters.create.call_args[1]
        assert call_kwargs["enabled"] is True
        model_entity_runner_mocks.sdk.inference.deployment_configs.list.assert_not_called()

    def test_launch_model_no_op_without_deployment_config(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """launch_model should not create deployments when deployment_config is None."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="no-deploy",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.assert_not_called()
        model_entity_runner_mocks.sdk.inference.deployments.create.assert_not_called()

    def test_launch_model_inline_skips_when_ready_deployment_exists(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """Inline params: returns early when a READY LoRA deployment already exists."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-exists",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config=DeploymentParameters(lora_enabled=True),
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        mock_config = MagicMock()
        mock_config.name = "existing-cfg"

        mock_deployment = MagicMock()
        mock_deployment.status = "READY"

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.return_value = MagicMock(data=[mock_config])
        model_entity_runner_mocks.sdk.inference.deployments.list.return_value = MagicMock(data=[mock_deployment])

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployments.create.assert_not_called()

    def test_launch_model_inline_skips_when_pending_deployment(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Inline params: returns early when a deployment is in progress."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-pending",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config=DeploymentParameters(lora_enabled=True),
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        mock_config = MagicMock()
        mock_config.name = "existing-cfg"

        mock_deployment = MagicMock()
        mock_deployment.status = "PENDING"

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.return_value = MagicMock(data=[mock_config])
        model_entity_runner_mocks.sdk.inference.deployments.list.return_value = MagicMock(data=[mock_deployment])

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployments.create.assert_not_called()

    def test_launch_model_inline_creates_new_config(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Inline params always create a new deployment config (no implicit discovery)."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-new-cfg",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config=DeploymentParameters(lora_enabled=True, gpu=2),
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.return_value = MagicMock(data=[])
        model_entity_runner_mocks.sdk.inference.deployments.list.return_value = MagicMock(data=[])

        mock_new_config = MagicMock()
        mock_new_config.name = "sft-cfg-llama-base"
        mock_new_config.workspace = "default"
        model_entity_runner_mocks.sdk.inference.deployment_configs.create.return_value = mock_new_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "default"
        mock_deployment.name = "sft-deploy-llama-base"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.create.assert_called_once()
        create_kwargs = model_entity_runner_mocks.sdk.inference.deployment_configs.create.call_args[1]
        assert create_kwargs["executor_config"]["gpu"] == 2
        assert create_kwargs["model_spec"]["lora_enabled"] is True

        model_entity_runner_mocks.sdk.inference.deployments.create.assert_called_once()

    def test_launch_model_inline_creates_new_config_even_when_existing_config_present(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """Inline params create a new config even when a LoRA-enabled config already exists."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-no-reuse",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config=DeploymentParameters(lora_enabled=True),
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        # No active deployments, so _has_active_deployment returns False
        model_entity_runner_mocks.sdk.inference.deployment_configs.list.return_value = MagicMock(data=[])
        model_entity_runner_mocks.sdk.inference.deployments.list.return_value = MagicMock(data=[])

        mock_new_config = MagicMock()
        mock_new_config.name = "sft-cfg-llama-base"
        mock_new_config.workspace = "default"
        model_entity_runner_mocks.sdk.inference.deployment_configs.create.return_value = mock_new_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "default"
        mock_deployment.name = "sft-deploy-llama-base"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.create.assert_called_once()
        model_entity_runner_mocks.sdk.inference.deployments.create.assert_called_once()

    def test_launch_model_inline_lora_warns_when_lora_disabled(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Inline params with lora_enabled=False on a LoRA job logs warning and skips."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-disabled",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config=DeploymentParameters(lora_enabled=False),
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.create.assert_not_called()
        model_entity_runner_mocks.sdk.inference.deployments.create.assert_not_called()

    def test_launch_model_inline_sft_creates_config_and_deploys(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """Inline params with full SFT (no peft) creates config and deploys."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="sft-output",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            deployment_config=DeploymentParameters(gpu=4, lora_enabled=False),
        )

        mock_me = MagicMock()
        mock_me.name = "sft-output"
        mock_me.workspace = "default"

        mock_new_config = MagicMock()
        mock_new_config.name = "sft-cfg-sft-output"
        mock_new_config.workspace = "default"
        model_entity_runner_mocks.sdk.inference.deployment_configs.create.return_value = mock_new_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "default"
        mock_deployment.name = "sft-deploy-sft-output"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.create.assert_called_once()
        create_kwargs = model_entity_runner_mocks.sdk.inference.deployment_configs.create.call_args[1]
        assert create_kwargs["executor_config"]["gpu"] == 4
        assert create_kwargs["model_spec"]["lora_enabled"] is False

        model_entity_runner_mocks.sdk.inference.deployments.create.assert_called_once()
        model_entity_runner_mocks.sdk.inference.deployment_configs.list.assert_not_called()

    def test_launch_model_config_ref_rejects_invalid_format(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """String config ref with too many slashes raises ModelEntityCreationError."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="bad-ref",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            deployment_config="a/b/c",
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        with pytest.raises(ModelEntityCreationError, match="Invalid deployment config reference"):
            runner.launch_model(config, mock_me)

    def test_launch_model_config_ref_creates_deployment(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """String config ref resolves to existing config and creates deployment."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="sft-with-ref",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            deployment_config="user-created-cfg",
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        mock_existing_config = MagicMock()
        mock_existing_config.name = "user-created-cfg"
        mock_existing_config.workspace = "default"
        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.return_value = mock_existing_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "default"
        mock_deployment.name = "sft-deploy-llama-base"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.assert_called_once_with(
            workspace="default", name="user-created-cfg"
        )
        model_entity_runner_mocks.sdk.inference.deployment_configs.create.assert_not_called()
        model_entity_runner_mocks.sdk.inference.deployments.create.assert_called_once()
        create_kwargs = model_entity_runner_mocks.sdk.inference.deployments.create.call_args[1]
        assert create_kwargs["config"] == "user-created-cfg"

    def test_launch_model_config_ref_workspace_name_format(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """String config ref with workspace/name format resolves correctly."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="sft-cross-ws",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            deployment_config="team-ws/shared-config",
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        mock_existing_config = MagicMock()
        mock_existing_config.name = "shared-config"
        mock_existing_config.workspace = "team-ws"
        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.return_value = mock_existing_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "team-ws"
        mock_deployment.name = "sft-deploy-llama-base"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.assert_called_once_with(
            workspace="team-ws", name="shared-config"
        )

    def test_launch_model_config_ref_lora_skips_when_active_deployment(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """String config ref + LoRA skips when active deployment exists."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-ref-skip",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config="existing-cfg",
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        mock_config = MagicMock()
        mock_config.name = "existing-cfg"

        mock_deployment = MagicMock()
        mock_deployment.status = "READY"

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.return_value = MagicMock(data=[mock_config])
        model_entity_runner_mocks.sdk.inference.deployments.list.return_value = MagicMock(data=[mock_deployment])

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.assert_not_called()
        model_entity_runner_mocks.sdk.inference.deployments.create.assert_not_called()

    def test_launch_model_config_ref_lora_deploys_when_no_active_deployment(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """String config ref + LoRA creates deployment when no active deployment exists."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-ref-deploy",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config="my-lora-cfg",
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.return_value = MagicMock(data=[])

        mock_existing_config = MagicMock()
        mock_existing_config.name = "my-lora-cfg"
        mock_existing_config.workspace = "default"
        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.return_value = mock_existing_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "default"
        mock_deployment.name = "sft-deploy-llama-base"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.assert_called_once()
        model_entity_runner_mocks.sdk.inference.deployments.create.assert_called_once()
        create_kwargs = model_entity_runner_mocks.sdk.inference.deployments.create.call_args[1]
        assert create_kwargs["config"] == "my-lora-cfg"

    def test_launch_model_inline_deployment_list_scoped_by_workspace(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """Deployment listing uses workspace filter to avoid cross-workspace matches."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-ws-check",
            workspace="default",
            model_entity="team-ws/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA, alpha=32, rank=8),
            deployment_config=DeploymentParameters(lora_enabled=True),
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "team-ws"

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.return_value = MagicMock(data=[])

        mock_new_config = MagicMock()
        mock_new_config.name = "sft-cfg-llama-base"
        mock_new_config.workspace = "team-ws"
        model_entity_runner_mocks.sdk.inference.deployment_configs.create.return_value = mock_new_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "team-ws"
        mock_deployment.name = "sft-deploy-llama-base"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        config_list_kwargs = model_entity_runner_mocks.sdk.inference.deployment_configs.list.call_args[1]
        assert config_list_kwargs["workspace"] == "team-ws"

    def test_launch_model_lora_merged_deploys_like_sft(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """LORA_MERGED skips _has_active_deployment and creates a fresh deployment like SFT."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="lora-merged-output",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            peft=PEFTConfig(type=FinetuningType.LORA_MERGED, alpha=32, rank=8),
            deployment_config=DeploymentParameters(gpu=2),
        )

        mock_me = MagicMock()
        mock_me.name = "lora-merged-output"
        mock_me.workspace = "default"

        mock_new_config = MagicMock()
        mock_new_config.name = "sft-cfg-lora-merged-output"
        mock_new_config.workspace = "default"
        model_entity_runner_mocks.sdk.inference.deployment_configs.create.return_value = mock_new_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "default"
        mock_deployment.name = "sft-deploy-lora-merged-output"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.list.assert_not_called()
        model_entity_runner_mocks.sdk.inference.deployment_configs.create.assert_called_once()
        model_entity_runner_mocks.sdk.inference.deployments.create.assert_called_once()

    def test_launch_model_inline_config_conflict_falls_back_to_update(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """_create_deployment_config falls back to update when config already exists."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="sft-conflict",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            deployment_config=DeploymentParameters(gpu=2),
        )

        mock_me = MagicMock()
        mock_me.name = "sft-conflict"
        mock_me.workspace = "default"

        model_entity_runner_mocks.sdk.inference.deployment_configs.create.side_effect = ConflictError(
            message="Config already exists",
            response=MagicMock(status_code=409),
            body=None,
        )

        mock_updated_config = MagicMock()
        mock_updated_config.name = "sft-cfg-sft-conflict"
        mock_updated_config.workspace = "default"
        model_entity_runner_mocks.sdk.inference.deployment_configs.update.return_value = mock_updated_config

        mock_deployment = MagicMock()
        mock_deployment.workspace = "default"
        mock_deployment.name = "sft-deploy-sft-conflict"
        model_entity_runner_mocks.sdk.inference.deployments.create.return_value = mock_deployment
        model_entity_runner_mocks.sdk.inference.deployments.retrieve.return_value = mock_deployment

        runner.launch_model(config, mock_me)

        model_entity_runner_mocks.sdk.inference.deployment_configs.create.assert_called_once()
        model_entity_runner_mocks.sdk.inference.deployment_configs.update.assert_called_once()
        update_kwargs = model_entity_runner_mocks.sdk.inference.deployment_configs.update.call_args[1]
        assert update_kwargs["executor_config"]["gpu"] == 2

        model_entity_runner_mocks.sdk.inference.deployments.create.assert_called_once()
        deploy_kwargs = model_entity_runner_mocks.sdk.inference.deployments.create.call_args[1]
        assert deploy_kwargs["config"] == "sft-cfg-sft-conflict"

    def test_launch_model_config_ref_not_found_raises_creation_error(
        self, model_entity_runner_mocks: ModelEntityRunnerMocks
    ):
        """String config ref that doesn't exist raises ModelEntityCreationError."""
        runner = ModelEntityRunner(
            sdk=model_entity_runner_mocks.sdk,
            job_ctx=model_entity_runner_mocks.job_ctx,
        )

        config = ModelEntityTaskConfig(
            name="bad-ref",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace="ws", name="files"),
            deployment_config="nonexistent-cfg",
        )

        mock_me = MagicMock()
        mock_me.name = "llama-base"
        mock_me.workspace = "default"

        model_entity_runner_mocks.sdk.inference.deployment_configs.retrieve.side_effect = NotFoundError(
            message="Config not found",
            response=MagicMock(status_code=404),
            body=None,
        )

        with pytest.raises(ModelEntityCreationError, match="Failed to resolve deployment config"):
            runner.launch_model(config, mock_me)

    def test_run_function_loads_config_and_executes(self, model_entity_runner_mocks: ModelEntityRunnerMocks):
        """Test that the run function loads config from file and executes runner."""
        config = ModelEntityTaskConfig(
            name="run-test-model",
            workspace="default",
            model_entity="default/llama-base",
            fileset=FileSetRef(workspace=None, name="test-files"),
        )

        config_path = model_entity_runner_mocks.job_ctx.config_path
        config_path.write_text(config.model_dump_json())

        mock_sdk = model_entity_runner_mocks.sdk
        mock_response = MagicMock()
        mock_response.id = "model-run"
        mock_response.name = "run-test-model"
        mock_response.workspace = "test-workspace"
        mock_response.model_dump.return_value = {
            "id": "model-run",
            "name": "run-test-model",
            "workspace": "test-workspace",
        }
        mock_sdk.models.create.return_value = mock_response

        exit_code = run(sdk=mock_sdk, job_ctx=model_entity_runner_mocks.job_ctx)

        mock_sdk.models.create.assert_called_once()
        assert exit_code == 0


class TestModelEntityCreationError:
    """Tests for ModelEntityCreationError exception."""

    def test_can_raise_and_catch_error(self):
        """Test that ModelEntityCreationError can be raised and caught."""
        with pytest.raises(ModelEntityCreationError) as exc_info:
            raise ModelEntityCreationError("Test error message")

        assert str(exc_info.value) == "Test error message"

    def test_error_is_exception_subclass(self):
        """Test that ModelEntityCreationError is an Exception subclass."""
        error = ModelEntityCreationError("test")
        assert isinstance(error, Exception)
