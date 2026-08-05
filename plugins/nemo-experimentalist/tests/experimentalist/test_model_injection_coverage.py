# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Every component the strategy builds must receive the run's resolved tiers.

`ModelTiers` exists so two runs in one process can target different endpoints and a test
can inject fakes without touching the environment, and the runner records what it
resolved as what the run used. A single construction that omits `models=` silently opts
that component out — the build Coder did, which is the one that writes candidate code —
and `config_snapshot` still claims otherwise. Asserting over the source catches the
omission at the construction site rather than needing a live run per component.
"""

import ast
import pathlib

COMPONENTS = {"Coder", "AgentAnalyzer", "Proposer", "Terminator", "GoalTreeGenerator", "GroupLeafScorer"}
SOURCES = ("strategies/evolutionary.py", "components/analyzer.py")


def test_no_component_construction_omits_the_runs_model_tiers() -> None:
    root = pathlib.Path(__file__).resolve().parents[2] / "src/nemo_experimentalist_plugin/experimentalist"
    omissions: list[str] = []
    for rel in SOURCES:
        path = root / rel
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id in COMPONENTS and not any(kw.arg == "models" for kw in node.keywords):
                omissions.append(f"{rel}:{node.lineno} {node.func.id}(...)")
    assert omissions == []
