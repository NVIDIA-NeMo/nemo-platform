# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, Mock

import nmp.evaluator.entities as entities
import pytest
from httpx import Response
from nemo_evaluator_sdk.enums import MetricType, ModelFormat
from nemo_evaluator_sdk.metrics.llm_judge import default_judge_prompt_template_chat
from nemo_evaluator_sdk.values import Model, RemoteScore, Rubric, RubricScore, SecretRef
from nmp.common.entities import SYSTEM_WORKSPACE
from nmp.common.entities.client import EntityClient
from nmp.evaluator.api.v2.metrics.manager import (
    MetricCreationError,
    MetricDeletionError,
    MetricRetrievalError,
    MetricsManager,
)
from nmp.evaluator.api.v2.metrics.schemas.metrics import LLMJudgeMetric
from nmp.evaluator.api.v2.metrics.schemas.metrics_resp import LLMJudgeMetricResponse
from nmp.testing import create_test_client


def create_not_found_error(message: str):
    """Helper to create a NotFoundError with required arguments."""
    from nemo_platform import NotFoundError

    mock_response = Mock(spec=Response)
    mock_response.status_code = 404
    mock_response.headers = {}
    return NotFoundError(message=message, response=mock_response, body={"detail": message})


@pytest.fixture
def mock_entity_client() -> Generator[EntityClient, None, None]:
    """Real EntityClient backed by in-memory storage for integration-style testing."""
    # Include workspaces needed by tests (default + cross-workspace tests)
    workspaces = ["default", "workspace1", "workspace2", "production", SYSTEM_WORKSPACE]
    with create_test_client(client_type=EntityClient, workspaces=workspaces) as client:
        yield client


# mock_sdk fixture is now provided by conftest.py


@pytest.fixture
def metrics_service(mock_entity_client) -> MetricsManager:
    """MetricsManager instance with mocked EntityClient."""
    return MetricsManager(mock_entity_client)


@pytest.fixture
def sample_metric_entity():
    """Sample LLMJudgeMetric entity for testing."""
    entity = entities.LLMJudgeMetric(
        name="test-metric",
        workspace="default",
        type=MetricType.LLM_JUDGE,
        description="Test metric",
        model=Model(
            url="https://api.openai.com/v1",
            name="gpt-4o",
            format=ModelFormat.OPEN_AI,
        ),
        prompt_template="Rate the response: {output}",
        scores=[
            RubricScore(
                name="quality",
                description="Quality of response",
                rubric=[
                    Rubric(label="good", description="Good response", value=1),
                    Rubric(label="bad", description="Bad response", value=0),
                ],
            )
        ],
    )
    # Set private attributes that would normally be set by the entity store
    entity._id = "metric-123"
    entity._created_at = datetime(2024, 1, 1, 0, 0, 0)
    entity._updated_at = datetime(2024, 1, 1, 0, 0, 0)
    return entity


@pytest.fixture
def sample_metric_entity_with_secret():
    """Sample LLMJudgeMetric entity with API key secret for testing."""
    return entities.LLMJudgeMetric(
        name="test-metric-with-secret",
        workspace="default",
        description="Test metric with secret",
        model=Model(
            url="https://api.openai.com/v1",
            name="gpt-4o",
            format=ModelFormat.OPEN_AI,
            api_key_secret=SecretRef(root="my-secret"),
        ),
        prompt_template="Rate the response: {output}",
        scores=[
            RubricScore(
                name="quality",
                description="Quality of response",
                rubric=[
                    Rubric(label="good", description="Good response", value=1),
                    Rubric(label="bad", description="Bad response", value=0),
                ],
            )
        ],
    )


@pytest.fixture
def sample_metric_request():
    """Sample LLMJudgeMetric for testing create_from_request method."""
    return LLMJudgeMetric(
        description="Test metric",
        model=Model(
            url="https://api.openai.com/v1",
            name="gpt-4o",
            format=ModelFormat.OPEN_AI,
        ),
        prompt_template="Rate the response: {output}",
        scores=[
            RubricScore(
                name="quality",
                description="Quality of response",
                rubric=[
                    Rubric(label="good", description="Good response", value=1),
                    Rubric(label="bad", description="Bad response", value=0),
                ],
            )
        ],
    )


