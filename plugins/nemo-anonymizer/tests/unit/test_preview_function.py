# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from anonymizer.config.anonymizer_config import AnonymizerConfig
from anonymizer.config.replace_strategies import Redact
from nemo_anonymizer_plugin.app.errors import AnonymizerInvalidConfigError
from nemo_anonymizer_plugin.app.input import AnonymizerInputSpec
from nemo_anonymizer_plugin.app.model_configs import SelectedModelsOverrides
from nemo_anonymizer_plugin.functions import _preview_worker as worker_module
from nemo_anonymizer_plugin.functions._preview_logs import request_callback_cvar
from nemo_anonymizer_plugin.functions.preview import LogFrame, PreviewFunction, PreviewSpec, TraceDatasetFrame
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.function_context import FunctionContext
from pydantic import BaseModel


def _preview_spec(tmp_path: Path) -> PreviewSpec:
    csv = tmp_path / "input.csv"
    csv.write_text("biography\nhello\n")
    return PreviewSpec(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source=str(csv), text_column="biography"),
        num_records=1,
    )


def test_preview_worker_sends_original_text_column_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames: list[BaseModel] = []
    trace_dataframe = pd.DataFrame([{"biography": "hello"}])
    trace_dataframe.attrs["original_text_column"] = "biography"

    class FakeResult:
        dataframe = pd.DataFrame([{"biography": "hello"}])
        failed_records: list[object] = []

        def __init__(self) -> None:
            self.trace_dataframe = trace_dataframe

    class FakeAnonymizer:
        def preview(self, **kwargs: object) -> FakeResult:
            return FakeResult()

    monkeypatch.setattr(worker_module, "_make_anonymizer", lambda **kwargs: FakeAnonymizer())

    worker_module._make_preview(
        frames.append,
        _preview_spec(tmp_path),
        data=object(),  # type: ignore[arg-type]
        model_configs_yaml="",
        dd_providers=None,
        num_records=1,
    )

    trace_frame = next(frame for frame in frames if isinstance(frame, TraceDatasetFrame))
    assert trace_frame.original_text_column == "biography"


@pytest.mark.asyncio
async def test_preview_function_resets_request_log_callback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_worker(
        send_frame: Callable[[BaseModel], None],
        *args: object,
    ) -> None:
        send_frame(LogFrame(level="info", message="generated"))

    monkeypatch.setattr(worker_module, "_make_preview", fake_worker)

    frames = [
        frame
        async for frame in PreviewFunction().run(
            _preview_spec(tmp_path),
            ctx=FunctionContext(workspace="team-a"),
            async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
            is_local=True,
        )
    ]

    assert [frame.model_dump()["kind"] for frame in frames] == ["log", "done"]
    assert request_callback_cvar.get() is None


@pytest.mark.asyncio
async def test_preview_function_rejects_selected_models_without_model_configs(tmp_path: Path) -> None:
    spec = _preview_spec(tmp_path).model_copy(
        update={"selected_models": SelectedModelsOverrides(detection={"entity_detector": "local"})}
    )

    with pytest.raises(AnonymizerInvalidConfigError, match="selected_models requires model_configs"):
        [
            frame
            async for frame in PreviewFunction().run(
                spec,
                ctx=FunctionContext(workspace="team-a"),
                async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
                is_local=True,
            )
        ]


@pytest.mark.asyncio
async def test_preview_submit_requires_model_configs(tmp_path: Path) -> None:
    with pytest.raises(AnonymizerInvalidConfigError, match="model_configs are required"):
        [
            frame
            async for frame in PreviewFunction().run(
                _preview_spec(tmp_path).model_copy(
                    update={"data": AnonymizerInputSpec(source="https://example.com/input.csv")}
                ),
                ctx=FunctionContext(workspace="team-a"),
                async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
                is_local=False,
            )
        ]
