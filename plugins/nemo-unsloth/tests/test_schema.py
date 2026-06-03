# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Schema validation tests for UnslothJobInput / UnslothJobOutput."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_unsloth_plugin.schema import (
    DatasetSpec,
    LoRAParams,
    ModelLoadSpec,
    OutputRequest,
    ScheduleSpec,
    TrainingSpec,
    UnslothJobInput,
    UnslothJobOutput,
)
from nemo_unsloth_plugin.transform import transform_input_to_output
from pydantic import ValidationError


def _stub_sdk(*, is_embedding: bool = False) -> SimpleNamespace:
    """Build a minimal async SDK that resolves model + dataset refs."""
    spec = SimpleNamespace(is_embedding_model=is_embedding) if is_embedding else None
    model_entity = SimpleNamespace(
        name="m",
        workspace="default",
        spec=spec,
        fileset="m",
        trust_remote_code=False,
    )
    return SimpleNamespace(
        models=SimpleNamespace(retrieve=AsyncMock(return_value=model_entity)),
        files=SimpleNamespace(
            filesets=SimpleNamespace(retrieve=AsyncMock(return_value=SimpleNamespace())),
        ),
    )


def _run_transform(spec: UnslothJobInput) -> UnslothJobOutput:
    return asyncio.run(transform_input_to_output(spec, "default", _stub_sdk()))


class TestCanonicalReexport:
    """Pin that the canonical types come from the service package."""

    def test_unsloth_job_output_lives_in_service(self) -> None:
        # Re-exported from the plugin for caller convenience, but the
        # source of truth is the service. Keeps the dependency direction
        # plugin → service.
        assert UnslothJobOutput.__module__ == "nmp.unsloth.schemas"


def _minimal_payload() -> dict[str, object]:
    return {
        "model": {"name": "unsloth/Qwen2.5-0.5B-Instruct", "max_seq_length": 2048},
        "dataset": {"path": "/data/sample.jsonl"},
        "schedule": {"max_steps": 60},
    }


