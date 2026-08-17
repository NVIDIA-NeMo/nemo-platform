# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Locating and publishing LoRA adapters inside a NeMo-RL checkpoint."""

from pathlib import Path

from nmp.rl.tasks.training.backends.nemo_rl.checkpoints import (
    copy_lora_adapter,
    find_lora_adapter_root,
)


def _write_adapter(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "adapter_config.json").write_text('{"peft_type": "LORA"}')
    (directory / "adapter_model.safetensors").write_text("weights")
    return directory


def _write_tokenizer(checkpoint: Path) -> Path:
    tokenizer = checkpoint / "policy" / "tokenizer"
    tokenizer.mkdir(parents=True, exist_ok=True)
    (tokenizer / "tokenizer_config.json").write_text("{}")
    (tokenizer / "tokenizer.json").write_text("{}")
    return tokenizer


def test_finds_adapter_in_dtensor_v2_layout(tmp_path: Path):
    """Automodel writes model artifacts to <weights_path>/model, so V2 nests one deeper."""
    checkpoint = tmp_path / "step_20"
    adapter = _write_adapter(checkpoint / "policy" / "weights" / "model")

    assert find_lora_adapter_root(checkpoint) == adapter


def test_finds_adapter_in_dtensor_v1_layout(tmp_path: Path):
    checkpoint = tmp_path / "step_20"
    adapter = _write_adapter(checkpoint / "policy" / "weights")

    assert find_lora_adapter_root(checkpoint) == adapter


def test_finds_adapter_at_checkpoint_root(tmp_path: Path):
    checkpoint = tmp_path / "step_20"
    _write_adapter(checkpoint)

    assert find_lora_adapter_root(checkpoint) == checkpoint


def test_prefers_the_most_specific_layout(tmp_path: Path):
    """A stray root-level config must not shadow the real adapter under policy/weights."""
    checkpoint = tmp_path / "step_20"
    _write_adapter(checkpoint)
    nested = _write_adapter(checkpoint / "policy" / "weights" / "model")

    assert find_lora_adapter_root(checkpoint) == nested


def test_returns_none_for_a_full_weight_checkpoint(tmp_path: Path):
    checkpoint = tmp_path / "step_20"
    weights = checkpoint / "policy" / "weights"
    weights.mkdir(parents=True)
    (weights / ".metadata").write_text("dcp")

    assert find_lora_adapter_root(checkpoint) is None


def test_copy_publishes_only_the_adapter_and_adds_the_tokenizer(tmp_path: Path):
    """Optimizer state is a training artifact and must not reach the published model."""
    checkpoint = tmp_path / "step_20"
    adapter = _write_adapter(checkpoint / "policy" / "weights" / "model")
    _write_tokenizer(checkpoint)
    optimizer = checkpoint / "policy" / "optimizer"
    optimizer.mkdir(parents=True)
    (optimizer / "optim.pt").write_text("optimizer state")

    output = tmp_path / "output"
    copy_lora_adapter(checkpoint, adapter, output)

    assert (output / "adapter_config.json").is_file()
    assert (output / "adapter_model.safetensors").is_file()
    assert (output / "tokenizer_config.json").is_file()
    assert not (output / "policy").exists()
    assert not (output / "optim.pt").exists()


def test_copy_keeps_a_tokenizer_already_beside_the_adapter(tmp_path: Path):
    """When Automodel already wrote one, the checkpoint-level copy must not clobber it."""
    checkpoint = tmp_path / "step_20"
    adapter = _write_adapter(checkpoint / "policy" / "weights" / "model")
    (adapter / "tokenizer_config.json").write_text('{"source": "adapter"}')
    tokenizer = _write_tokenizer(checkpoint)
    (tokenizer / "tokenizer_config.json").write_text('{"source": "checkpoint"}')

    output = tmp_path / "output"
    copy_lora_adapter(checkpoint, adapter, output)

    assert '"source": "adapter"' in (output / "tokenizer_config.json").read_text()


def test_copy_without_a_tokenizer_still_publishes_the_adapter(tmp_path: Path):
    checkpoint = tmp_path / "step_20"
    adapter = _write_adapter(checkpoint / "policy" / "weights" / "model")

    output = tmp_path / "output"
    copy_lora_adapter(checkpoint, adapter, output)

    assert (output / "adapter_config.json").is_file()
    assert not (output / "tokenizer_config.json").exists()