@pytest.fixture
def sample_system_metric_entity() -> entities.SystemMetric:
    """Sample SystemMetric entity for testing internal system metric helpers."""
    return entities.SystemMetric(
        name="system-metric",
        description="System metric",
    )


class TestMetricsServiceGetAll:
    """Tests for MetricsManager.get_all method."""

    @pytest.mark.asyncio
    async def test_get_all_returns_empty_list(self, metrics_service):
        """Test get_all returns empty list when no metrics exist."""
        # Act
        result = await metrics_service.get_all(workspace="default")

        # Assert
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_get_all_returns_metrics(self, metrics_service, mock_entity_client, sample_metric_entity):
        """Test get_all returns all metrics for a workspace."""
        # Arrange - Add entities to the mock entity client
        await mock_entity_client.create(sample_metric_entity)

        entity2 = entities.LLMJudgeMetric(
            name="test-metric-2",
            workspace="default",
            description="Test metric 2",
            model=Model(
                url="https://api.openai.com/v1",
                name="gpt-3.5",
                format=ModelFormat.OPEN_AI,
            ),
            prompt_template="Rate: {output}",
            scores=[
                RubricScore(
                    name="score",
                    description="Score",
                    rubric=[
                        Rubric(label="yes", description="Yes", value=1),
                        Rubric(label="no", description="No", value=0),
                    ],
                )
            ],
        )
        await mock_entity_client.create(entity2)

        # Act
        result = await metrics_service.get_all(workspace="default")

        # Assert
        assert len(result.data) == 2
        assert all(isinstance(m, LLMJudgeMetricResponse) for m in result.data)
        # Results might be in any order
        names = {r.name for r in result.data}
        assert names == {"test-metric", "test-metric-2"}


class TestMetricsServiceGetByName:
    """Tests for MetricsManager.get_by_name method."""

    @pytest.mark.asyncio
    async def test_get_by_name_returns_metric(self, metrics_service, mock_entity_client, sample_metric_entity):
        """Test get_by_name returns the metric when it exists."""
        # Arrange - Add entity to the mock entity client
        await mock_entity_client.create(sample_metric_entity)

        # Act
        result = await metrics_service.get_by_name(workspace="default", name="test-metric")

        # Assert
        assert result is not None
        assert isinstance(result, LLMJudgeMetricResponse)
        assert result.created_at is not None, "missing entity private attributes"
        assert result.name == "test-metric"

    @pytest.mark.asyncio
    async def test_get_by_name_raises_error_when_not_found(self, metrics_service):
        """Test get_by_name raises MetricRetrievalError when metric not found."""
        # Act & Assert
        with pytest.raises(MetricRetrievalError) as exc_info:
            await metrics_service.get_by_name(workspace="default", name="nonexistent")

        assert isinstance(exc_info.value, MetricRetrievalError)
        assert exc_info.value.error_code == "METRIC_NOT_FOUND"
        assert "default/nonexistent" in exc_info.value.detail