class TestMinimalShape:
    def test_minimal_payload_validates(self) -> None:
        spec = UnslothJobInput.model_validate(_minimal_payload())
        # Defaults applied
        assert spec.training.finetuning_type == "lora"
        assert spec.training.lora is not None
        assert spec.training.lora.rank == 16
        # Unsloth's recommended 7-module set
        assert spec.training.lora.target_modules == [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]
        assert spec.optimizer.optim == "adamw_8bit"
        assert spec.hardware.precision == "bf16"

    def test_fixture_minimal_unsloth_sft_loads(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "minimal_unsloth_sft.json"
        UnslothJobInput.model_validate(json.loads(fixture.read_text()))


class TestRequiredFields:
    def test_dataset_path_required(self) -> None:
        payload = _minimal_payload()
        del payload["dataset"]
        with pytest.raises(ValidationError):
            UnslothJobInput.model_validate(payload)

    def test_model_required(self) -> None:
        payload = _minimal_payload()
        del payload["model"]
        with pytest.raises(ValidationError):
            UnslothJobInput.model_validate(payload)


class TestScheduleMutex:
    def test_neither_epochs_nor_max_steps_rejected(self) -> None:
        payload = _minimal_payload()
        payload["schedule"] = {}
        with pytest.raises(ValidationError, match="schedule.epochs or schedule.max_steps"):
            UnslothJobInput.model_validate(payload)

    def test_both_epochs_and_max_steps_rejected(self) -> None:
        payload = _minimal_payload()
        payload["schedule"] = {"epochs": 1, "max_steps": 60}
        with pytest.raises(ValidationError, match="mutually exclusive"):
            UnslothJobInput.model_validate(payload)

    def test_either_one_is_fine(self) -> None:
        for sched in ({"epochs": 3}, {"max_steps": 60}):
            payload = _minimal_payload()
            payload["schedule"] = sched
            UnslothJobInput.model_validate(payload)


class TestQuantizationMutex:
    def test_4bit_and_8bit_rejected(self) -> None:
        payload = _minimal_payload()
        payload["model"] = {
            "name": "x",
            "max_seq_length": 1024,
            "load_in_4bit": True,
            "load_in_8bit": True,
        }
        with pytest.raises(ValidationError, match="load_in_4bit and model.load_in_8bit"):
            UnslothJobInput.model_validate(payload)


class TestFullFinetuneRules:
    def test_full_ft_rejects_4bit(self) -> None:
        payload = _minimal_payload()
        payload["training"] = {"finetuning_type": "full"}
        # default load_in_4bit=True
        with pytest.raises(ValidationError, match="incompatible with 4-bit/8-bit"):
            UnslothJobInput.model_validate(payload)

    def test_full_ft_rejects_lora_block(self) -> None:
        payload = _minimal_payload()
        payload["model"]["load_in_4bit"] = False
        payload["training"] = {"finetuning_type": "full", "lora": {"rank": 8}}
        with pytest.raises(ValidationError, match="training.lora must be unset"):
            UnslothJobInput.model_validate(payload)

    def test_full_ft_clean(self) -> None:
        payload = _minimal_payload()
        payload["model"]["load_in_4bit"] = False
        payload["training"] = {"finetuning_type": "full"}
        spec = UnslothJobInput.model_validate(payload)
        assert spec.training.lora is None


class TestWarmupMutex:
    def test_warmup_steps_and_ratio_rejected(self) -> None:
        payload = _minimal_payload()
        payload["schedule"] = {"max_steps": 60, "warmup_steps": 10, "warmup_ratio": 0.1}
        with pytest.raises(ValidationError, match="warmup_steps and schedule.warmup_ratio"):
            UnslothJobInput.model_validate(payload)


class TestSaveMethodCompatibility:
    def test_merged_save_with_lora_ok(self) -> None:
        payload = _minimal_payload()
        payload["output"] = {"save_method": "merged_16bit"}
        UnslothJobInput.model_validate(payload)

    def test_merged_save_with_full_rejected(self) -> None:
        payload = _minimal_payload()
        payload["model"]["load_in_4bit"] = False
        payload["training"] = {"finetuning_type": "full"}
        payload["output"] = {"save_method": "merged_16bit"}
        with pytest.raises(ValidationError, match="only valid for training.finetuning_type='lora'"):
            UnslothJobInput.model_validate(payload)


class TestExtraForbidden:
    def test_unknown_top_level_rejected(self) -> None:
        payload = _minimal_payload()
        payload["mystery_field"] = "boom"
        with pytest.raises(ValidationError):
            UnslothJobInput.model_validate(payload)


class TestTransformOutput:
    def test_auto_name_when_output_omitted(self) -> None:
        spec = UnslothJobInput.model_validate(_minimal_payload())
        out = _run_transform(spec)
        # Auto-name draws from the model basename + dataset basename.
        # "Qwen2.5-0.5B-Instruct" → "Qwen2-5-0-5B-Instruct" (dots → hyphens).
        assert out.output.name.startswith("Qwen2-5-0-5B-Instruct-sample-")
        assert out.output.type == "adapter"
        assert out.output.save_method == "lora"
        # Fileset defaults to the entity name (mirrors automodel).
        assert out.output.fileset == out.output.name

    def test_explicit_name_preserved(self) -> None:
        payload = _minimal_payload()
        payload["output"] = {"name": "my-run", "save_method": "lora"}
        out = _run_transform(UnslothJobInput.model_validate(payload))
        assert out.output.name == "my-run"
        assert out.output.fileset == "my-run"

    def test_merged_inferred_as_model_type(self) -> None:
        payload = _minimal_payload()
        payload["output"] = {"save_method": "merged_4bit"}
        out = _run_transform(UnslothJobInput.model_validate(payload))
        assert out.output.type == "model"
        assert out.output.save_method == "merged_4bit"

    def test_embedding_model_rejected(self) -> None:
        sdk = _stub_sdk(is_embedding=True)
        spec = UnslothJobInput.model_validate(_minimal_payload())
        with pytest.raises(ValueError, match="Embedding-model SFT"):
            asyncio.run(transform_input_to_output(spec, "default", sdk))


class TestSubSpecExtras:
    def test_dataset_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DatasetSpec.model_validate({"path": "/x", "junk": 1})

    def test_lora_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoRAParams.model_validate({"rank": 8, "junk": 1})

    def test_model_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelLoadSpec.model_validate({"name": "x", "junk": 1})

    def test_schedule_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ScheduleSpec.model_validate({"max_steps": 1, "junk": 1})

    def test_training_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TrainingSpec.model_validate({"junk": 1})

    def test_output_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OutputRequest.model_validate({"junk": 1})
