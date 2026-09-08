# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Locating and publishing the model tree inside a NeMo-RL checkpoint."""

from pathlib import Path

from nmp.rl.tasks.training.backends.nemo_rl.checkpoints import (
    copy_consolidated_hf,
    copy_lora_adapter,
    find_consolidated_hf_root,
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


def _write_consolidated(checkpoint: Path) -> Path:
    """The tree DTensor V2 writes when checkpointing.save_consolidated is set."""
    root = checkpoint / "policy" / "weights" / "model" / "consolidated"
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.json").write_text('{"model_type": "qwen3"}')
    (root / "model.safetensors.index.json").write_text('{"weight_map": {}}')
    (root / "model-00001-of-00001.safetensors").write_text("weights")
    return root


def test_finds_the_consolidated_tree_dtensor_v2_writes(tmp_path: Path):
    expected = _write_consolidated(tmp_path)
    assert find_consolidated_hf_root(tmp_path) == expected


def test_sharded_safetensors_alone_are_not_a_consolidated_tree(tmp_path: Path):
    """Regression guard for nvbug 6740834.

    V2 writes safetensors SHARDS by default, and those carry no DCP .metadata, so the
    publisher's DCP converter died after a successful all-weights run. Shards on their own
    must not be mistaken for a publishable tree -- the consolidated export is what counts.
    """
    model_dir = tmp_path / "policy" / "weights" / "model"
    model_dir.mkdir(parents=True)
    (model_dir / "shard-00001-model-00001-of-00001.safetensors").write_text("weights")

    assert find_consolidated_hf_root(tmp_path) is None


def test_an_empty_consolidated_dir_is_not_published(tmp_path: Path):
    """Automodel creates the directory before writing into it, so existence is not enough."""
    (tmp_path / "policy" / "weights" / "model" / "consolidated").mkdir(parents=True)

    assert find_consolidated_hf_root(tmp_path) is None


def test_a_dcp_checkpoint_has_no_consolidated_tree(tmp_path: Path):
    """DTensor V1 writes real DCP, which still goes through convert_dcp_to_huggingface."""
    weights = tmp_path / "policy" / "weights"
    weights.mkdir(parents=True)
    (weights / ".metadata").write_text("dcp")

    assert find_consolidated_hf_root(tmp_path) is None


def test_copy_publishes_the_consolidated_tree_and_adds_the_tokenizer(tmp_path: Path):
    checkpoint = tmp_path / "step_1"
    root = _write_consolidated(checkpoint)
    tokenizer = checkpoint / "policy" / "tokenizer"
    tokenizer.mkdir(parents=True)
    (tokenizer / "tokenizer_config.json").write_text("{}")
    # A training artifact beside the weights, which must not reach the published model.
    (checkpoint / "policy" / "weights" / "optimizer").mkdir(parents=True, exist_ok=True)

    output = tmp_path / "published"
    copy_consolidated_hf(checkpoint, root, output)

    assert (output / "config.json").is_file()
    assert (output / "model.safetensors.index.json").is_file()
    assert (output / "tokenizer_config.json").is_file()
    assert not (output / "optimizer").exists()
