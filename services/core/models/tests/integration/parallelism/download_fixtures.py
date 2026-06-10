#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
One-time script to download HuggingFace model config files for offline test fixtures.

Run this script when adding new models to parallelism tests:
    uv run python services/core/models/tests/integration/parallelism/download_fixtures.py

It downloads config.json (and model_config.yaml if present) for each model
into the fixtures/ directory, enabling tests to run without network access.
"""

import json
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# All non-gated model IDs used across parallelism integration tests.
# Gated models (meta-llama/*, google/gemma-*) are already skipped via REQUIRES_HF_TOKEN.
MODEL_IDS = [
    "gpt2",
    "microsoft/phi-2",
    "microsoft/phi-4",
    "mistralai/Mixtral-8x7B-v0.1",
    "mistralai/Mistral-7B-v0.1",
    "mistralai/Devstral-Small-2505",
    "nvidia/Mistral-NeMo-Minitron-8B-Instruct",
    "nvidia/NVIDIA-Nemotron-Nano-9B-v2",
    "nvidia/nemotron-4-340b-instruct",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "EleutherAI/gpt-j-6b",
    "EleutherAI/gpt-neox-20b",
    "Qwen/Qwen3-8B",
    "Qwen/Qwen3-4B-SafeRL",
    "Qwen/Qwen2.5-7B",
    "Qwen/Qwen2.5-72B",
    "Qwen/Qwen2.5-72B-Instruct",
    "deepseek-ai/deepseek-llm-7b-base",
    "deepseek-ai/deepseek-llm-67b-base",
    "deepseek-ai/DeepSeek-V3-Base",
]


def _model_dir(model_id: str) -> Path:
    """Return the fixture directory for a model, e.g. fixtures/gpt2 or fixtures/microsoft/phi-4."""
    return FIXTURES_DIR / model_id


def download_model_configs(model_id: str) -> None:
    dest = _model_dir(model_id)
    dest.mkdir(parents=True, exist_ok=True)

    got_config_json = False
    for filename in ("config.json", "model_config.yaml"):
        try:
            cached_path = hf_hub_download(model_id, filename)
            shutil.copy2(cached_path, dest / filename)
            print(f"  [OK] {model_id}/{filename}")
            if filename == "config.json":
                got_config_json = True
        except Exception:
            # model_config.yaml is optional; config.json is required unless
            # model_config.yaml exists (NeMo YAML-only models like Nemotron-4-340B)
            pass

    if not got_config_json and not (dest / "model_config.yaml").exists():
        raise RuntimeError(f"Neither config.json nor model_config.yaml found for {model_id}")

    # Download custom config/model Python files referenced by auto_map.
    # These are needed for AutoConfig.from_pretrained(trust_remote_code=True).
    if got_config_json:
        config = json.loads((dest / "config.json").read_text())
        auto_map = config.get("auto_map", {})
        for key, value in auto_map.items():
            # value is like "configuration_nemotron_h.NemotronHConfig"
            module_name = value.split(".")[0]
            py_file = f"{module_name}.py"
            try:
                cached_path = hf_hub_download(model_id, py_file)
                shutil.copy2(cached_path, dest / py_file)
                print(f"  [OK] {model_id}/{py_file}")
            except Exception:
                print(f"  [WARN] {model_id}/{py_file} not found (auto_map: {key}={value})")


def main() -> None:
    print(f"Downloading config fixtures to {FIXTURES_DIR}/\n")
    for model_id in MODEL_IDS:
        print(f"Downloading {model_id}...")
        download_model_configs(model_id)
    print("\nDone! Fixtures are ready for offline tests.")

    # Write a manifest so the conftest can validate completeness
    manifest = {mid: sorted(str(p.name) for p in _model_dir(mid).iterdir()) for mid in MODEL_IDS}
    manifest_path = FIXTURES_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Wrote manifest to {manifest_path}")


if __name__ == "__main__":
    main()
