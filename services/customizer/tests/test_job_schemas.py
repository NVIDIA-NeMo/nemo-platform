# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for CustomizationJobInput schema.

Tests the output field behavior:
- Auto-generation when not provided
- User-provided values are preserved
- Stability across serialization roundtrip (storage and retrieval)
"""

import asyncio
import re
from datetime import datetime

import pytest
from nemo_platform_plugin.jobs.api_factory import handle_job_spec_mismatch
from nmp.common.entities.utils import get_random_id
from nmp.core.models.schemas import FinetuningType, ModelEntity
from nmp.customizer.api.v2.jobs.schemas import (
    CustomizationJobInput,
    CustomizationJobOutput,
    DeploymentParams,
)
from nmp.customizer.api.v2.jobs.schemas import (
    ValidationError as JobValidationError,
)
from nmp.customizer.utils import _generate_random_id, get_entity_name, transform_input_to_output
from pydantic import ValidationError

AUTO_MODEL_ID_PATTERN = r"^test-target-my-dataset-[a-f0-9]{12}$"
CUSTOM_MODEL_FILESET_PATTERN = r"^my-custom-model-[a-f0-9]{12}$"


def make_valid_job_input_dict() -> dict:
    """Create a valid CustomizationJobInput as a dictionary."""
    return {
        "model": "default/test-target",
        "training": {
            "type": "sft",
            "peft": {"type": "lora"},
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 0.0001,
        },
        "dataset": "fileset://default/my-dataset",
    }


def _transform_input(
    job_input: CustomizationJobInput, mocker, *, is_embedding_model: bool = False
) -> CustomizationJobOutput:
    mock_entity = mocker.Mock()
    mock_entity.spec = mocker.Mock(is_embedding_model=is_embedding_model) if is_embedding_model else None
    mocker.patch(
        "nmp.customizer.utils.fetch_model_entity",
        new_callable=mocker.AsyncMock,
        return_value=mock_entity,
    )
    mocker.patch(
        "nmp.customizer.utils.check_dataset_access",
        new_callable=mocker.AsyncMock,
    )
    return asyncio.run(
        transform_input_to_output(
            job_input,
            "default",
            mocker.Mock(),
            None,
            mocker.AsyncMock(),
        )
    )


class TestOutputFields:
    """Tests for output field behavior."""

    def test_auto_generated_when_not_provided(self, mocker):
        """Test that output is auto-generated when not provided."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)

        assert job_output.output is not None
        assert re.match(AUTO_MODEL_ID_PATTERN, job_output.output.name)
        assert job_output.output.fileset == job_output.output.name

    @pytest.mark.parametrize(
        ("model", "dataset", "expected_prefix"),
        [
            ("default/test-target", "fileset://default/my-dataset", "test-target-my-dataset"),
            ("workspace-a/target-from-ref", "fileset://workspace-b/train-set", "target-from-ref-train-set"),
            ("target-name-only", "fileset://default/my-dataset", "target-name-only-my-dataset"),
        ],
        ids=["target_object", "target_workspace_name", "target_name_only"],
    )
    def test_auto_generated_uses_target_and_dataset_names(
        self,
        mocker,
        model: str,
        dataset: str,
        expected_prefix: str,
    ):
        """Test output name prefix extraction from target and dataset refs."""
        data = make_valid_job_input_dict()
        data["model"] = model
        data["dataset"] = dataset
        job_input = CustomizationJobInput.model_validate(data)

        job_output = _transform_input(job_input, mocker)

        assert job_output.output is not None
        assert re.match(rf"^{expected_prefix}-[a-f0-9]{{12}}$", job_output.output.name)
        assert job_output.output.fileset == job_output.output.name

    def test_unique_ids_per_instance(self, mocker):
        """Test that each job input gets unique auto-generated IDs."""
        data = make_valid_job_input_dict()
        job_input_1 = CustomizationJobInput.model_validate(data)
        job_input_2 = CustomizationJobInput.model_validate(data)
        output_1 = _transform_input(job_input_1, mocker)
        output_2 = _transform_input(job_input_2, mocker)

        assert output_1.output.name == output_1.output.fileset
        assert output_2.output.name == output_2.output.fileset
        assert output_1.output.name != output_2.output.name
        assert output_1.output.fileset != output_2.output.fileset

    def test_user_provided_values_preserved(self, mocker):
        """Test that user-provided output name is preserved."""
        data = make_valid_job_input_dict()
        data["output"] = {"name": "my-custom-model"}
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)

        assert job_output.output.name == "my-custom-model"
        assert re.match(CUSTOM_MODEL_FILESET_PATTERN, job_output.output.fileset)

    def test_user_output_with_auto_fileset(self, mocker):
        """Test that user-provided output name works with auto-generated fileset."""
        data = make_valid_job_input_dict()
        data["output"] = {"name": "my-custom-model"}
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)

        assert job_output.output.name == "my-custom-model"
        assert re.match(CUSTOM_MODEL_FILESET_PATTERN, job_output.output.fileset)

    def test_included_in_exclude_unset_serialization(self, mocker):
        """Test that auto-generated fields are included with exclude_unset=True."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)
        serialized = job_output.model_dump(exclude_unset=True)

        assert "output" in serialized
        assert "fileset" in serialized["output"]

    def test_stable_across_storage_roundtrip(self, mocker):
        """Test that fields are stable across serialize -> store -> deserialize cycle."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        original = _transform_input(job_input, mocker)
        stored = original.model_dump(exclude_unset=True)

        retrieved_1 = handle_job_spec_mismatch(CustomizationJobOutput, stored)
        retrieved_2 = handle_job_spec_mismatch(CustomizationJobOutput, stored)

        assert retrieved_1.output.fileset == original.output.fileset
        assert retrieved_1.output.name == original.output.name
        assert retrieved_2.output.fileset == original.output.fileset
        assert retrieved_2.output.name == original.output.name

    def test_legacy_output_model_rejected_on_input(self):
        """Legacy output_model field should be rejected with a clear error message."""
        data = make_valid_job_input_dict()
        data["output_model"] = "my-model"
        with pytest.raises(ValidationError, match="output_model was removed.*Use spec.output"):
            CustomizationJobInput.model_validate(data)

    def test_lora_infers_adapter_type(self, mocker):
        """Unmerged LoRA should infer output.type=adapter for non-embedding models."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)
        assert job_output.output.type == "adapter"

    def test_lora_merge_infers_model_type(self, mocker):
        """LoRA with merge=True should infer output.type=model."""
        data = make_valid_job_input_dict()
        data["training"]["peft"] = {"type": "lora", "merge": True}
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)
        assert job_output.output.type == "model"

    def test_embedding_model_always_infers_model_type(self, mocker):
        """Embedding models should always produce type=model, even with LoRA."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker, is_embedding_model=True)
        assert job_output.output.type == "model"


