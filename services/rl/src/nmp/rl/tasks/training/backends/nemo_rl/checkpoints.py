# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Checkpoint publication helpers for NeMo-RL training.

DTensor V1 writes PyTorch Distributed Checkpoint (DCP) trees that still need
``convert_dcp_to_hf``. DTensor V2 / Automodel already writes HuggingFace
safetensors (optionally under ``model/consolidated``), so publication must copy
that tree instead of sending it to the DCP converter, which requires a
``.metadata`` file and fails on the HF layout.

LoRA adapters are nested under ``<step>/policy/`` rather than at the checkpoint
root the way an Automodel SFT export does.
"""

import glob
import json
import logging
import os
import re
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

# Full-weight HF trees, most specific first. Automodel writes shards to
# ``policy/weights/model`` and, when consolidation ran, a loadable HF export under
# ``model/consolidated``. V1 DCP lives in ``policy/weights`` and is not listed here.
HF_FULL_WEIGHT_SEARCH_PATHS: tuple[Path, ...] = (
    Path("policy") / "weights" / "model" / "consolidated",
    Path("policy") / "weights" / "model",
    Path("policy") / "weights",
)

_DCP_METADATA_SEARCH_PATHS: tuple[Path, ...] = (
    Path("policy") / "weights" / "model",
    Path("policy") / "weights",
)

# Automodel internals that must not become the published HuggingFace root.
_HF_SKIP_NAMES = {
    ".hf_metadata",
    "consolidated",
    "consolidate.sh",
    "fqn_to_file_index_mapping.json",
    "fqn_to_dtype_mapping.json",
}

# shard-00001-model-00001-of-00001.safetensors -> model-00001-of-00001.safetensors
_AUTOMODEL_SHARD_RE = re.compile(r"^shard-\d+-(model-\d+-of-\d+\.safetensors)$")


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
    _copy_tokenizer_if_missing(checkpoint_path, output_path)


def _copy_tokenizer_if_missing(checkpoint_path: Path, output_path: Path) -> None:
    if (output_path / "tokenizer_config.json").is_file():
        return
    tokenizer_dir = checkpoint_path / RL_TOKENIZER_SUBPATH
    if not tokenizer_dir.is_dir():
        logger.warning(
            "No tokenizer found at %s; the published tree is without one",
            tokenizer_dir,
        )
        return
    logger.info("Copying tokenizer from %s to %s", tokenizer_dir, output_path)
    shutil.copytree(tokenizer_dir, output_path, dirs_exist_ok=True)


def _is_peft_weight_dir(path: Path) -> bool:
    return (path / "adapter_config.json").is_file() or (path / "adapter_model.safetensors").is_file()


def _has_dcp_metadata(path: Path) -> bool:
    return (path / ".metadata").is_file()


def _weight_safetensors(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(p for p in path.glob("*.safetensors") if p.is_file() and p.name != "adapter_model.safetensors")


def find_hf_full_weight_root(checkpoint_path: Path) -> Path | None:
    """Return the directory holding full-weight HuggingFace safetensors, or None.

    Prefers Automodel's consolidated export when present. Directories that are DCP
    (``.metadata``) or PEFT adapters are skipped so V1 conversion still runs.
    """
    for relative in HF_FULL_WEIGHT_SEARCH_PATHS:
        candidate = checkpoint_path / relative
        if _has_dcp_metadata(candidate) or _is_peft_weight_dir(candidate):
            continue
        if _weight_safetensors(candidate):
            return candidate
    return None


def find_dcp_weights_root(checkpoint_path: Path) -> Path | None:
    """Return the DCP directory that contains ``.metadata``, or None."""
    for relative in _DCP_METADATA_SEARCH_PATHS:
        candidate = checkpoint_path / relative
        if _has_dcp_metadata(candidate):
            return candidate
    return None


def _flatten_hf_metadata(model_dir: Path, output_path: Path) -> None:
    metadata_dir = model_dir / ".hf_metadata"
    if not metadata_dir.is_dir():
        return
    for item in metadata_dir.iterdir():
        if item.name in _HF_SKIP_NAMES:
            continue
        dest = output_path / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def _promote_automodel_shards(output_path: Path) -> None:
    """Rewrite Automodel ``shard-*-model-*-of-*.safetensors`` names to HuggingFace names.

    Rank-local shards that share the same ``model-NNNN-of-NNNN`` suffix still need
    Automodel consolidation and are left unchanged. A single file per suffix (the
    one-GPU GRPO layout) is a complete tensor set and is renamed so Platform's
    fileset checks (``model.safetensors`` / ``model-*.safetensors``) accept it.
    """
    groups: dict[str, list[Path]] = {}
    for path in _weight_safetensors(output_path):
        match = _AUTOMODEL_SHARD_RE.match(path.name)
        if match:
            groups.setdefault(match.group(1), []).append(path)
    if not groups:
        return
    if any(len(files) != 1 for files in groups.values()):
        logger.warning(
            "Automodel wrote multi-rank shards under %s without a consolidated/ "
            "export; publishing the shard files as-is. Multi-GPU all_weights GRPO "
            "needs a consolidated HuggingFace tree to load with from_pretrained.",
            output_path,
        )
        return
    for hf_name, (shard,) in groups.items():
        target_name = "model.safetensors" if hf_name == "model-00001-of-00001.safetensors" else hf_name
        target = output_path / target_name
        if target.exists():
            continue
        logger.info("Publishing %s as %s", shard.name, target_name)
        shard.rename(target)


def _fix_fsdp2_architecture(model_path: Path) -> None:
    """Strip the FSDP prefix FSDP2 may write into ``config.json`` architectures."""
    config_path = model_path / "config.json"
    if not config_path.is_file():
        return
    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s to fix FSDP2 architectures: %s", config_path, exc)
        return
    original = config.get("architectures")
    if not original:
        return
    fixed = [arch.removeprefix("FSDP") if isinstance(arch, str) else arch for arch in original]
    if original == fixed:
        return
    config["architectures"] = fixed
    config_path.write_text(json.dumps(config, indent=2))
    logger.info("Fixed FSDP2 architecture names: %s -> %s", original, fixed)


def copy_hf_full_weights(checkpoint_path: Path, weights_root: Path, output_path: Path) -> None:
    """Copy an already-HuggingFace full-weight tree to ``output_path``.

    Optimizer shards under ``policy/optimizer`` are left behind. Automodel metadata
    (``.hf_metadata``, ``consolidate.sh``) is not published; ``config.json`` and
    tokenizer files from ``.hf_metadata`` are flattened onto the output root.
    """
    output_path.mkdir(parents=True, exist_ok=True)
    for item in weights_root.iterdir():
        if item.name in _HF_SKIP_NAMES:
            continue
        dest = output_path / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    _flatten_hf_metadata(weights_root, output_path)
    if weights_root.name == "consolidated":
        _flatten_hf_metadata(weights_root.parent, output_path)
    _promote_automodel_shards(output_path)
    _copy_tokenizer_if_missing(checkpoint_path, output_path)
    _fix_fsdp2_architecture(output_path)


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
