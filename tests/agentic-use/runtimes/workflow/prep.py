# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare NAT workflow files for container execution."""

from __future__ import annotations

from pathlib import Path

import yaml


def prepare_workflow_for_runtime(
    workflow_path: Path,
    output_dir: Path,
    nmp_base_url: str,
    *,
    nat_model: str | None = None,
) -> Path:
    """Prepare a NAT workflow file compatible with current NAT schema."""
    text = workflow_path.read_text(encoding="utf-8")
    text = text.replace("http://localhost:8080", nmp_base_url)
    if nat_model:
        text = text.replace(
            "model_name: nvidia/llama-3.1-nemotron-70b-instruct",
            f"model_name: {nat_model}",
            1,
        )

    if "_type: mcp_client" in text or "_type: per_user_mcp_client" in text:
        if "\nfunction_groups:\n" not in text and "\nfunctions:\n" in text:
            text = text.replace("\nfunctions:\n", "\nfunction_groups:\n", 1)

    config = yaml.safe_load(text)
    if not isinstance(config, dict):
        raise ValueError(f"Workflow config must be a mapping: {workflow_path}")
    general = config.setdefault("general", {})
    if not isinstance(general, dict):
        raise ValueError(f"Workflow general config must be a mapping: {workflow_path}")
    telemetry = general.setdefault("telemetry", {})
    if not isinstance(telemetry, dict):
        raise ValueError(f"Workflow telemetry config must be a mapping: {workflow_path}")
    tracing = telemetry.setdefault("tracing", {})
    if not isinstance(tracing, dict):
        raise ValueError(f"Workflow telemetry tracing config must be a mapping: {workflow_path}")
    tracing["agentic_use_file_trace"] = {
        "_type": "file",
        "output_path": "/logs/agent/intermediate_steps.jsonl",
        "project": "agentic-use",
        "mode": "overwrite",
        "cleanup_on_init": True,
    }

    text = yaml.dump(config, default_flow_style=False, sort_keys=False)
    rewritten = output_dir / "workflow.runtime.yml"
    rewritten.write_text(text, encoding="utf-8")
    return rewritten