class TestMetricsServiceCreate:
    """Tests for MetricsManager.create method."""

    @pytest.mark.asyncio
    async def test_create_without_api_key(self, metrics_service, sample_metric_entity, mock_sdk):
        """Test create successfully creates a metric without API key."""
        # Act
        result = await metrics_service.create(sample_metric_entity, sdk=mock_sdk)

        # Assert
        assert result is not None
        assert isinstance(result, LLMJudgeMetricResponse)
        assert result.created_at is not None, "missing entity private attributes"
        assert result.name == sample_metric_entity.name
        assert result.id is not None  # ID is auto-generated

    @pytest.mark.asyncio
    async def test_create_bleu_metric(self, metrics_service, mock_sdk):
        """Test create successfully creates a BLEU metric (no model resolution needed).

        Regression test for NVBug 5827225.
        """
        # Arrange
        bleu_metric = entities.BLEUMetric(
            name="test-bleu-metric",
            workspace="default",
            references=["{{item.reference}}"],
        )

        # Act
        result = await metrics_service.create(bleu_metric, sdk=mock_sdk)

        # Assert
        assert result is not None
        assert result.name == "test-bleu-metric"
        assert result.type == "bleu"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_rouge_metric(self, metrics_service, mock_sdk):
        """Test create successfully creates a ROUGE metric (no model resolution needed).

        Regression test for NVBug 5827225.
        """
        # Arrange
        rouge_metric = entities.ROUGEMetric(
            name="test-rouge-metric",
            workspace="default",
            reference="{{item.reference}}",
        )

        # Act
        result = await metrics_service.create(rouge_metric, sdk=mock_sdk)

        # Assert
        assert result is not None
        assert result.name == "test-rouge-metric"
        assert result.type == "rouge"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_string_check_metric(self, metrics_service, mock_sdk):
        """Test create successfully creates a StringCheck metric (no model resolution needed).

        Regression test for NVBug 5827225.
        """
        # Arrange
        string_check_metric = entities.StringCheckMetric(
            name="test-string-check-metric",
            workspace="default",
            operation="contains",
            left_template="{{item.response}}",
            right_template="{{item.expected}}",
        )

        # Act
        result = await metrics_service.create(string_check_metric, sdk=mock_sdk)

        # Assert
        assert result is not None
        assert result.name == "test-string-check-metric"
        assert result.type == "string-check"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_with_valid_api_key(self, metrics_service, sample_metric_entity_with_secret, mock_sdk):
        """Test create successfully creates a metric with valid API key secret."""
        # Arrange
        mock_secret = MagicMock()
        mock_secret.root = "my-secret"
        mock_sdk.secrets.retrieve = AsyncMock(return_value=mock_secret)

        # Act
        result = await metrics_service.create(sample_metric_entity_with_secret, sdk=mock_sdk)

        # Assert
        assert result is not None
        assert isinstance(result, LLMJudgeMetricResponse)
        assert result.created_at is not None, "missing entity private attributes"
        assert result.name == sample_metric_entity_with_secret.name
        mock_sdk.secrets.retrieve.assert_called_once_with("my-secret", workspace="default")

    @pytest.mark.asyncio
    async def test_create_with_invalid_api_key_raises_error(
        self, metrics_service, sample_metric_entity_with_secret, mock_sdk
    ):
        """Test create raises MetricCreationError when API key secret not found."""
        # Arrange
        mock_sdk.secrets.retrieve = AsyncMock(side_effect=create_not_found_error("Secret not found"))

        # Act & Assert
        with pytest.raises(MetricCreationError) as exc_info:
            await metrics_service.create(sample_metric_entity_with_secret, sdk=mock_sdk)

        assert isinstance(exc_info.value, MetricCreationError)
        assert exc_info.value.error_code == "SECRET_NOT_FOUND"
        assert "default/my-secret" in exc_info.value.detail
        assert "test-metric-with-secret" in exc_info.value.detail
        mock_sdk.secrets.retrieve.assert_called_once_with("my-secret", workspace="default")

    @pytest.mark.asyncio
    async def test_create_remote_metric_validates_api_key_secret(self, metrics_service, mock_sdk):
        """Test create validates remote metric API key secrets."""
        metric_entity = entities.RemoteMetric(
            name="remote-metric-with-secret",
            workspace="default",
            url="https://remote.example.test/score",
            api_key_secret="remote-secret",
            body={"input": "{{sample.output_text}}"},
            scores=[RemoteScore(name="score")],
        )

        await metrics_service.create(metric_entity, sdk=mock_sdk)

        mock_sdk.secrets.retrieve.assert_called_once_with("remote-secret", workspace="default")