class TestGetEntityName:
    """Tests for get_entity_name helper."""

    @pytest.mark.parametrize(
        ("entity", "expected"),
        [
            (
                ModelEntity(
                    id=get_random_id("model"),
                    workspace="default",
                    name="target-from-object",
                    fileset="default/base-model",
                    finetuning_type=FinetuningType.LORA,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                ),
                "target-from-object",
            ),
            ("workspace-a/target-from-ref", "target-from-ref"),
            ("target-name-only", "target-name-only"),
            ("default/some-target", "some-target"),
        ],
        ids=["customization_target", "workspace_name_ref", "name_only", "urn_format"],
    )
    def test_extracts_entity_name(self, entity: str | ModelEntity, expected: str):
        """Should normalize target object or ref string to entity name."""
        assert get_entity_name(entity) == expected


class TestGenerateRandomId:
    """Tests for _generate_random_id helper."""

    def test_valid_prefix_generates_id(self):
        """Test that a valid prefix generates an ID in the expected format."""
        result = _generate_random_id("my-prefix")
        assert re.match(r"^my-prefix-[a-f0-9]{12}$", result)

    def test_trailing_hyphens_stripped(self):
        """Test that trailing hyphens are stripped from the prefix."""
        result = _generate_random_id("my-prefix---")
        assert re.match(r"^my-prefix-[a-f0-9]{12}$", result)

    @pytest.mark.parametrize(
        "invalid_prefix",
        [
            "",
            "-",
            "---",
            "--------------------",
        ],
        ids=["empty", "single_hyphen", "multiple_hyphens", "many_hyphens"],
    )
    def test_empty_prefix_raises_error(self, invalid_prefix: str):
        """Test that empty prefix (after stripping) raises an actionable ValueError."""
        with pytest.raises(ValueError, match=r"Cannot generate ID.*contains no valid characters"):
            _generate_random_id(invalid_prefix)


