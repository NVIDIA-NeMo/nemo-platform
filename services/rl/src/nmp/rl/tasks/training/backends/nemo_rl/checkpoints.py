# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""DCP → HuggingFace checkpoint conversion utilities.

This module handles conversion of Distributed Checkpoint (DCP) format
used by PyTorch/NeMo to HuggingFace format for model serving and distribution.

It also locates LoRA adapters inside a NeMo-RL checkpoint. NeMo-RL nests policy
artifacts under ``<step>/policy/``, so an adapter never sits at the checkpoint root
the way an Automodel export does.
"""

import glob
import logging
import os
import shutil
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Where a LoRA adapter can sit inside a NeMo-RL checkpoint, most specific first.
#
# DTensor V2 delegates to Automodel's checkpointer, which writes every model artifact to
# ``<weights_path>/model`` -- so with NeMo-RL passing
# ``<step>/policy/weights`` as weights_path, the PEFT files land in
# ``<step>/policy/weights/model``. The V1 layout writes directly to weights_path, and the
# bare root is kept for adapters exported by something other than the policy worker.
LORA_ADAPTER_SEARCH_PATHS: tuple[Path, ...] = (
    Path("policy") / "weights" / "model",
    Path("policy") / "weights",
    Path(),
)

# NeMo-RL saves the tokenizer beside the weights rather than inside them, so a copied
# adapter tree would otherwise ship without one.
RL_TOKENIZER_SUBPATH = Path("policy") / "tokenizer"


def find_lora_adapter_root(checkpoint_path: Path) -> Path | None:
    """Return the directory holding ``adapter_config.json``, or None if there is none."""
    for relative in LORA_ADAPTER_SEARCH_PATHS:
        candidate = checkpoint_path / relative
        if (candidate / "adapter_config.json").is_file():
            return candidate
    return None


def copy_lora_adapter(checkpoint_path: Path, adapter_root: Path, output_path: Path) -> None:
    """Copy an adapter tree to ``output_path``, adding the tokenizer when it is elsewhere.

    Only the adapter directory is copied: the checkpoint root also holds optimizer shards
    and scheduler state, which are training artifacts rather than part of the published
    model.
    """
    output_path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(adapter_root, output_path, dirs_exist_ok=True)

    tokenizer_dir = checkpoint_path / RL_TOKENIZER_SUBPATH
    if (output_path / "tokenizer_config.json").is_file():
        return
    if not tokenizer_dir.is_dir():
        logger.warning(
            "No tokenizer found at %s; the adapter tree is published without one",
            tokenizer_dir,
        )
        return
    logger.info("Copying tokenizer from %s to %s", tokenizer_dir, output_path)
    shutil.copytree(tokenizer_dir, output_path, dirs_exist_ok=True)


def convert_dcp_to_huggingface(
    dcp_checkpoint_path: Path,
    output_path: Path,
) -> Path:
    """Convert a DCP checkpoint to HuggingFace format.

    Args:
        dcp_checkpoint_path: Path to the DCP checkpoint directory
        output_path: Path for the output HuggingFace checkpoint
        model_config: Optional model configuration overrides

    Returns:
        Path to the converted HuggingFace checkpoint
    """
    # Imported here, not at module scope: nemo_rl and transformers exist only in the
    # training image, and the adapter helpers in this module must stay importable (and
    # unit-testable) from the platform environment, which ships neither.
    from nemo_rl.utils.native_checkpoint import convert_dcp_to_hf
    from transformers import AutoModelForCausalLM

    with open(dcp_checkpoint_path / "config.yaml", "r") as f:
        config = yaml.safe_load(f)

    model_name_or_path = config["policy"]["model_name"]
    tokenizer_name_or_path = f"{dcp_checkpoint_path}/policy/tokenizer"

    # It saves the weights as a single pytorch_model.bin file (pickle-based PyTorch format).
    hf_ckpt = convert_dcp_to_hf(
        dcp_ckpt_path=f"{dcp_checkpoint_path}/policy/weights",
        hf_ckpt_path=str(output_path),
        model_name_or_path=model_name_or_path,
        tokenizer_name_or_path=tokenizer_name_or_path,
        overwrite=True,
    )

    saved_hf_checkpoint_path = Path(hf_ckpt)
    if not saved_hf_checkpoint_path.exists():
        raise FileNotFoundError(
            f"HF checkpoint not found at {saved_hf_checkpoint_path} after conversion from DCP to HF"
        )
    # Compare resolved paths: convert_dcp_to_hf() may return an absolute path while
    # output_path is relative, and string inequality would then falsely trip even
    # when both point at the same directory.
    if output_path.resolve() != saved_hf_checkpoint_path.resolve():
        raise ValueError(
            f"Output path {output_path} does not match the saved HF checkpoint path {saved_hf_checkpoint_path}"
        )

    # Convert pickle-based .bin format to safetensors format
    # Shards the model into multiple files if larger than 4GB
    model = AutoModelForCausalLM.from_pretrained(saved_hf_checkpoint_path)
    model.save_pretrained(
        saved_hf_checkpoint_path,
        safe_serialization=True,
        max_shard_size="4GB",
    )

    # Remove unnecessary files from DCP checkpoint
    # *.bin files come from the DCP format, which is not needed in the HF safetensors format
    for f in glob.glob(os.path.join(saved_hf_checkpoint_path, "*.bin")) + glob.glob(
        os.path.join(saved_hf_checkpoint_path, "*.bin.index.json")
    ):
        os.remove(f)

    logger.info("Saved HF checkpoint successfully")

    return saved_hf_checkpoint_path
