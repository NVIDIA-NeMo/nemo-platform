# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import data_designer.config as dd
import nemo_anonymizer_plugin.tasks.anonymizer.run as task_run_module
import pytest
from anonymizer.config.anonymizer_config import AnonymizerConfig
from anonymizer.config.replace_strategies import Redact
from data_designer.engine.model_provider import ModelProvider as NDDModelProvider
from data_designer.engine.model_provider import ModelProviderRegistry
from data_designer_nemo.errors import NDDInvalidConfigError
from nemo_anonymizer_plugin.app import context as context_module
from nemo_anonymizer_plugin.app.input import AnonymizerInputSpec
from nemo_anonymizer_plugin.app.model_configs import SelectedModelsOverrides
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest, AnonymizerStepConfig
from nemo_anonymizer_plugin.jobs import run as run_module
from nemo_anonymizer_plugin.jobs.run import RunJob
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError


def _make_job_context(tmp_path: Path, *, workspace: str = "team-a") -> JobContext:
    storage = StoragePaths(ephemeral=tmp_path / "ephemeral", persistent=tmp_path / "persistent")
    storage.ephemeral.mkdir(parents=True, exist_ok=True)
    storage.persistent.mkdir(parents=True, exist_ok=True)
    return JobContext(
        workspace=workspace,
        storage=storage,
        results=LocalJobResults(root=storage.persistent / "results"),
    )


def _snapshot_task_loggers() -> dict[str, tuple[list[logging.Handler], int, bool]]:
    snapshot = {}
    for logger_name in ("anonymizer", "data_designer", "nemo_anonymizer_plugin"):
        logger = logging.getLogger(logger_name)
        snapshot[logger_name] = (list(logger.handlers), logger.level, logger.propagate)
    return snapshot


def _restore_task_loggers(snapshot: dict[str, tuple[list[logging.Handler], int, bool]]) -> None:
    for logger_name, (handlers, level, propagate) in snapshot.items():
        logger = logging.getLogger(logger_name)
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate


@pytest.mark.asyncio
async def test_run_job_rejects_selected_models_without_model_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source="https://example.com/input.csv", text_column="text"),
        selected_models=SelectedModelsOverrides(detection={"entity_detector": "local"}),
    )
    monkeypatch.setattr(RunJob, "_validate_anonymizer_config", classmethod(lambda cls, config: None))

    with pytest.raises(PlatformJobCompilationError, match="selected_models requires model_configs"):
        await RunJob.to_spec(
            request,
            workspace="team-a",
            entity_client=object(),
            async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_run_job_wraps_shared_provider_config_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source="https://example.com/input.csv", text_column="text"),
        model_configs=[dd.ModelConfig(alias="detector", model="test/model", provider="missing")],
    )
    monkeypatch.setattr(RunJob, "_validate_anonymizer_config", classmethod(lambda cls, config: None))
    monkeypatch.setattr(
        context_module,
        "make_model_provider_registry",
        AsyncMock(side_effect=NDDInvalidConfigError("bad provider")),
    )

    with pytest.raises(PlatformJobCompilationError, match="bad provider"):
        await RunJob.to_spec(
            request,
            workspace="team-a",
            entity_client=object(),
            async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_run_submit_requires_model_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source="https://example.com/input.csv", text_column="text"),
    )
    monkeypatch.setattr(RunJob, "_validate_anonymizer_config", classmethod(lambda cls, config: None))

    with pytest.raises(PlatformJobCompilationError, match="model_configs are required"):
        await RunJob.to_spec(
            request,
            workspace="team-a",
            entity_client=object(),
            async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_run_local_allows_missing_model_configs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("text\nhello\n")
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source=str(csv), text_column="text"),
    )
    monkeypatch.setattr(RunJob, "_validate_anonymizer_config", classmethod(lambda cls, config: None))

    step_config = await RunJob.to_spec(
        request,
        workspace="team-a",
        entity_client=object(),
        async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
        is_local=True,
    )

    assert isinstance(step_config, AnonymizerStepConfig)
    assert step_config.model_configs_yaml == ""
    assert step_config.dd_model_providers == []
    round_tripped = AnonymizerStepConfig.model_validate(step_config.model_dump())
    assert isinstance(round_tripped.request.config.replace, Redact)


@pytest.mark.asyncio
async def test_run_local_model_configs_uses_injected_async_sdk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("text\nhello\n")
    local_first_registry = ModelProviderRegistry(
        providers=[NDDModelProvider(name="local-provider", endpoint="http://localhost:8000")],
    )
    local_first_lookup = AsyncMock(return_value=local_first_registry)
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source=str(csv), text_column="text"),
        model_configs=[dd.ModelConfig(alias="detector", model="local/model", provider="local-provider")],
    )
    monkeypatch.setattr(RunJob, "_validate_anonymizer_config", classmethod(lambda cls, config: None))
    monkeypatch.setattr(context_module, "make_local_first_model_provider_registry", local_first_lookup)
    async_sdk = AsyncMock(spec=AsyncNeMoPlatform)

    step_config = await RunJob.to_spec(
        request,
        workspace="team-a",
        entity_client=object(),
        async_sdk=async_sdk,
        is_local=True,
    )

    local_first_lookup.assert_awaited_once()
    assert local_first_lookup.await_args is not None
    assert local_first_lookup.await_args.kwargs["sdk"] is async_sdk
    assert isinstance(step_config, AnonymizerStepConfig)
    assert len(step_config.dd_model_providers) == 1
    assert step_config.dd_model_providers[0]["name"] == "local-provider"


