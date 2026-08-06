# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer


def test_rollback_removes_all_result_directories_for_removed_candidate(tmp_path: Path) -> None:
    root = tmp_path / "eval-and-optimize"
    agents_dir = root / "agents"
    results_dir = root / "results"
    analysis_dir = root / "analysis"
    smoke_dataset_dir = root / "smoke-dataset"
    smoke_results_dir = root / "smoke-results"
    for directory in (agents_dir, results_dir, analysis_dir, smoke_dataset_dir, smoke_results_dir):
        directory.mkdir(parents=True)

    removed_agent = agents_dir / "agent-2"
    removed_agent.mkdir()
    (removed_agent / "metadata.json").write_text(json.dumps({"round": 2}))
    surviving_agent = agents_dir / "agent-20"
    surviving_agent.mkdir()
    (surviving_agent / "metadata.json").write_text(json.dumps({"round": 1}))

    removed_results = [
        results_dir / "agent-2-train",
        results_dir / "agent-2-validation",
        results_dir / "agent-2-custom-channel",
    ]
    for result_dir in removed_results:
        result_dir.mkdir()
    surviving_result = results_dir / "agent-20-custom-channel"
    surviving_result.mkdir()

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    optimizer._delete_all_artifacts(from_round=1)

    assert not removed_agent.exists()
    assert all(not result_dir.exists() for result_dir in removed_results)
    assert surviving_agent.is_dir()
    assert surviving_result.is_dir()
