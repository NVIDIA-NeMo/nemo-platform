# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import time
from collections.abc import Callable
from unittest.mock import AsyncMock

import data_designer.config as dd
import pytest
from data_designer_nemo.context import DataDesignerContext, LocalDataDesignerContext
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_data_designer_plugin.functions import preview as preview_module
from nemo_data_designer_plugin.functions._types import LogFrame, PreviewSpec
from nemo_data_designer_plugin.functions.preview import PreviewFunction
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.dependencies import get_sdk_client
from nemo_platform_plugin.function_context import FunctionContext
from nemo_platform_plugin.functions.routes import NDJSON_MEDIA_TYPE, add_function_routes
from pydantic import BaseModel


def _config() -> dd.DataDesignerConfig:
    builder = dd.DataDesignerConfigBuilder(model_configs=[dd.ModelConfig(alias="text", model="model")])
    builder.add_column(
        column_config=dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a"]),
        )
    )
    return builder.build()


def _patch_preview_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bypass real model-config extraction so the test config's incomplete
    # ``ModelConfig`` (no provider) doesn't fail provider resolution. The
    # call site lives inside ``data_designer_nemo.runnable.resolve_runnable_config``
    # since the cross-call-site refactor.
    from data_designer_nemo import runnable as runnable_module

    monkeypatch.setattr(runnable_module, "get_model_configs", lambda config: [])


@pytest.mark.asyncio
async def test_preview_function_streams_worker_frames_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_preview_dependencies(monkeypatch)

    def fake_worker(
        config_builder: dd.DataDesignerConfigBuilder,
        dd_ctx: DataDesignerContext,
        send_frame: Callable[[BaseModel], None],
        *args: object,
    ) -> None:
        assert isinstance(dd_ctx, LocalDataDesignerContext)
        send_frame(LogFrame(level="info", message="generated"))

    # Patch the symbol on ``preview_module`` (not ``_preview_worker``) because
    # ``preview.py`` imports ``make_preview_dataset`` at module load time, so
    # the local reference inside ``PreviewFunction.run`` does not pick up
    # patches applied to ``_preview_worker.make_preview_dataset``.
    monkeypatch.setattr(preview_module, "make_preview_dataset", fake_worker)

    frames = [
        frame
        async for frame in PreviewFunction().run(
            PreviewSpec(config=_config(), num_records=2),
            ctx=FunctionContext(workspace="team-a"),
            async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
            is_local=True,
        )
    ]

    assert [frame.model_dump()["kind"] for frame in frames] == ["log", "done"]


def test_preview_route_streams_ndjson_and_heartbeats(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_preview_dependencies(monkeypatch)

    def slow_worker(
        config_builder: dd.DataDesignerConfigBuilder,
        workspace: str,
        send_frame: Callable[[BaseModel], None],
        *args: object,
    ) -> None:
        send_frame(LogFrame(level="info", message="started"))
        time.sleep(0.05)
        send_frame(LogFrame(level="info", message=f"generated in {workspace}"))

    monkeypatch.setattr(preview_module, "make_preview_dataset", slow_worker)

    app = FastAPI()
    app.dependency_overrides[get_sdk_client] = lambda: AsyncMock(spec=AsyncNeMoPlatform)
    app.include_router(
        add_function_routes(PreviewFunction, heartbeat_interval_seconds=0.01),
        prefix="/apis/data-designer/v2/workspaces/{workspace}",
    )
    client = TestClient(app)

    with client.stream(
        "POST",
        "/apis/data-designer/v2/workspaces/team-a/preview",
        json=PreviewSpec(config=_config(), num_records=2).model_dump(mode="json"),
    ) as resp:
        assert resp.status_code == 200
        assert NDJSON_MEDIA_TYPE in resp.headers["content-type"]
        frames = [json.loads(line) for line in resp.iter_lines() if line]

    kinds = [frame["kind"] for frame in frames]
    assert "heartbeat" in kinds
    assert kinds[-2:] == ["log", "done"]
