# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    MetricResult,
    ResourceRef,
    TrialResult,
)
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import RemoteExperimentalistBackend

pytestmark = pytest.mark.asyncio


def _backend(tmp_path: Path) -> RemoteExperimentalistBackend:
    # client=None: no platform client, so the composed LocalExperimentalistBackend persists
    # to files only (its projection is a no-op without a client). This exercises remote-mode
    # delegation; the projection itself is covered in tests/test_local_backend_projection.py.
    return RemoteExperimentalistBackend(client=None, path=tmp_path)


async def test_create_run_writes_run_json(tmp_path: Path) -> None:
    be = _backend(tmp_path)
    run = ExperimentRun(workspace="default", agent="a", config_snapshot={}, status="running", rounds_completed=0)
    out = await be.create_run(workspace="default", run=run)
    assert out.id  # local backend assigns an id
    assert (tmp_path / "eval-and-optimize" / "run.json").exists()


async def test_create_candidate_writes_metadata_json(tmp_path: Path) -> None:
    be = _backend(tmp_path)
    c = Candidate(run_id="run-1", label="agent-0", round=0, optimization="baseline")
    out = await be.create_candidate(workspace="default", candidate=c)
    assert out.label == "agent-0"
    meta = tmp_path / "eval-and-optimize" / "agents" / "agent-0" / "metadata.json"
    assert meta.exists()
    assert json.loads(meta.read_text())["label"] == "agent-0"


async def test_candidate_trial_details_round_trip_through_metadata_json(tmp_path: Path) -> None:
    be = _backend(tmp_path)
    trial_json = {
        "id": "task-a__attempt-2",
        "task_id": "task-a",
        "attempt": 2,
        "status": "failed",
        "trace": {
            "uri": "file:///tmp/trace.jsonl",
            "description": "Agent trace",
            "metadata": {"format": "jsonl"},
        },
        "outputs": {"answer": "42"},
        "resources": {
            "workspace": {
                "uri": "file:///tmp/workspace",
                "description": "Final workspace",
                "metadata": {"kind": "directory"},
            }
        },
        "metrics": {
            "reward": {
                "name": "reward",
                "value": 0.0,
                "spec": None,
                "metadata": {"source": "harbor"},
            }
        },
        "error": {
            "type": "RuntimeError",
            "message": "agent failed",
            "traceback": "RuntimeError: agent failed",
        },
        "metadata": {"harbor_trial_dir": "/tmp/job/task-a__attempt-2"},
    }
    trial = TrialResult(
        id="task-a__attempt-2",
        task_id="task-a",
        attempt=2,
        status="failed",
        trace=ResourceRef(
            uri="file:///tmp/trace.jsonl",
            description="Agent trace",
            metadata={"format": "jsonl"},
        ),
        outputs={"answer": "42"},
        resources={
            "workspace": ResourceRef(
                uri="file:///tmp/workspace",
                description="Final workspace",
                metadata={"kind": "directory"},
            )
        },
        metrics={
            "reward": MetricResult(
                name="reward",
                value=0.0,
                metadata={"source": "harbor"},
            )
        },
        error={
            "type": "RuntimeError",
            "message": "agent failed",
            "traceback": "RuntimeError: agent failed",
        },
        metadata={"harbor_trial_dir": "/tmp/job/task-a__attempt-2"},
    )
    candidate = Candidate(
        run_id="run-1",
        label="agent-0",
        round=0,
        optimization="baseline",
        train_reward={"reward": 0.0},
        train_reward_details=[trial],
    )

    await be.create_candidate(workspace="default", candidate=candidate)
    loaded = await be.get_candidate(workspace="default", candidate_id="agent-0")

    assert loaded.train_reward_details is not None
    assert len(loaded.train_reward_details) == 1
    assert loaded.train_reward_details[0].model_dump(mode="json") == trial_json
