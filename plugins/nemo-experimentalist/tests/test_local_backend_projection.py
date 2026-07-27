# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""LocalExperimentalistBackend's best-effort projection onto native platform Experiments.

The projection is active only when the backend has a platform client (the real-world
local-mode-with-a-live-platform run); without a client it is a no-op. A projection failure
must never fail the run or the local-file persistence (spec §3 / F).
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nemo_experimentalist_plugin.entities import Candidate, ExperimentRun
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import LocalExperimentalistBackend
from nemo_experimentalist_plugin.experimentalist.result import ExperimentalistResult

pytestmark = pytest.mark.asyncio


def _run() -> ExperimentRun:
    return ExperimentRun(workspace="default", agent="a", config_snapshot={}, status="running", rounds_completed=0)


async def test_no_projection_without_client(tmp_path: Path) -> None:
    # No platform client → projection is a no-op; local files still written, no mirror built.
    be = LocalExperimentalistBackend(client=None, path=tmp_path)
    out = await be.create_run(workspace="default", run=_run())
    assert out.id
    assert (tmp_path / "eval-and-optimize" / "run.json").exists()
    assert be._mirrors == {}  # never constructed a mirror


async def test_create_run_projects_when_client_present(tmp_path: Path) -> None:
    # A platform client is present → create_run best-effort projects (ensure_group).
    be = LocalExperimentalistBackend(client=SimpleNamespace(), path=tmp_path)
    be._mirrors["default"] = AsyncMock()  # injected so no real SDK call is made
    await be.create_run(workspace="default", run=_run())
    be._mirrors["default"].ensure_group.assert_awaited_once()
    assert (tmp_path / "eval-and-optimize" / "run.json").exists()


async def test_create_candidate_projects_when_client_present(tmp_path: Path) -> None:
    be = LocalExperimentalistBackend(client=SimpleNamespace(), path=tmp_path)
    be._mirrors["default"] = AsyncMock()
    await be.create_candidate(
        workspace="default",
        candidate=Candidate(run_id="run-1", label="agent-0", round=0, optimization="baseline"),
    )
    be._mirrors["default"].project_candidate.assert_awaited_once()


async def test_persist_result_projects_finalize(tmp_path: Path) -> None:
    be = LocalExperimentalistBackend(client=SimpleNamespace(), path=tmp_path)
    be._mirrors["default"] = AsyncMock()
    await be.persist_result(
        workspace="default",
        result=ExperimentalistResult(summary="done", run_id="run-1", rounds_completed=1, winner=None),
    )
    be._mirrors["default"].finalize.assert_awaited_once()


async def test_projection_failure_is_swallowed(tmp_path: Path) -> None:
    # A projection failure must never fail the run or the local-file write.
    class _BoomMirror:
        async def ensure_group(self, _run: ExperimentRun) -> None:
            raise RuntimeError("platform down")

    be = LocalExperimentalistBackend(client=SimpleNamespace(), path=tmp_path)
    be._mirrors["default"] = _BoomMirror()
    out = await be.create_run(workspace="default", run=_run())  # must NOT raise
    assert out.id
    assert (tmp_path / "eval-and-optimize" / "run.json").exists()
