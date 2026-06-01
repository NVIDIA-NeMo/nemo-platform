# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from unittest.mock import Mock

import pandas as pd
import pytest
from httpx import Response
from nemo_platform import NotFoundError, PermissionDeniedError
from nemo_platform.beta.safe_synthesizer.job_builder import SafeSynthesizerJobBuilder
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_safe_synthesizer.config.job import SafeSynthesizerJobConfig, SafeSynthesizerParameters
from nemo_safe_synthesizer.config.replace_pii import ClassifyConfig, Globals, PiiReplacerConfig, StepDefinition
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.safe_synthesizer.api.v2.jobs.endpoints import job_config_compiler

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_client():
    mock_client = Mock()
    # Mock the files.filesets.retrieve to simulate fileset exists
    mock_client.files.filesets.retrieve.return_value = Mock()
    mock_client.files.filesets.create.return_value = Mock()
    mock_client.safe_synthesizer.jobs.create.return_value = Mock(name="test-job-123")
    # Mock sdk.files.upload (high-level file upload)
    mock_client.files.upload.return_value = None

    return mock_client


@pytest.fixture
def basic_builder(mock_client):
    data = pd.read_csv(
        "https://raw.githubusercontent.com/gretelai/gretel-blueprints/refs/heads/main/sample_data/financial_transactions.csv"
    )

    builder = SafeSynthesizerJobBuilder(mock_client).with_data_source(data)
    yield builder


def test_create_job(basic_builder):
    builder = basic_builder.synthesize()

    job = builder.create_job()
    assert job is not None
    # Verify upload was called (data was uploaded)
    builder._client.files.upload.assert_called_once()


def test_create_job_redact_pii(basic_builder):
    builder = basic_builder.with_replace_pii()

    job = builder.create_job()
    assert job is not None
    # Verify upload was called (data was uploaded)
    builder._client.files.upload.assert_called_once()


class TestJobConfigCompilerErrorCases:
    @pytest.mark.asyncio
    async def test_malformed_classify_model_provider(self, mock_client: Mock):
        job_config = _make_job_config(model_provider="no-workspace-in-reference")
        with pytest.raises(PlatformJobCompilationError):
            await _compile_config(job_config, mock_client)

    @pytest.mark.asyncio
    async def test_not_found_classify_model_provider(self, mock_client: Mock):
        mock_client.inference.providers.retrieve.side_effect = NotFoundError(
            "Nope!", response=Response(status_code=401, request=Mock()), body={}
        )
        job_config = _make_job_config(model_provider="default/my-provider")

        with pytest.raises(PlatformJobCompilationError) as exc_info:
            await _compile_config(job_config, mock_client)

        assert "Could not find model provider" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unauthorized_classify_model_provider(self, mock_client: Mock):
        mock_client.inference.providers.retrieve.side_effect = PermissionDeniedError(
            "Nope!", response=Response(status_code=401, request=Mock()), body={}
        )
        job_config = _make_job_config(model_provider="default/my-provider")

        with pytest.raises(PlatformJobCompilationError) as exc_info:
            await _compile_config(job_config, mock_client)

        assert "Access denied to workspace" in str(exc_info.value)


def _make_job_config(model_provider: str) -> SafeSynthesizerJobConfig:
    return SafeSynthesizerJobConfig(
        data_source="foo",
        config=SafeSynthesizerParameters(
            replace_pii=PiiReplacerConfig(
                globals=Globals(
                    classify=ClassifyConfig(
                        classify_model_provider=model_provider,
                    )
                ),
                steps=[StepDefinition()],
            ),
        ),
    )


async def _compile_config(config: SafeSynthesizerJobConfig, mock_client: Mock) -> PlatformJobSpec:
    return await job_config_compiler(
        workspace="default",
        original_spec=config,
        transformed_spec=config,
        entity_client=Mock(),
        job_name="job_name",
        sdk=mock_client,
    )
