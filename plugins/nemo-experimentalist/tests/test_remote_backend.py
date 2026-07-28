# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import RemoteExperimentalistBackend

pytestmark = pytest.mark.asyncio


def _backend(tmp_path: Path) -> RemoteExperimentalistBackend:
    # client=None: no platform client, so the composed LocalExperimentalistBackend persists
    # to files only (its projection is a no-op without a client). This exercises remote-mode
    # delegation; the projection itself is covered in tests/test_local_backend_projection.py.
    return RemoteExperimentalistBackend(client=None, path=tmp_path)  # type: ignore[arg-type]


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
