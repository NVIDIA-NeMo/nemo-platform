# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock

import pytest
from nemo_platform import NotFoundError, PermissionDeniedError
from nemo_safe_synthesizer.config.replace_pii import ClassifyConfig, Globals, PiiReplacerConfig, StepDefinition
from nemo_safe_synthesizer_plugin.api.v2.jobs import endpoints
from nemo_safe_synthesizer_plugin.api.v2.jobs.endpoints import SafeSynthesizerJobConfig as PluginJobConfig
from nemo_safe_synthesizer_plugin.api.v2.jobs.endpoints import SafeSynthesizerParameters, job_config_compiler
from nemo_safe_synthesizer_plugin.runtime import TASK_MODULE
from nmp.common.jobs.exceptions import PlatformJobCompilationError

DEFAULT_WORKSPACE = "default"
DEFAULT_DATA_SOURCE = "default/test-data#file.csv"


@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    sdk.files.filesets.retrieve = AsyncMock()
    sdk.inference.providers.retrieve = AsyncMock()
    sdk.models.get_provider_route_openai_url = MagicMock(
        return_value="http://nmp-host/apis/inference-gateway/v2/workspaces/default/provider/my-nim/-/v1"
    )
    return sdk


@pytest.fixture(autouse=True)
def mock_runtime_command(monkeypatch):
    monkeypatch.setattr(endpoints, "runtime_task_command", lambda _config: ["/runtime/bin/python", "-m", TASK_MODULE])


def _make_spec(data_source: str = DEFAULT_DATA_SOURCE, model_provider: str | None = None):
    replace_pii = None
    if model_provider is not None:
        replace_pii = PiiReplacerConfig(
            globals=Globals(classify=ClassifyConfig(classify_model_provider=model_provider)),
            steps=[StepDefinition()],
        )
    return PluginJobConfig(
        data_source=data_source,
        config=SafeSynthesizerParameters(replace_pii=replace_pii),
    )


async def _compile(spec, mock_sdk):
    return await job_config_compiler(
        workspace=DEFAULT_WORKSPACE,
        original_spec=spec,
        transformed_spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        sdk=mock_sdk,
    )


@pytest.mark.asyncio
async def test_job_config_compiler_validates_data_source(mock_sdk):
    spec = _make_spec(data_source="my-workspace/my-fileset#data.csv")

    await _compile(spec, mock_sdk)

    mock_sdk.files.filesets.retrieve.assert_awaited_once_with(name="my-fileset", workspace="my-workspace")


@pytest.mark.asyncio
async def test_job_config_compiler_data_source_not_found(mock_sdk):
    mock_sdk.files.filesets.retrieve.side_effect = NotFoundError(
        message="not found", response=MagicMock(status_code=404), body=None
    )

    with pytest.raises(PlatformJobCompilationError, match="Could not find fileset"):
        await _compile(_make_spec(), mock_sdk)


@pytest.mark.asyncio
async def test_job_config_compiler_data_source_permission_denied(mock_sdk):
    mock_sdk.files.filesets.retrieve.side_effect = PermissionDeniedError(
        message="denied", response=MagicMock(status_code=403), body=None
    )

    with pytest.raises(PermissionError, match="Access denied to fileset"):
        await _compile(_make_spec(), mock_sdk)


@pytest.mark.asyncio
async def test_job_config_compiler_with_classify_provider(mock_sdk):
    result = await _compile(_make_spec(model_provider="default/my-nim"), mock_sdk)

    mock_sdk.inference.providers.retrieve.assert_awaited_once_with("my-nim", workspace="default")
    step = next(iter(result["steps"]))
    assert step["executor"]["provider"] == "subprocess"
    assert step["executor"]["command"] == ["/runtime/bin/python", "-m", TASK_MODULE]
    env = {e["name"]: e.get("value") for e in step.get("environment", [])}
    assert env["CLASSIFY_LLM_ENDPOINT_PATH"] == "/apis/inference-gateway/v2/workspaces/default/provider/my-nim/-/v1"


@pytest.mark.asyncio
async def test_job_config_compiler_validates_pretrained_model_job(mock_sdk):
    mock_sdk.jobs.results.retrieve = AsyncMock(
        return_value=MagicMock(artifact_url="default/job-results-prior#results/attempt-1/adapter")
    )
    spec = PluginJobConfig.model_validate(
        {
            "data_source": DEFAULT_DATA_SOURCE,
            "pretrained_model_job": "prior-safe-synth-job",
            "config": {},
        }
    )

    await _compile(spec, mock_sdk)

    mock_sdk.jobs.results.retrieve.assert_awaited_once_with(
        name="adapter",
        job="prior-safe-synth-job",
        workspace=DEFAULT_WORKSPACE,
    )


@pytest.mark.asyncio
async def test_job_config_compiler_pretrained_model_job_not_found(mock_sdk):
    mock_sdk.jobs.results.retrieve = AsyncMock(
        side_effect=NotFoundError(message="not found", response=MagicMock(status_code=404), body=None)
    )
    spec = PluginJobConfig.model_validate(
        {
            "data_source": DEFAULT_DATA_SOURCE,
            "pretrained_model_job": "other-ws/prior-safe-synth-job",
            "config": {},
        }
    )

    with pytest.raises(PlatformJobCompilationError, match="Could not find adapter result"):
        await _compile(spec, mock_sdk)


def test_plugin_job_config_rejects_conflicting_pretrained_model_sources():
    with pytest.raises(ValueError, match="Use either 'pretrained_model_job' or 'config.training.pretrained_model'"):
        PluginJobConfig.model_validate(
            {
                "data_source": DEFAULT_DATA_SOURCE,
                "pretrained_model_job": "prior-safe-synth-job",
                "config": {"training": {"pretrained_model": "HuggingFaceTB/SmolLM3-3B"}},
            }
        )


@pytest.mark.asyncio
async def test_job_config_compiler_classify_provider_wrong_format(mock_sdk):
    with pytest.raises(PlatformJobCompilationError, match="Expected 'workspace/provider_name'"):
        await _compile(_make_spec(model_provider="no-slash-here"), mock_sdk)


def test_plugin_job_config_enable_flags():
    spec = PluginJobConfig.model_validate(
        {"data_source": "default/data#file.csv", "config": {"enable_synthesis": False, "enable_replace_pii": False}}
    )

    assert spec.enable_synthesis is False
    assert spec.config.replace_pii is None


def test_plugin_job_config_enable_flags_schema():
    schema = PluginJobConfig.model_json_schema()
    config_schema = schema["$defs"]["SafeSynthesizerParameters"]

    assert "enable_synthesis" not in schema["properties"]
    assert "enable_synthesis" in config_schema["properties"]
    assert "enable_replace_pii" in config_schema["properties"]
