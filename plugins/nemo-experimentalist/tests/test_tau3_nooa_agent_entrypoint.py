# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tau3 agent entrypoint compatibility with the trusted Harbor adapter."""

import sys
from importlib import util
from pathlib import Path

AGENT_MAIN = Path(__file__).parents[1] / "examples" / "tau3-nooa-agent" / "main.py"


def _load_main():
    spec = util.spec_from_file_location("tau3_nooa_agent_main", AGENT_MAIN)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_entrypoint_accepts_harbor_prompt_file_contract(tmp_path: Path, monkeypatch) -> None:
    main = _load_main()
    prompt_file = tmp_path / "instruction.txt"
    prompt_file.write_text("trusted task instruction", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "--prompt-file",
            str(prompt_file),
            "--trace-path",
            "/app/traces/trace.jsonl",
            "--summary-path",
            "/logs/agent/summary.json",
        ],
    )

    assert main.prompt_from_args(main.parse_args()) == "trusted task instruction"