class TestMetricsServiceCreateFromRequest:
    """Tests for MetricsService.create_from_request method."""

    @pytest.mark.asyncio
    async def test_create_from_request_llm_judge(self, metrics_service, sample_metric_request, mock_sdk):
        """Test create_from_request creates LLMJudge metric from request DTO."""
        # Act
        result = await metrics_service.create_from_request(
            name="test-llm-judge",
            workspace="default",
            request=sample_metric_request,
            sdk=mock_sdk,
        )

        # Assert
        assert result is not None
        assert isinstance(result, LLMJudgeMetricResponse)
        assert result.created_at is not None, "missing entity private attributes"
        assert result.name == "test-llm-judge"
        assert result.workspace == "default"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_from_request_bleu(self, metrics_service, mock_sdk):
        """Test create_from_request creates BLEU metric from request DTO."""
        from nmp.evaluator.api.v2.metrics.schemas.metrics import BLEUMetric

        # Arrange
        bleu_request = BLEUMetric(
            references=["{{item.reference}}"],
        )

        # Act
        result = await metrics_service.create_from_request(
            name="test-bleu",
            workspace="default",
            request=bleu_request,
            sdk=mock_sdk,
        )

        # Assert
        assert result is not None
        assert result.name == "test-bleu"
        assert result.workspace == "default"
        assert result.type == "bleu"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_from_request_llm_judge_without_prompt_template(
        self,
        metrics_service,
        mock_sdk,
    ):
        """Zero-config LLM Judge should auto-populate a prompt template."""
        request = LLMJudgeMetric(
            description="Zero config metric",
            model=Model(
                url="https://inference-api.nvidia.com/v1/chat/completions",
                name="nvidia/openai/gpt-oss-20b",
                format=ModelFormat.OPEN_AI,
            ),
            scores=[
                RubricScore(
                    name="quality",
                    rubric=[
                        Rubric(label="poor", value=0),
                        Rubric(label="good", value=1),
                    ],
                )
            ],
        )

        result = await metrics_service.create_from_request(
            name="test-llm-judge-zero-config",
            workspace="default",
            request=request,
            sdk=mock_sdk,
        )

        assert isinstance(result, LLMJudgeMetricResponse)
        assert result.prompt_template == default_judge_prompt_template_chat()


class TestMetricsServiceDelete:
    """Tests for MetricsManager.delete method."""

    @pytest.mark.asyncio
    async def test_delete_successful(self, metrics_service, mock_entity_client, sample_metric_entity):
        """Test delete successfully deletes a metric."""
        # Arrange - Add entity first
        await mock_entity_client.create(sample_metric_entity)

        # Act
        result = await metrics_service.delete(workspace="default", name="test-metric")

        # Assert
        assert result.message == "Resource deleted successfully"

        # Verify it's actually deleted
        with pytest.raises(MetricRetrievalError):
            await metrics_service.get_by_name(workspace="default", name="test-metric")

    @pytest.mark.asyncio
    async def test_delete_raises_error_when_not_found(self, metrics_service):
        """Test delete raises MetricDeletionError when metric not found."""
        # Act & Assert
        with pytest.raises(MetricDeletionError) as exc_info:
            await metrics_service.delete(workspace="default", name="nonexistent")

        assert isinstance(exc_info.value, MetricDeletionError)
        assert exc_info.value.error_code == "METRIC_NOT_FOUND"
        assert "default/nonexistent" in exc_info.value.detail


class TestGetRegisteredSystemMetrics:
    """Tests for MetricsManager._get_registered_system_metrics method."""

    @pytest.mark.asyncio
    async def test_returns_only_system_metric_entities(
        self,
        metrics_service,
        mock_entity_client,
        sample_metric_entity,
        sample_system_metric_entity,
    ):
        """Test helper returns typed system metrics scoped to the system workspace."""
        await mock_entity_client.create(sample_metric_entity)
        await mock_entity_client.create(sample_system_metric_entity)

        result = await metrics_service._get_registered_system_metrics()

        assert len(result.data) == 1
        assert isinstance(result.data[0], entities.SystemMetric)
        assert result.data[0].name == sample_system_metric_entity.name
        assert result.data[0].workspace == SYSTEM_WORKSPACE


