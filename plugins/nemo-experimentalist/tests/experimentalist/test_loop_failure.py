# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_experimentalist_plugin.entities import ExperimentRun
from nemo_experimentalist_plugin.experimentalist.components import loop as loop_module
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizer
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import LocalExperimentalistBackend
from nemo_experimentalist_plugin.resolve import EvolutionaryOptimizerConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_method", ["create", "evaluate"])
async def test_baseline_failure_marks_run_failed(monkeypatch, tmp_path, failure_method):
    candidate = SimpleNamespace(label="agent-0")
    evolution_tree = SimpleNamespace(survivors=lambda round_num: [candidate])
    backend = LocalExperimentalistBackend(path=tmp_path)
    run_entity = await backend.create_run(
        workspace="default",
        run=ExperimentRun(
            workspace="default",
            agent="agent",
            config_snapshot={},
            status="running",
            rounds_completed=0,
        ),
    )
    monkeypatch.setattr(backend, "get_agent_code", AsyncMock())
    config = EvolutionaryOptimizerConfig()

    monkeypatch.setattr(
        loop_module,
        "EvaluatorFactory",
        lambda: SimpleNamespace(build_evaluator=lambda *args, **kwargs: object()),
    )
    monkeypatch.setattr(
        loop_module,
        "DatasetFactory",
        lambda: SimpleNamespace(build_dataset=lambda *args, **kwargs: object()),
    )
    monkeypatch.setattr(loop_module.EvolutionTree, "from_dir", lambda path: evolution_tree)
    monkeypatch.setattr(EvolutionaryOptimizer, "_init_structure", lambda self: (tmp_path, tmp_path, tmp_path))
    monkeypatch.setattr(EvolutionaryOptimizer, "_detect_last_round", lambda self: None)
    monkeypatch.setattr(
        EvolutionaryOptimizer,
        "_create_experiment_run",
        AsyncMock(return_value=run_entity),
    )
    baseline_failure = ValueError("baseline failed")
    create_baseline = (
        AsyncMock(side_effect=baseline_failure) if failure_method == "create" else AsyncMock(return_value=candidate)
    )
    monkeypatch.setattr(EvolutionaryOptimizer, "_create_baseline_agent", create_baseline)
    monkeypatch.setattr(EvolutionaryOptimizer, "_update_candidate", AsyncMock())
    evaluate_validation = (
        AsyncMock(side_effect=baseline_failure)
        if failure_method == "evaluate"
        else AsyncMock(return_value={"agent-0": object()})
    )
    monkeypatch.setattr(EvolutionaryOptimizer, "_evaluate_validation_candidates", evaluate_validation)

    optimizer = object.__new__(EvolutionaryOptimizer)
    optimizer.working_dir = tmp_path
    optimizer.config = config
    optimizer.shell = SimpleNamespace(close=AsyncMock())
    deps = SimpleNamespace(
        backend=backend,
        workspace="default",
        config=config,
        evaluator_type="harbor",
        train_dataset=object(),
        validation_dataset=object(),
        insight=None,
        agent=tmp_path / "agent",
        agent_spec=None,
        task_template=None,
    )

    with pytest.raises(ValueError, match="baseline failed"):
        await optimizer.run(deps)

    optimizer.shell.close.assert_awaited_once()
    assert run_entity.status == "failed"
    saved = json.loads((tmp_path / "eval-and-optimize" / "run.json").read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
