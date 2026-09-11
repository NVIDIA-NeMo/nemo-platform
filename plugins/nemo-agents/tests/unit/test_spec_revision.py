# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Recording the revision a deployment actually staged."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from nemo_agents_plugin.spec_revision import SpecRevision, stage_with_spec_revision
from nemo_platform_plugin.files.storage_config import GithubStorageConfig

FIRST_SHA = "1" * 40
SECOND_SHA = "2" * 40
THIRD_SHA = "3" * 40


@contextmanager
def _fileset_reporting(*revisions: str) -> Iterator[None]:
    """Serve each revision in turn for the agent's fileset, then the last one forever."""
    responses = [
        SimpleNamespace(
            data=lambda revision=revision: SimpleNamespace(
                storage=GithubStorageConfig(owner="acme", repo="agents", revision=revision, original_revision="main")
            )
        )
        for revision in revisions
    ]
    client = AsyncMock()
    client.get_fileset = AsyncMock(side_effect=lambda **_: responses.pop(0) if len(responses) > 1 else responses[0])

    with patch("nemo_agents_plugin.spec_revision.client_from_platform", return_value=client):
        yield


class TestStageWithSpecRevision:
    async def test_records_the_revision_staging_read(self) -> None:
        stage = AsyncMock(return_value="staged")

        with _fileset_reporting(FIRST_SHA):
            staged, spec = await stage_with_spec_revision(
                MagicMock(), workspace="default", agent_name="calc", stage=stage
            )

        assert (staged, spec) == ("staged", SpecRevision(revision=FIRST_SHA, tracked_revision="main"))
        assert stage.await_count == 1

    async def test_restages_when_a_refresh_lands_mid_stage(self) -> None:
        stage = AsyncMock(return_value="staged")

        with _fileset_reporting(FIRST_SHA, SECOND_SHA, SECOND_SHA):
            _, spec = await stage_with_spec_revision(MagicMock(), workspace="default", agent_name="calc", stage=stage)

        # Recording SECOND_SHA against content downloaded at FIRST_SHA is the bug;
        # the second staging pass is what makes the recorded revision true.
        assert spec.revision == SECOND_SHA
        assert stage.await_count == 2

    async def test_records_the_last_revision_when_it_keeps_moving(self) -> None:
        stage = AsyncMock(return_value="staged")

        with _fileset_reporting(FIRST_SHA, SECOND_SHA, THIRD_SHA):
            _, spec = await stage_with_spec_revision(MagicMock(), workspace="default", agent_name="calc", stage=stage)

        assert spec.revision == THIRD_SHA
        assert stage.await_count == 2

    async def test_stages_anyway_when_provenance_cannot_be_read(self) -> None:
        """An SDK the adapter rejects costs the deployment its revision, not its deployment."""
        stage = AsyncMock(return_value="staged")

        with patch("nemo_agents_plugin.spec_revision.client_from_platform", side_effect=TypeError("not a client")):
            staged, spec = await stage_with_spec_revision(
                MagicMock(), workspace="default", agent_name="calc", stage=stage
            )

        assert (staged, spec) == ("staged", SpecRevision())
        assert stage.await_count == 1
