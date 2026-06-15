# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for automodel config compilation functions."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Mock nemo_automodel before importing the config module
# (nemo_automodel is only available in the training container)
sys.modules["nemo_automodel"] = MagicMock()
sys.modules["nemo_automodel._transformers"] = MagicMock()
sys.modules["nemo_automodel._transformers.registry"] = MagicMock()
sys.modules.setdefault("transformers", MagicMock())

from nmp.automodel.tasks.training.backends.config import (  # noqa: E402
    _configure_chat_dataset,
    _configure_moe_backend,
    _configure_sft_dataset,
)

CONFIG_MODULE = "nmp.automodel.tasks.training.backends.config"
AUTOCONFIG_PATCH = "transformers.AutoConfig"
MODEL_REGISTRY_PATCH = f"{CONFIG_MODULE}.ModelRegistry"


@pytest.fixture
def mock_customizer_config() -> MagicMock:
    """Create a mock TrainingStepConfig for testing."""
    config = MagicMock()
    config.model.path = "/models/test-model"
    config.model.name = "test/model"
    return config


@pytest.fixture
def temp_dataset_files(tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary dataset files for testing."""
    train_file = tmp_path / "train.jsonl"
    val_file = tmp_path / "validation.jsonl"
    train_file.write_text('{"messages": [{"role": "user", "content": "test"}]}\n')
    val_file.write_text('{"messages": [{"role": "user", "content": "test"}]}\n')
    return train_file, val_file


class TestConfigureChatDataset:
    """Tests for _configure_chat_dataset function."""

    def test_chat_dataset_includes_split_attribute(
        self,
        mock_customizer_config: MagicMock,
        temp_dataset_files: tuple[Path, Path],
        mocker,
    ) -> None:
        train_file, val_file = temp_dataset_files
        cfg: dict[str, Any] = {}

        mocker.patch(f"{CONFIG_MODULE}.resolve_chat_template", return_value="mock_template")
        mock_customizer_config.parallelism.pipeline_parallel_size = 1
        _configure_chat_dataset(cfg, mock_customizer_config, train_file, val_file, seq_length=2048)

        assert "dataset" in cfg
        assert "validation_dataset" in cfg
        assert cfg["dataset"]["split"] == "train"
        assert cfg["validation_dataset"]["split"] == "validation"

    def test_chat_dataset_includes_required_fields(
        self,
        mock_customizer_config: MagicMock,
        temp_dataset_files: tuple[Path, Path],
        mocker,
    ) -> None:
        train_file, val_file = temp_dataset_files
        cfg: dict[str, Any] = {}

        mocker.patch(f"{CONFIG_MODULE}.resolve_chat_template", return_value="mock_template")
        mock_customizer_config.parallelism.pipeline_parallel_size = 1
        _configure_chat_dataset(cfg, mock_customizer_config, train_file, val_file, seq_length=2048)

        assert cfg["dataset"]["_target_"] == "nemo_automodel.components.datasets.llm.chat_dataset.ChatDataset"
        assert cfg["dataset"]["path_or_dataset_id"] == str(train_file)
        assert cfg["dataset"]["seq_length"] == 2048
        assert cfg["dataset"]["chat_template"] == "mock_template"


class TestConfigureSftDataset:
    """Tests for _configure_sft_dataset function."""

    def test_sft_dataset_includes_split_attribute(
        self,
        temp_dataset_files: tuple[Path, Path],
        mock_customizer_config: MagicMock,
    ) -> None:
        train_file, val_file = temp_dataset_files
        cfg: dict[str, Any] = {}

        mock_customizer_config.parallelism.pipeline_parallel_size = 1
        _configure_sft_dataset(
            cfg,
            mock_customizer_config,
            train_file,
            val_file,
            question_col="prompt",
            answer_col="completion",
            seq_length=2048,
        )

        assert "dataset" in cfg
        assert "validation_dataset" in cfg
        assert cfg["dataset"]["split"] == "train"
        assert cfg["validation_dataset"]["split"] == "validation"

    def test_sft_dataset_includes_required_fields(
        self,
        temp_dataset_files: tuple[Path, Path],
        mock_customizer_config: MagicMock,
    ) -> None:
        train_file, val_file = temp_dataset_files
        cfg: dict[str, Any] = {}

        mock_customizer_config.parallelism.pipeline_parallel_size = 1
        _configure_sft_dataset(
            cfg,
            mock_customizer_config,
            train_file,
            val_file,
            question_col="prompt",
            answer_col="completion",
            seq_length=2048,
        )

        assert (
            cfg["dataset"]["_target_"]
            == "nemo_automodel.components.datasets.llm.column_mapped_text_instruction_dataset.ColumnMappedTextInstructionDataset"
        )
        assert cfg["dataset"]["path_or_dataset_id"] == str(train_file)
        assert cfg["dataset"]["seq_length"] == 2048
        assert cfg["dataset"]["column_mapping"]["question"] == "prompt"
        assert cfg["dataset"]["column_mapping"]["answer"] == "completion"
        assert cfg["dataset"]["answer_only_loss_mask"] is True
        assert cfg["dataset"]["padding"] == "do_not_pad"
        assert cfg["dataset"]["truncation"] == "longest_first"


class TestConfigureMoeBackend:
    """Tests for _configure_moe_backend function."""

    def _make_config(
        self,
        model_path: str = "/models/test-model",
        num_nodes: int = 1,
        num_gpus_per_node: int = 1,
        tensor_parallel_size: int = 1,
        expert_parallel_size: int | None = None,
    ) -> MagicMock:
        config = MagicMock()
        config.model.path = model_path
        config.parallelism.num_nodes = num_nodes
        config.parallelism.num_gpus_per_node = num_gpus_per_node
        config.parallelism.tensor_parallel_size = tensor_parallel_size
        config.parallelism.expert_parallel_size = expert_parallel_size
        return config

    def _make_hf_config(
        self,
        architectures: list[str],
        num_local_experts: int | None = None,
        num_experts: int | None = None,
    ) -> MagicMock:
        hf_config = MagicMock()
        hf_config.architectures = architectures

        original_getattr = type(hf_config).__getattr__

        def _controlled_getattr(self, name):
            if name == "num_local_experts":
                return num_local_experts
            if name == "num_experts":
                return num_experts
            return original_getattr(self, name)

        type(hf_config).__getattr__ = _controlled_getattr
        return hf_config

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_moe_model_gets_backend_and_parallelizer(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["NemotronHForCausalLM"],
            num_local_experts=8,
        )
        mock_registry.model_arch_name_to_cls = {"NemotronHForCausalLM": MagicMock()}

        cfg: dict[str, Any] = {"model": {}}
        _configure_moe_backend(cfg, self._make_config(num_gpus_per_node=8, expert_parallel_size=8))

        assert cfg["model"]["backend"] == {
            "_target_": "nemo_automodel.components.models.common.utils.BackendConfig",
            "enable_deepep": False,
        }

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_moe_multi_gpu_tp_gt1_raises(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["NemotronHForCausalLM"],
            num_local_experts=8,
        )
        mock_registry.model_arch_name_to_cls = {"NemotronHForCausalLM": MagicMock()}

        cfg: dict[str, Any] = {"model": {}}
        with pytest.raises(ValueError, match=r"Tensor parallelism.*not supported.*MoE"):
            _configure_moe_backend(
                cfg,
                self._make_config(num_gpus_per_node=8, tensor_parallel_size=2, expert_parallel_size=4),
            )

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_moe_multi_gpu_ep_not_set_raises(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["NemotronHForCausalLM"],
            num_local_experts=8,
        )
        mock_registry.model_arch_name_to_cls = {"NemotronHForCausalLM": MagicMock()}

        cfg: dict[str, Any] = {"model": {}}
        with pytest.raises(ValueError, match=r"expert_parallel_size.*not set.*requires expert_parallel_size > 1"):
            _configure_moe_backend(
                cfg,
                self._make_config(num_gpus_per_node=8, expert_parallel_size=None),
            )

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_moe_multi_gpu_ep_eq1_raises(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["NemotronHForCausalLM"],
            num_local_experts=8,
        )
        mock_registry.model_arch_name_to_cls = {"NemotronHForCausalLM": MagicMock()}

        cfg: dict[str, Any] = {"model": {}}
        with pytest.raises(ValueError, match=r"expert_parallel_size is 1.*requires expert_parallel_size > 1"):
            _configure_moe_backend(
                cfg,
                self._make_config(num_gpus_per_node=8, expert_parallel_size=1),
            )

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_moe_single_gpu_skips_multi_gpu_validation(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["NemotronHForCausalLM"],
            num_local_experts=8,
        )
        mock_registry.model_arch_name_to_cls = {"NemotronHForCausalLM": MagicMock()}

        cfg: dict[str, Any] = {"model": {}}
        _configure_moe_backend(cfg, self._make_config(num_gpus_per_node=1, expert_parallel_size=None))

        assert cfg["model"]["backend"]["_target_"] == "nemo_automodel.components.models.common.utils.BackendConfig"

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_dense_custom_model_no_moe_config(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["LlamaForCausalLM"],
        )
        mock_registry.model_arch_name_to_cls = {"LlamaForCausalLM": MagicMock()}

        cfg: dict[str, Any] = {"model": {}}
        _configure_moe_backend(cfg, self._make_config())

        assert "backend" not in cfg["model"]
        assert "parallelizer" not in cfg

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_standard_hf_model_no_custom_config(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["LlamaForCausalLM"],
        )
        mock_registry.model_arch_name_to_cls = {}

        cfg: dict[str, Any] = {"model": {}}
        _configure_moe_backend(cfg, self._make_config())

        assert "backend" not in cfg["model"]
        assert "parallelizer" not in cfg

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_autoconfig_exception_handled_gracefully(self, mock_autoconfig_cls, _mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.side_effect = OSError("Model not found")

        cfg: dict[str, Any] = {"model": {}}
        _configure_moe_backend(cfg, self._make_config())

        assert "backend" not in cfg["model"]
        assert "parallelizer" not in cfg

    @patch(MODEL_REGISTRY_PATCH)
    @patch(AUTOCONFIG_PATCH)
    def test_moe_validation_error_propagates(self, mock_autoconfig_cls, mock_registry) -> None:
        mock_autoconfig_cls.from_pretrained.return_value = self._make_hf_config(
            architectures=["NemotronHForCausalLM"],
            num_local_experts=8,
        )
        mock_registry.model_arch_name_to_cls = {"NemotronHForCausalLM": MagicMock()}

        cfg: dict[str, Any] = {}
        with pytest.raises(ValueError, match="Tensor parallelism"):
            _configure_moe_backend(
                cfg,
                self._make_config(num_gpus_per_node=8, tensor_parallel_size=4, expert_parallel_size=2),
            )