class TestEntityNameValidation:
    """Tests for entity name validation on CustomizationJobInput."""

    @pytest.mark.parametrize(
        "output",
        [
            "my-model",
            "model-v1",
            "ab",
            "a1",
            "a",
            "My-Model",
            "123-model",
            "model.v1",
            "model_v1",
            "model--name",
        ],
        ids=[
            "hyphenated",
            "with-version",
            "two-chars",
            "alphanumeric",
            "single-char",
            "uppercase",
            "starts-with-digit",
            "with-dot",
            "with-underscore",
            "consecutive-hyphens",
        ],
    )
    def test_valid_output_accepted(self, output: str):
        """Valid output names should pass schema validation."""
        data = make_valid_job_input_dict()
        data["output"] = {"name": output}
        job_input = CustomizationJobInput.model_validate(data)
        assert job_input.output is not None
        assert job_input.output.name == output

    @pytest.mark.parametrize(
        "output",
        [
            "-",
            "---",
            "--------------------",
        ],
        ids=["single-hyphen", "multiple-hyphens", "many-hyphens"],
    )
    def test_all_hyphen_output_rejected_at_transform(self, mocker, output: str):
        """All-hyphen output passes regex but fails ID generation with clear error."""
        data = make_valid_job_input_dict()
        data["output"] = {"name": output}
        job_input = CustomizationJobInput.model_validate(data)
        assert job_input.output is not None
        assert job_input.output.name == output

        with pytest.raises(ValueError, match=r"Cannot generate ID.*contains no valid characters"):
            _transform_input(job_input, mocker)

    def test_none_output_accepted(self):
        """None output (auto-generate) should pass validation."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        assert job_input.output is None

    @pytest.mark.parametrize(
        "output",
        [
            "",
            "model name",
            "model@v1",
            "model+v1",
            "invalid*chars",
            "path/to/model",
        ],
        ids=["empty", "contains-space", "contains-at", "contains-plus", "contains-star", "contains-slash"],
    )
    def test_invalid_output_rejected(self, output: str):
        """Invalid output names should be rejected by pattern validation."""
        data = make_valid_job_input_dict()
        data["output"] = {"name": output}
        with pytest.raises(ValidationError, match="String should match pattern"):
            CustomizationJobInput.model_validate(data)

    @pytest.mark.parametrize(
        "output_name",
        [
            "My-Model",
            "model.v1",
            "model_v1",
            "123-model",
        ],
        ids=["uppercase", "with-dot", "with-underscore", "starts-with-digit"],
    )
    def test_valid_output_name_on_output_schema(self, mocker, output_name: str):
        """Valid output names should pass CustomizationJobOutput validation."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)
        stored = job_output.model_dump()
        stored["output"]["name"] = output_name
        result = CustomizationJobOutput.model_validate(stored)
        assert result.output.name == output_name

    @pytest.mark.parametrize(
        "fileset",
        [
            "my-fileset",
            "Fileset.v1",
            "fileset_name",
            "123-fileset",
        ],
        ids=["hyphenated", "uppercase-with-dot", "with-underscore", "starts-with-digit"],
    )
    def test_valid_output_fileset_accepted(self, mocker, fileset: str):
        """Valid fileset names should pass CustomizationJobOutput validation."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)
        stored = job_output.model_dump()
        stored["output"]["fileset"] = fileset
        result = CustomizationJobOutput.model_validate(stored)
        assert result.output.fileset == fileset

    @pytest.mark.parametrize(
        "fileset",
        [
            "",
            "invalid *chars",
            "fileset@name",
            "fileset+name",
            "invalid*chars",
            "path/to/fileset",
        ],
        ids=["empty", "contains-space", "contains-at", "contains-plus", "contains-star", "contains-slash"],
    )
    def test_invalid_output_fileset_rejected(self, mocker, fileset: str):
        """Invalid fileset names should be rejected by pattern validation."""
        data = make_valid_job_input_dict()
        job_input = CustomizationJobInput.model_validate(data)
        job_output = _transform_input(job_input, mocker)
        stored = job_output.model_dump()
        stored["output"]["fileset"] = fileset
        with pytest.raises(ValidationError, match="String should match pattern"):
            CustomizationJobOutput.model_validate(stored)

    @pytest.mark.parametrize(
        "model",
        [
            "default/---",
        ],
        ids=["ref-all-hyphens"],
    )
    def test_all_hyphen_target_rejected_at_transform_when_auto_generating(self, mocker, model: str):
        """All-hyphen target name passes validation but dataset name provides valid chars."""
        data = make_valid_job_input_dict()
        data["model"] = model
        job_input = CustomizationJobInput.model_validate(data)

        job_output = _transform_input(job_input, mocker)
        assert job_output.output is not None

    @pytest.mark.parametrize(
        "dataset",
        [
            "fileset://default/Upper_Name",
            "fileset://default/1-starts-with-digit",
            "fileset://default/dataset.v2",
        ],
        ids=["uppercase-underscore", "starts-with-digit", "with-dot"],
    )
    def test_valid_dataset_name_accepted(self, dataset: str):
        """Valid dataset names should pass the model validator."""
        data = make_valid_job_input_dict()
        data["dataset"] = dataset
        CustomizationJobInput.model_validate(data)

    @pytest.mark.parametrize(
        ("dataset", "invalid_name"),
        [
            ("fileset://default/bad name", "bad name"),
            ("fileset://default/bad@name", "bad@name"),
            ("fileset://default/bad+name", "bad+name"),
            ("fileset://default/bad*name", "bad*name"),
        ],
        ids=["contains-space", "contains-at", "contains-plus", "contains-star"],
    )
    def test_invalid_dataset_name_rejected(self, dataset: str, invalid_name: str):
        """Invalid dataset names should be rejected by model validator."""
        data = make_valid_job_input_dict()
        data["dataset"] = dataset
        with pytest.raises(ValidationError, match=f"Invalid dataset name: '{re.escape(invalid_name)}'"):
            CustomizationJobInput.model_validate(data)

    def test_all_hyphen_dataset_accepted_when_target_has_valid_chars(self, mocker):
        """All-hyphen dataset name passes validation; transform succeeds if target has valid chars."""
        data = make_valid_job_input_dict()
        data["dataset"] = "fileset://default/---"
        job_input = CustomizationJobInput.model_validate(data)

        job_output = _transform_input(job_input, mocker)
        assert job_output.output is not None

    def test_all_hyphen_target_and_dataset_rejected_at_transform(self, mocker):
        """All-hyphen target AND dataset fails ID generation during transform."""
        data = make_valid_job_input_dict()
        data["model"] = "default/---"
        data["dataset"] = "fileset://default/---"
        job_input = CustomizationJobInput.model_validate(data)

        with pytest.raises(ValueError, match=r"Cannot generate ID.*contains no valid characters"):
            _transform_input(job_input, mocker)


def _make_job_output(mocker, **training_overrides) -> CustomizationJobOutput:
    """Create a CustomizationJobOutput with overrides for validation testing.

    Any **kwargs are merged into the base training config.
    """
    training: dict = {
        "type": "sft",
        "peft": {"type": "lora"},
        "epochs": 1,
        "batch_size": 4,
        "learning_rate": 0.0001,
    }
    training.update(training_overrides)
    data = {
        "model": "default/test-target",
        "training": training,
        "dataset": "fileset://default/my-dataset",
    }
    job_input = CustomizationJobInput.model_validate(data)
    return _transform_input(job_input, mocker)


class TestValidateForTrainingMoEParallelism:
    """Tests for MoE parallelism constraints in validate_for_training.

    Automodel's MoE parallelizer enforces:
    - Tensor parallelism not supported for MoE models (tp must be 1 when ep > 1)
    See: nemo_automodel/components/moe/parallelizer.py
    """

    def test_ep_gt1_with_tp_gt1_multi_gpu_rejected(self, mocker):
        """EP > 1 with TP > 1 on multi-GPU must be rejected."""
        job_output = _make_job_output(
            mocker,
            batch_size=8,
            parallelism={"num_gpus_per_node": 8, "expert_parallel_size": 4, "tensor_parallel_size": 2},
        )
        with pytest.raises(JobValidationError, match="Tensor parallelism.*not supported for MoE"):
            job_output.validate_for_training()

    def test_ep_gt1_with_tp_eq1_accepted(self, mocker):
        """EP > 1 with TP == 1 should pass validation."""
        job_output = _make_job_output(
            mocker,
            batch_size=8,
            parallelism={"num_gpus_per_node": 8, "expert_parallel_size": 8, "tensor_parallel_size": 1},
        )
        job_output.validate_for_training()  # Should not raise

    def test_distillation_accepted(self):
        """Distillation training with valid fields should be accepted."""
        data = make_valid_job_input_dict()
        data["training"] = {
            "type": "distillation",
            "teacher_model": "meta/llama-3.1-70b-instruct",
            "distillation_ratio": 0.7,
        }
        job = CustomizationJobInput.model_validate(data)
        assert job.training.type == "distillation"
        assert job.training.teacher_model == "meta/llama-3.1-70b-instruct"
        assert job.training.distillation_ratio == 0.7
        assert job.training.distillation_temperature == 1.0
        assert job.training.teacher_precision == "bf16"

    def test_ep_eq1_with_tp_gt1_accepted(self, mocker):
        """EP == 1 (not MoE) with TP > 1 is fine for dense models."""
        job_output = _make_job_output(
            mocker,
            batch_size=8,
            parallelism={"num_gpus_per_node": 8, "expert_parallel_size": 1, "tensor_parallel_size": 2},
        )
        job_output.validate_for_training()  # Should not raise

    def test_ep_none_with_tp_gt1_accepted(self, mocker):
        """EP not set with TP > 1 is fine for dense models."""
        job_output = _make_job_output(
            mocker,
            batch_size=8,
            parallelism={"num_gpus_per_node": 8, "tensor_parallel_size": 2},
        )
        job_output.validate_for_training()  # Should not raise

    def test_ep_gt1_dp_cp_not_divisible_rejected(self, mocker):
        """EP > 1 where (DP * CP) is not divisible by EP must be rejected."""
        job_output = _make_job_output(
            mocker,
            batch_size=8,
            parallelism={"num_gpus_per_node": 8, "expert_parallel_size": 3, "tensor_parallel_size": 1},
        )
        with pytest.raises(JobValidationError, match="must be divisible by expert_parallel_size"):
            job_output.validate_for_training()

    def test_invalid_training_type_rejected(self):
        """Unknown training type should be rejected."""
        data = make_valid_job_input_dict()
        data["training"] = {"type": "invalid_type"}
        with pytest.raises(ValidationError):
            CustomizationJobInput.model_validate(data)

    def test_dpo_rejects_peft(self):
        """DPO training should reject PEFT configuration (not yet supported)."""
        data = make_valid_job_input_dict()
        data["training"] = {"type": "dpo", "peft": {"type": "lora"}}
        with pytest.raises(ValidationError, match="not yet supported with DPO"):
            CustomizationJobInput.model_validate(data)

    def test_dpo_without_peft_accepted(self):
        """DPO training without PEFT should be accepted."""
        data = make_valid_job_input_dict()
        data["training"] = {"type": "dpo"}
        job = CustomizationJobInput.model_validate(data)
        assert job.training.type == "dpo"
        assert job.training.peft is None

    def test_distillation_with_peft_lora_accepted(self):
        """Distillation + LoRA should be accepted."""
        data = make_valid_job_input_dict()
        data["training"] = {
            "type": "distillation",
            "teacher_model": "meta/llama-3.1-70b-instruct",
            "peft": {"type": "lora", "rank": 16},
        }
        job = CustomizationJobInput.model_validate(data)
        assert job.training.type == "distillation"
        assert job.training.peft is not None
        assert job.training.peft.rank == 16

    def test_distillation_requires_teacher_model(self):
        """Distillation training without teacher_model should be rejected."""
        data = make_valid_job_input_dict()
        data["training"] = {
            "type": "distillation",
        }
        with pytest.raises(ValidationError, match="teacher_model"):
            CustomizationJobInput.model_validate(data)

    def test_distillation_ratio_bounds(self):
        """Distillation ratio must be between 0.0 and 1.0."""
        data = make_valid_job_input_dict()
        data["training"] = {
            "type": "distillation",
            "teacher_model": "meta/llama-3.1-70b-instruct",
            "distillation_ratio": 1.5,
        }
        with pytest.raises(ValidationError):
            CustomizationJobInput.model_validate(data)

    def test_distillation_temperature_must_be_positive(self):
        """Distillation temperature must be > 0."""
        data = make_valid_job_input_dict()
        data["training"] = {
            "type": "distillation",
            "teacher_model": "meta/llama-3.1-70b-instruct",
            "distillation_temperature": 0.0,
        }
        with pytest.raises(ValidationError):
            CustomizationJobInput.model_validate(data)

    def test_distillation_defaults(self):
        """Distillation should use correct defaults for optional fields."""
        data = make_valid_job_input_dict()
        data["training"] = {
            "type": "distillation",
            "teacher_model": "meta/llama-3.1-70b-instruct",
        }
        job = CustomizationJobInput.model_validate(data)
        assert job.training.distillation_ratio == 0.5
        assert job.training.distillation_temperature == 1.0
        assert job.training.teacher_precision == "bf16"

    def test_lora_merge_produces_lora_merged_finetuning_type(self, mocker):
        """LoRA with merge=True should produce lora_merged finetuning type."""
        job_output = _make_job_output(mocker, peft={"type": "lora", "merge": True})
        assert job_output.training.finetuning_type.value == "lora_merged"

    def test_lora_without_merge_produces_lora_finetuning_type(self, mocker):
        """LoRA with merge=False (default) should produce lora finetuning type."""
        job_output = _make_job_output(mocker, peft={"type": "lora"})
        assert job_output.training.finetuning_type.value == "lora"

    def test_no_peft_produces_all_weights_finetuning_type(self, mocker):
        """No PEFT config should produce all_weights finetuning type."""
        job_output = _make_job_output(mocker, peft=None)
        assert job_output.training.finetuning_type.value == "all_weights"

    def test_lora_with_lora_enabled_false_rejected(self):
        """LoRA training with deployment_config.lora_enabled=False should be rejected."""
        data = make_valid_job_input_dict()
        data["deployment_config"] = {"lora_enabled": False}
        with pytest.raises(ValidationError, match="lora_enabled must be true"):
            CustomizationJobInput.model_validate(data)

    def test_lora_with_lora_enabled_true_accepted(self):
        """LoRA training with deployment_config.lora_enabled=True should be accepted."""
        data = make_valid_job_input_dict()
        data["deployment_config"] = {"lora_enabled": True}
        job = CustomizationJobInput.model_validate(data)
        assert isinstance(job.deployment_config, DeploymentParams) and job.deployment_config.lora_enabled is True

    def test_lora_merged_with_lora_enabled_false_accepted(self):
        """LoRA merged training with lora_enabled=False should be accepted (produces full-weight model)."""
        data = make_valid_job_input_dict()
        data["training"]["peft"]["merge"] = True
        data["deployment_config"] = {"lora_enabled": False}
        job = CustomizationJobInput.model_validate(data)
        assert isinstance(job.deployment_config, DeploymentParams) and job.deployment_config.lora_enabled is False

    def test_sft_with_lora_enabled_false_accepted(self):
        """Full SFT training with lora_enabled=False should be accepted."""
        data = make_valid_job_input_dict()
        data["training"]["peft"] = None
        data["deployment_config"] = {"lora_enabled": False}
        job = CustomizationJobInput.model_validate(data)
        assert isinstance(job.deployment_config, DeploymentParams) and job.deployment_config.lora_enabled is False

    def test_lora_with_string_deployment_config_accepted(self):
        """LoRA training with a string deployment_config ref is accepted at schema level."""
        data = make_valid_job_input_dict()
        data["deployment_config"] = "my-existing-config"
        job = CustomizationJobInput.model_validate(data)
        assert isinstance(job.deployment_config, str) and job.deployment_config == "my-existing-config"
