# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import data_designer.config as dd
import pytest
from nemo_data_designer_plugin.functions.retrieval_preview import RetrievalPreviewFrame, RetrievalPreviewFunction
from nemo_data_designer_plugin.jobs.retrieval_spec import RetrievalGenerateJobConfig, RetrievalPreviewSpec
from nemo_platform_plugin.functions.frames import Done


@pytest.mark.asyncio
async def test_retrieval_preview_uses_preview_generation(tmp_path) -> None:
    spec = RetrievalPreviewSpec(
        generate=RetrievalGenerateJobConfig(corpus=str(tmp_path), provider="default/nvidia-build"),
        num_records=1,
    )
    (tmp_path / "doc.txt").write_text("hello", encoding="utf-8")
    providers = [dd.ModelProvider(name="default/nvidia-build", endpoint="http://igw")]
    dd_ctx = AsyncMock()
    dd_ctx.get_model_providers = AsyncMock(return_value=providers)
    ctx = Mock()
    ctx.workspace = "default"
    preview_result = SimpleNamespace(num_seed_records=1, num_preview_records=1)
    frames = []
    with (
        patch(
            "nemo_data_designer_plugin.functions.retrieval_preview.create_data_designer_context",
            return_value=dd_ctx,
        ),
        patch(
            "nemo_data_designer_plugin.functions.retrieval_preview.execute_generation",
            return_value=preview_result,
        ) as execute,
        patch(
            "nemo_data_designer_plugin.functions.retrieval_preview.async_to_sync_sdk",
            return_value=Mock(),
        ),
    ):
        async for frame in RetrievalPreviewFunction().run(spec, ctx=ctx, async_sdk=AsyncMock(), is_local=False):
            frames.append(frame)
    execute.assert_called_once()
    assert execute.call_args.kwargs["preview"] is True
    assert any(isinstance(frame, RetrievalPreviewFrame) for frame in frames)
    assert isinstance(frames[-1], Done)