@pytest.mark.asyncio
async def test_run_local_serialized_step_config_can_be_revalidated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("text\nhello\n")
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source=str(csv), text_column="text"),
    )
    monkeypatch.setattr(RunJob, "_validate_anonymizer_config", classmethod(lambda cls, config: None))
    monkeypatch.setattr(run_module, "run_step_config", lambda *args, **kwargs: 0)

    step_config = await RunJob.to_spec(
        request,
        workspace="team-a",
        entity_client=object(),
        async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
        is_local=True,
    )

    ctx = _make_job_context(tmp_path)
    assert RunJob().run(
        step_config.model_dump(),
        ctx=ctx,
        sdk=Mock(spec=NeMoPlatform),
        is_local=True,
    ) == {"exit_code": 0}


def test_run_step_config_local_uses_ctx_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("text\nhello\n")
    captured: dict[str, object] = {}

    class FakeFrame:
        def __init__(self, rows: int, body: str):
            self._rows = rows
            self._body = body

        def __len__(self) -> int:
            return self._rows

        def to_parquet(self, path: Path, *, index: bool) -> None:
            captured[f"{self._body}_index"] = index
            path.write_text(self._body)

    class FakeResult:
        dataframe = FakeFrame(1, "dataset")
        trace_dataframe = FakeFrame(0, "trace")
        failed_records: list[object] = []

    class FakeAnonymizer:
        def __init__(
            self,
            *,
            model_configs: str | None,
            model_providers: object,
            artifact_path: Path,
        ) -> None:
            captured["model_configs"] = model_configs
            captured["model_providers"] = model_providers
            captured["artifact_path"] = artifact_path

        def run(self, *, config: AnonymizerConfig, data: object) -> FakeResult:
            captured["config"] = config
            captured["data"] = data
            return FakeResult()

    step_config = AnonymizerStepConfig(
        request=AnonymizerRequest(
            config=AnonymizerConfig(replace=Redact()),
            data=AnonymizerInputSpec(source=str(csv), text_column="text"),
        ),
        model_configs_yaml="",
        dd_model_providers=[],
    )

    monkeypatch.setattr(task_run_module, "Anonymizer", FakeAnonymizer)
    ctx = _make_job_context(tmp_path)
    logging_snapshot = _snapshot_task_loggers()

    try:
        assert (
            task_run_module.run_step_config(
                step_config,
                ctx=ctx,
                is_local=True,
            )
            == 0
        )
    finally:
        _restore_task_loggers(logging_snapshot)
    assert captured["artifact_path"] == ctx.storage.persistent / "anonymizer-artifacts"
    artifacts_dir = ctx.storage.persistent / "artifacts"
    assert (artifacts_dir / "dataset.parquet").read_text() == "dataset"
    assert (artifacts_dir / "trace.parquet").read_text() == "trace"
    assert json.loads((artifacts_dir / "metadata.json").read_text()) == {"original_text_column": "text"}
    saved_artifacts_dir = ctx.storage.persistent / "results" / task_run_module.ARTIFACTS_RESULT_NAME
    assert (saved_artifacts_dir / "dataset.parquet").read_text() == "dataset"
    assert captured["dataset_index"] is False
    assert captured["trace_index"] is False


def test_run_step_config_remote_requires_sdk(tmp_path: Path) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("text\nhello\n")
    step_config = AnonymizerStepConfig(
        request=AnonymizerRequest(
            config=AnonymizerConfig(replace=Redact()),
            data=AnonymizerInputSpec(source=str(csv), text_column="text"),
        ),
        model_configs_yaml="",
        dd_model_providers=[],
    )
    ctx = _make_job_context(tmp_path)
    logging_snapshot = _snapshot_task_loggers()

    try:
        assert task_run_module.run_step_config(step_config, ctx=ctx, is_local=False) == 1
    finally:
        _restore_task_loggers(logging_snapshot)


@pytest.mark.asyncio
async def test_run_submit_rejects_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv = tmp_path / "input.csv"
    csv.write_text("text\nhello\n")
    request = AnonymizerRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source=str(csv), text_column="text"),
        model_configs=[dd.ModelConfig(alias="detector", model="test/model", provider="provider")],
    )
    monkeypatch.setattr(RunJob, "_validate_anonymizer_config", classmethod(lambda cls, config: None))

    with pytest.raises(PlatformJobCompilationError, match="local path"):
        await RunJob.to_spec(
            request,
            workspace="team-a",
            entity_client=object(),
            async_sdk=AsyncMock(spec=AsyncNeMoPlatform),
            is_local=False,
        )
