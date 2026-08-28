# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

GENERATION_MANIFEST_FILENAME = "generation_result.json"
GENERATION_MANIFEST_SCHEMA_VERSION = 1


def write_generation_manifest(*, output_dir: Path, output_path: Path, dataset_name: str) -> Path:
    """Write the Stage 0 handoff manifest next to generation artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        stored_output = str(output_path.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        stored_output = str(output_path.resolve())
    payload = {
        "schema_version": GENERATION_MANIFEST_SCHEMA_VERSION,
        "dataset_name": dataset_name,
        "output_path": stored_output,
    }
    manifest_path = output_dir / GENERATION_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def resolve_generation_input(input_path: Path) -> Path:
    """Resolve a generation-result manifest or return an explicit data path."""
    input_path = input_path.resolve()
    if input_path.name != GENERATION_MANIFEST_FILENAME:
        return input_path

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid generation manifest: {input_path}") from exc

    if payload.get("schema_version") != GENERATION_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported generation manifest schema in {input_path}")

    stored_output = payload.get("output_path")
    if not isinstance(stored_output, str) or not stored_output:
        raise ValueError(f"Generation manifest has no output_path: {input_path}")

    output_path = Path(stored_output)
    if not output_path.is_absolute():
        output_path = input_path.parent / output_path
    output_path = output_path.resolve()
    if not output_path.is_file():
        raise FileNotFoundError(f"Generation output referenced by {input_path} does not exist: {output_path}")
    return output_path