class TestDeleteAllSystemMetrics:
    """Tests for MetricsManager.delete_all_system_metrics method."""

    @pytest.mark.asyncio
    async def test_deletes_only_system_metrics(
        self,
        metrics_service,
        mock_entity_client,
        sample_metric_entity,
        sample_system_metric_entity,
    ):
        """Test helper deletes all system metrics without touching regular metrics."""
        second_system_metric = entities.SystemMetric(
            name="system-metric-2",
            description="Second system metric",
        )
        await mock_entity_client.create(sample_metric_entity)
        await mock_entity_client.create(sample_system_metric_entity)
        await mock_entity_client.create(second_system_metric)

        await metrics_service.delete_all_system_metrics()

        remaining_system_metrics = await mock_entity_client.list(entities.SystemMetric, workspace=SYSTEM_WORKSPACE)
        remaining_regular_metrics = await mock_entity_client.list(entities.Metric, workspace="default")

        assert remaining_system_metrics.data == []
        assert len(remaining_regular_metrics.data) == 1
        assert remaining_regular_metrics.data[0].name == sample_metric_entity.name


class TestMetricsServiceExists:
    """Tests for MetricsManager.exists method."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_metric_exists(
        self, metrics_service, mock_entity_client, sample_metric_entity
    ):
        """Test exists returns True when metric exists."""
        # Arrange - Add entity first
        await mock_entity_client.create(sample_metric_entity)

        # Act
        result = await metrics_service.exists(workspace="default", name="test-metric")

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_metric_not_found(self, metrics_service):
        """Test exists returns False when metric not found."""
        # Act
        result = await metrics_service.exists(workspace="default", name="nonexistent")

        # Assert
        assert result is False


class TestMetricsServiceEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_get_all_with_different_workspace(self, metrics_service, mock_entity_client, sample_metric_entity):
        """Test get_all filters by workspace_id correctly."""
        # Arrange - Add metric to default workspace
        await mock_entity_client.create(sample_metric_entity)

        # Add metric to production workspace
        prod_entity = entities.LLMJudgeMetric(
            name="prod-metric",
            workspace="production",
            type=MetricType.LLM_JUDGE,
            description="Production metric",
            model=Model(
                url="https://api.openai.com/v1",
                name="gpt-4o",
                format=ModelFormat.OPEN_AI,
            ),
            prompt_template="Rate: {output}",
            scores=[
                RubricScore(
                    name="score",
                    description="Score",
                    rubric=[
                        Rubric(label="good", description="Good", value=1),
                        Rubric(label="bad", description="Bad", value=0),
                    ],
                )
            ],
        )
        await mock_entity_client.create(prod_entity)

        # Act
        default_results = await metrics_service.get_all(workspace="default")
        prod_results = await metrics_service.get_all(workspace="production")

        # Assert - each workspace has only its own metrics
        assert len(default_results.data) == 1
        assert default_results.data[0].name == "test-metric"
        assert len(prod_results.data) == 1
        assert prod_results.data[0].name == "prod-metric"

    @pytest.mark.asyncio
    async def test_create_with_malformed_api_key_reference(self, metrics_service, mock_sdk):
        """Test create handles malformed API key reference gracefully."""
        # Arrange - This should fail during secret validation because the secret is not found.
        # This test verifies the error handling in the service layer.
        metric_entity = entities.LLMJudgeMetric(
            name="test-metric",
            workspace="default",
            description="Test",
            model=Model(
                url="https://api.openai.com/v1",
                name="gpt-4o",
                format=ModelFormat.OPEN_AI,
                api_key_secret=SecretRef(root="valid-secret"),  # Valid format
            ),
            prompt_template="Rate: {output}",
            scores=[
                RubricScore(
                    name="score",
                    description="Score",
                    rubric=[
                        Rubric(label="good", description="Good", value=1),
                        Rubric(label="bad", description="Bad", value=0),
                    ],
                )
            ],
        )

        mock_sdk.secrets.retrieve = AsyncMock(side_effect=create_not_found_error("Secret not found"))

        # Act & Assert
        with pytest.raises(MetricCreationError):
            await metrics_service.create(metric_entity, sdk=mock_sdk)
