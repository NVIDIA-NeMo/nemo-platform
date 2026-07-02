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
"""

import glob
import logging
import os
from pathlib import Path

import yaml
from nemo_rl.utils.native_checkpoint import convert_dcp_to_hf
from transformers import AutoModelForCausalLM

logger = logging.getLogger(__name__)


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
