# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ModelProviderReconciler."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nemo_platform import AsyncNeMoPlatform
from nemo_platform._exceptions import APIStatusError, ConflictError, NotFoundError
from nemo_platform.types.inference import ServedModelMapping
from nemo_platform.types.inference.model_provider import ModelProvider
from nmp.core.models.controllers.context import ModelContext
from nmp.core.models.controllers.provider_reconciler import (
    PROVIDER_ERROR_RETRY_INTERVAL_SECONDS,
    PROVIDER_ERROR_THRESHOLD_SECONDS,
    PROVIDER_LOST_THRESHOLD_SECONDS,
    ArtifactDetails,
    DiscoveryNonCompliant,
    DiscoverySuccess,
    DiscoveryTransientError,
    ModelProviderReconciler,
    _entity_name_from_discovered_model,
    _infer_backend_format,
    _is_valid_served_model_entity_id,
    _resolve_base_backend_model_id,
)
from nmp.core.models.schemas import ModelProviderStatus


def _discovery_models_from_ids(ids: list[str]) -> list[dict]:
    """Build GET /v1/models data[] entries (id only; root/parent omitted in external-path tests)."""
    return [{"id": i, "root": None, "parent": None} for i in ids]


class _AsyncPaginator:
    """Tiny async iterator for SDK list() calls in reconciler tests."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def test_infer_backend_format():
    assert _infer_backend_format("meta-llama-3-1-8b") == "OPENAI_CHAT"
    assert _infer_backend_format("anthropic.claude-sonnet-4-6") == "ANTHROPIC_MESSAGES"
    assert _infer_backend_format("anthropic/claude-opus-4-7") == "ANTHROPIC_MESSAGES"
    assert _infer_backend_format("CLAUDE-3-haiku") == "ANTHROPIC_MESSAGES"
    assert _infer_backend_format("my-claude-like-model") == "OPENAI_CHAT"


@pytest.fixture
def mock_models_sdk():
    """Create a mock AsyncNeMoPlatform SDK."""
    sdk = MagicMock(spec=AsyncNeMoPlatform)
    # virtual_models.create must be an AsyncMock so tests that exercise the full
    # reconcile path don't fail when _ensure_passthrough_virtual_model awaits it.
    sdk.inference.virtual_models.create = AsyncMock(return_value=None)
    sdk.inference.virtual_models.delete = AsyncMock(return_value=None)
    sdk.inference.virtual_models.list = MagicMock(return_value=_AsyncPaginator([]))
    return sdk


@pytest.fixture
def reconciler(mock_models_sdk):
    """Create a ModelProviderReconciler instance."""
    return ModelProviderReconciler(models_sdk=mock_models_sdk)


# ============================================================================
# _get_available_models_from_provider Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_available_models_from_provider_success(reconciler, mock_models_sdk):
    """Test successfully getting models from OpenAI-compliant provider."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(
        return_value={
            "object": "list",
            "data": [
                {"id": "model-1", "object": "model"},
                {"id": "model-2", "object": "model"},
                {"id": "model-3", "object": "model"},
            ],
        }
    )

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com/v1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoverySuccess)
    assert result.model_ids == ["model-1", "model-2", "model-3"]
    mock_models_sdk.inference.gateway.provider.get.assert_called_once_with(
        "v1/models",
        workspace="test-ns",
        name="test-provider",
    )


@pytest.mark.asyncio
async def test_get_available_models_from_provider_non_compliant_missing_data(reconciler, mock_models_sdk):
    """Test provider with non-OpenAI compliant response (missing 'data' field)."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(
        return_value={"object": "list"}  # Missing 'data'
    )

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoveryNonCompliant)


@pytest.mark.asyncio
async def test_get_available_models_from_provider_non_compliant_wrong_type(reconciler, mock_models_sdk):
    """Test provider with non-dict response."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(
        return_value=["model-1", "model-2"]  # Not a dict
    )

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoveryNonCompliant)


@pytest.mark.asyncio
async def test_get_available_models_from_provider_non_compliant_data_not_list(reconciler, mock_models_sdk):
    """Test provider with 'data' field that is not a list."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(return_value={"object": "list", "data": "not-a-list"})

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoveryNonCompliant)


@pytest.mark.asyncio
async def test_get_available_models_from_provider_skips_invalid_entries(reconciler, mock_models_sdk):
    """Test provider response with some invalid model entries."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(
        return_value={
            "object": "list",
            "data": [
                {"id": "model-1", "object": "model"},
                {"object": "model"},  # Missing 'id'
                "invalid-entry",  # Not a dict
                {"id": 123, "object": "model"},  # Non-string id (int)
                {"id": None, "object": "model"},  # Non-string id (None)
                {"id": "model-2", "object": "model"},
            ],
        }
    )

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    # Should skip invalid entries and return only valid ones
    assert isinstance(result, DiscoverySuccess)
    assert result.model_ids == ["model-1", "model-2"]


@pytest.mark.asyncio
async def test_get_available_models_from_provider_handles_exception(reconciler, mock_models_sdk):
    """Test that exceptions from provider endpoint return DiscoveryTransientError."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(side_effect=Exception("Connection error"))

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoveryTransientError)


@pytest.mark.asyncio
async def test_query_available_models_gateway_404_provider_not_in_cache_is_transient(reconciler, mock_models_sdk):
    """Gateway 404 'Model provider not found' (cache miss) must be treated as transient."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(
        side_effect=APIStatusError(
            "Error code: 404 - {'detail': 'Model provider not found for test-ns/test-provider'}",
            response=mock_response,
            body={"detail": "Model provider not found for test-ns/test-provider"},
        )
    )

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoveryTransientError)


@pytest.mark.asyncio
async def test_query_available_models_502_backend_404_is_non_compliant(reconciler, mock_models_sdk):
    """502 with 'Backend returned 404' means backend has no GET /v1/models — non-compliant."""
    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(
        side_effect=APIStatusError(
            "Error code: 502 - {'detail': 'Backend returned 404: Not Found'}",
            response=mock_response,
            body={"detail": "Backend returned 404: Not Found"},
        )
    )

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoveryNonCompliant)


@pytest.mark.asyncio
async def test_query_available_models_502_other_detail_is_transient(reconciler, mock_models_sdk):
    """502 with detail other than 'Backend returned 404' is treated as transient."""
    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(
        side_effect=APIStatusError(
            "Error code: 502 - {'detail': 'Backend networking error: Connection refused'}",
            response=mock_response,
            body={"detail": "Backend networking error: Connection refused"},
        )
    )

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoveryTransientError)


@pytest.mark.asyncio
async def test_get_available_models_from_provider_empty_list(reconciler, mock_models_sdk):
    """Test provider with no models."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(return_value={"object": "list", "data": []})

    model_provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    result = await reconciler._discover_models(model_provider)

    assert isinstance(result, DiscoverySuccess)
    assert result.model_ids == []


# ============================================================================
# _entity_name_from_discovered_model Tests
# ============================================================================


def test_entity_name_from_discovered_model_strips_same_workspace_prefix():
    """When model_id is workspace/name, strip prefix and normalize only the name part."""
    assert _entity_name_from_discovered_model("e2e-27cb499c/qwen-2-5-1-5b", "e2e-27cb499c") == "qwen-2-5-1-5b"
    assert _entity_name_from_discovered_model("test-ns/my-model", "test-ns") == "my-model"


def test_entity_name_from_discovered_model_no_prefix_normalizes_whole_id():
    """When model_id has no provider-workspace prefix, normalize the whole id (existing behavior)."""
    assert _entity_name_from_discovered_model("meta/llama-3.2-1b-instruct", "other-ns") == "meta-llama-3-2-1b-instruct"
    assert _entity_name_from_discovered_model("model:with:colons", "test-ns") == "model-with-colons"


def test_entity_name_from_discovered_model_different_workspace_prefix_normalizes_whole():
    """When model_id starts with a different workspace, do not strip; normalize whole id."""
    assert _entity_name_from_discovered_model("other-ns/qwen-2-5-1-5b", "test-ns") == "other-ns-qwen-2-5-1-5b"


def test_entity_name_from_discovered_model_invalid_raises():
    """When model_id normalizes to an invalid entity name, ValueError is raised."""
    # Single-character id still fails NAME_PATTERN's 2-char minimum length.
    with pytest.raises(ValueError, match="not valid"):
        _entity_name_from_discovered_model("a", "test-ns")


def test_entity_name_from_discovered_model_digit_leading_gets_prefix():
    """Digit-leading upstream ids (e.g. NVIDIA Build's '01-ai/yi-large') get an
    internal 'm-' prefix from normalize_model_entity_name and become routable."""
    assert _entity_name_from_discovered_model("01-ai/yi-large", "default") == "m-01-ai-yi-large"
    assert _entity_name_from_discovered_model("123", "test-ns") == "m-123"


# ============================================================================
# _get_artifact_details Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_artifact_details_external_provider(reconciler):
    """Test getting artifact details for external provider."""
    provider = MagicMock()
    provider.host_url = "https://external-api.com"

    with patch("nmp.core.models.controllers.provider_reconciler.get_model_weights_type") as mock_get_location:
        from nmp.core.models.app import ModelWeightsType

        mock_get_location.return_value = ModelWeightsType.EXTERNAL_PROVIDER

        details = await reconciler._build_artifact_details(
            model_name="test-model",
            provider_id="test-ns/test-provider",
            provider=provider,
            model_entity=None,
            deployment=None,
            config=None,
        )

    assert details.fileset_url is None
    assert details.api_endpoint == {
        "url": "https://external-api.com",
        "model_id": "test-model",
        "format": "openai",
    }


@pytest.mark.asyncio
async def test_get_artifact_details_huggingface(reconciler):
    """Test getting artifact details for HuggingFace model."""
    provider = MagicMock()
    config = MagicMock()
    config.nim_deployment.model_namespace = "meta"
    config.nim_deployment.model_name = "llama-3.1-8b-instruct"
    config.nim_deployment.model_revision = "v1.0"

    with patch("nmp.core.models.controllers.provider_reconciler.get_model_weights_type") as mock_get_location:
        from nmp.core.models.app import ModelWeightsType

        mock_get_location.return_value = ModelWeightsType.HUGGINGFACE

        details = await reconciler._build_artifact_details(
            model_name="test-model",
            provider_id="test-ns/test-provider",
            provider=provider,
            model_entity=None,
            deployment=None,
            config=config,
        )

    assert details.api_endpoint is None
    assert details.fileset_url == "hf://meta/llama-3.1-8b-instruct@v1.0"


@pytest.mark.asyncio
async def test_get_artifact_details_huggingface_no_revision(reconciler):
    """Test getting artifact details for HuggingFace model without revision."""
    provider = MagicMock()
    config = MagicMock()
    config.nim_deployment.model_namespace = "meta"
    config.nim_deployment.model_name = "llama-3.1-8b-instruct"
    config.nim_deployment.model_revision = None

    with patch("nmp.core.models.controllers.provider_reconciler.get_model_weights_type") as mock_get_location:
        from nmp.core.models.app import ModelWeightsType

        mock_get_location.return_value = ModelWeightsType.HUGGINGFACE

        details = await reconciler._build_artifact_details(
            model_name="test-model",
            provider_id="test-ns/test-provider",
            provider=provider,
            model_entity=None,
            deployment=None,
            config=config,
        )

    assert details.fileset_url == "hf://meta/llama-3.1-8b-instruct"


@pytest.mark.asyncio
async def test_get_artifact_details_files_service(reconciler):
    """Test getting artifact details for Files service model."""
    provider = MagicMock()
    config = MagicMock()
    config.nim_deployment.model_namespace = "test-org"
    config.nim_deployment.model_name = "custom-model"
    config.nim_deployment.model_revision = "v2.1"

    with patch("nmp.core.models.controllers.provider_reconciler.get_model_weights_type") as mock_get_location:
        from nmp.core.models.app import ModelWeightsType

        mock_get_location.return_value = ModelWeightsType.FILES_SERVICE

        details = await reconciler._build_artifact_details(
            model_name="test-model",
            provider_id="test-ns/test-provider",
            provider=provider,
            model_entity=None,
            deployment=None,
            config=config,
        )

    assert details.api_endpoint is None
    assert details.fileset_url == "hf://test-org/custom-model@v2.1"


@pytest.mark.asyncio
async def test_get_artifact_details_handles_exception(reconciler):
    """Test handling exceptions gracefully in _get_artifact_details."""
    provider = MagicMock()

    with patch("nmp.core.models.controllers.provider_reconciler.get_model_weights_type") as mock_get_location:
        mock_get_location.side_effect = Exception("Unexpected error")

        details = await reconciler._build_artifact_details(
            model_name="test-model",
            provider_id="test-ns/test-provider",
            provider=provider,
            model_entity=None,
            deployment=None,
            config=None,
        )

    # Should return empty ArtifactDetails on error
    assert details.fileset_url is None
    assert details.api_endpoint is None


# ============================================================================
# _ensure_model_entity_for_provider Tests
# ============================================================================


@pytest.mark.asyncio
async def test_ensure_model_entity_creates_new_entity(reconciler):
    """Test creating a new model entity when it doesn't exist."""
    # Mock entity doesn't exist
    reconciler._models_sdk.models.retrieve = AsyncMock(
        side_effect=NotFoundError("Not found", response=MagicMock(), body=None)
    )
    reconciler._models_sdk.models.create = AsyncMock()

    # Mock context
    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(
        reconciler, "_build_artifact_details", return_value=ArtifactDetails(fileset_url="hf://test/model")
    ):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    # Verify entity creation was called
    reconciler._models_sdk.models.create.assert_called_once_with(
        workspace="test-ns",
        name="test-model",
        description="Auto-discovered model from provider test-ns/test-provider",
        model_providers=["test-ns/test-provider"],
        backend_format="OPENAI_CHAT",
        fileset="test/model",
    )


@pytest.mark.asyncio
async def test_ensure_model_entity_updates_existing_adds_provider(reconciler):
    """Test updating existing entity to add provider to model_providers list."""
    # Mock existing entity
    existing_entity = MagicMock()
    existing_entity.model_providers = ["other-ns/other-provider"]
    existing_entity.fileset = None
    existing_entity.api_endpoint = None

    reconciler._models_sdk.models.retrieve = AsyncMock(return_value=existing_entity)
    reconciler._models_sdk.models.update = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(reconciler, "_build_artifact_details", return_value=ArtifactDetails()):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    # Verify update was called to add provider
    reconciler._models_sdk.models.update.assert_called_once_with(
        name="test-model",
        workspace="test-ns",
        model_providers=["other-ns/other-provider", "test-ns/test-provider"],
        backend_format="OPENAI_CHAT",
    )


@pytest.mark.asyncio
async def test_ensure_model_entity_skips_if_provider_already_linked(reconciler):
    """Test skipping update when provider is already linked to entity."""
    # Mock existing entity with provider already in list
    existing_entity = MagicMock()
    existing_entity.model_providers = ["test-ns/test-provider", "other-ns/other-provider"]
    existing_entity.backend_format = "OPENAI_CHAT"

    reconciler._models_sdk.models.retrieve = AsyncMock(return_value=existing_entity)
    reconciler._models_sdk.models.update = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(reconciler, "_build_artifact_details", return_value=ArtifactDetails()):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    # Verify update was NOT called
    reconciler._models_sdk.models.update.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_model_entity_backfills_missing_backend_format(reconciler):
    """Test setting backend_format when the provider is already linked but the field is empty."""
    existing_entity = MagicMock()
    existing_entity.model_providers = ["test-ns/test-provider"]
    existing_entity.fileset = None
    existing_entity.api_endpoint = None
    existing_entity.backend_format = None

    reconciler._models_sdk.models.retrieve = AsyncMock(return_value=existing_entity)
    reconciler._models_sdk.models.update = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(reconciler, "_build_artifact_details", return_value=ArtifactDetails()):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="anthropic.claude-3-5-sonnet",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    reconciler._models_sdk.models.update.assert_called_once_with(
        name="anthropic.claude-3-5-sonnet",
        workspace="test-ns",
        backend_format="ANTHROPIC_MESSAGES",
    )


@pytest.mark.asyncio
async def test_ensure_model_entity_adds_artifact_to_existing_without_artifact(reconciler):
    """Test adding artifact to existing entity that doesn't have one."""
    # Mock existing entity without artifact
    existing_entity = MagicMock()
    existing_entity.model_providers = ["other-ns/other-provider"]
    existing_entity.fileset = None
    existing_entity.api_endpoint = None

    reconciler._models_sdk.models.retrieve = AsyncMock(return_value=existing_entity)
    reconciler._models_sdk.models.update = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(
        reconciler, "_build_artifact_details", return_value=ArtifactDetails(fileset_url="hf://test/model")
    ):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    # Verify update includes artifact
    reconciler._models_sdk.models.update.assert_called_once_with(
        name="test-model",
        workspace="test-ns",
        model_providers=["other-ns/other-provider", "test-ns/test-provider"],
        backend_format="OPENAI_CHAT",
        fileset="test/model",
    )


@pytest.mark.asyncio
async def test_ensure_model_entity_doesnt_overwrite_existing_artifact(reconciler):
    """Test not overwriting artifact if entity already has one."""
    # Mock existing entity with artifact
    existing_entity = MagicMock()
    existing_entity.model_providers = []
    existing_entity.fileset = "existing://artifact"
    existing_entity.api_endpoint = None

    reconciler._models_sdk.models.retrieve = AsyncMock(return_value=existing_entity)
    reconciler._models_sdk.models.update = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(
        reconciler, "_build_artifact_details", return_value=ArtifactDetails(fileset_url="hf://test/model")
    ):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    # Verify update does NOT include fileset (since it already exists)
    call_kwargs = reconciler._models_sdk.models.update.call_args.kwargs
    assert "fileset" not in call_kwargs


@pytest.mark.asyncio
async def test_ensure_model_entity_doesnt_overwrite_existing_backend_format(reconciler):
    """Test not overwriting backend_format if the user already corrected it."""
    existing_entity = MagicMock()
    existing_entity.model_providers = []
    existing_entity.fileset = None
    existing_entity.api_endpoint = None
    existing_entity.backend_format = "ANTHROPIC_MESSAGES"

    reconciler._models_sdk.models.retrieve = AsyncMock(return_value=existing_entity)
    reconciler._models_sdk.models.update = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(reconciler, "_build_artifact_details", return_value=ArtifactDetails()):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    call_kwargs = reconciler._models_sdk.models.update.call_args.kwargs
    assert "backend_format" not in call_kwargs


@pytest.mark.asyncio
async def test_ensure_model_entity_handles_null_model_providers(reconciler):
    """Test handling entity with None model_providers."""
    # Mock existing entity with None model_providers
    existing_entity = MagicMock()
    existing_entity.model_providers = None
    existing_entity.fileset = None
    existing_entity.api_endpoint = None

    reconciler._models_sdk.models.retrieve = AsyncMock(return_value=existing_entity)
    reconciler._models_sdk.models.update = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(reconciler, "_build_artifact_details", return_value=ArtifactDetails()):
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    # Verify update was called with provider as first in list
    reconciler._models_sdk.models.update.assert_called_once_with(
        name="test-model",
        workspace="test-ns",
        model_providers=["test-ns/test-provider"],
        backend_format="OPENAI_CHAT",
    )


@pytest.mark.asyncio
async def test_ensure_model_entity_handles_create_exception(reconciler):
    """Test handling exception during entity creation."""
    reconciler._models_sdk.models.retrieve = AsyncMock(
        side_effect=NotFoundError("Not found", response=MagicMock(), body=None)
    )
    reconciler._models_sdk.models.create = AsyncMock(side_effect=Exception("Creation failed"))

    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(reconciler, "_build_artifact_details", return_value=ArtifactDetails()):
        # Should not raise exception
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )


@pytest.mark.asyncio
async def test_ensure_model_entity_handles_retrieve_non_not_found_exception(reconciler):
    """Retrieve failures other than NotFound must not propagate; skip create/update until next loop."""
    mock_response = MagicMock()
    mock_response.status_code = 503
    reconciler._models_sdk.models.retrieve = AsyncMock(
        side_effect=APIStatusError(
            "Service unavailable",
            response=mock_response,
            body={"detail": "upstream error"},
        )
    )
    reconciler._models_sdk.models.create = AsyncMock()

    ctx = ModelContext(
        model_provider=MagicMock(host_url="https://api.com"),
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    with patch.object(reconciler, "_build_artifact_details", return_value=ArtifactDetails()) as mock_compile:
        await reconciler._ensure_model_entity_for_provider(
            model_workspace="test-ns",
            model_name="test-model",
            provider_id="test-ns/test-provider",
            ctx=ctx,
        )

    mock_compile.assert_not_called()
    reconciler._models_sdk.models.create.assert_not_called()


# ============================================================================
# update_model_providers Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_model_providers_success(reconciler):
    """Test successful provider update flow."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-1", "model-2"])),
    ) as mock_get_models:
        with patch.object(reconciler, "_ensure_model_entity_for_provider", return_value=None) as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Verify models were discovered
    mock_get_models.assert_called_once()

    # Verify entities were ensured for both models
    assert mock_ensure.call_count == 2

    # Verify provider was updated with served models
    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["name"] == "test-provider"
    assert call_kwargs["workspace"] == "test-ns"
    assert call_kwargs["status"] == "READY"
    assert len(call_kwargs["served_models"]) == 2


@pytest.mark.asyncio
async def test_update_model_providers_filters_by_enabled_models(reconciler):
    """Test filtering discovered models by enabled_models."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = ["model-1", "model-3"]  # Filter to only these
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-1", "model-2", "model-3"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Verify only enabled models were initialized
    assert mock_ensure.call_count == 2
    ensured_models = {call.kwargs["model_name"] for call in mock_ensure.call_args_list}
    assert ensured_models == {"model-1", "model-3"}


@pytest.mark.asyncio
async def test_ensure_external_entities_retries_after_transient_entity_failure(reconciler):
    """Tests that ``_ensure_model_entity_for_provider`` is called for every valid discovered model.

    Previously, ``_ensure_external_entities`` gated retries on the provider's current
    ``served_models``. That list gets published unconditionally by
    ``_reconcile_single_provider`` even when ``_ensure_model_entity_for_provider``
    swallowed a transient failure, which meant the served_model_name was treated as
    "existing" forever and the ModelEntity was never created. This test simulates
    cycle 1 (entity retrieve fails transiently, mapping still gets published) and
    cycle 2 (entity retrieve should be attempted again, not skipped).
    """
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.host_url = "https://example.com/v1"
    provider.model_deployment_id = None
    provider.enabled_models = None
    # Cycle 2 precondition: cycle 1 already published the mapping even though the
    # entity failed to initialize — exactly the stale state the old gating logic
    # produced.
    provider.served_models = [
        ServedModelMapping(model_entity_id="test-ns/model-1", served_model_name="model-1"),
    ]

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-1"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # With the fix, ensure is called for model-1 despite being in served_models —
    # giving the controller a chance to recover from last cycle's failure.
    mock_ensure.assert_called_once()
    assert mock_ensure.call_args.kwargs["model_name"] == "model-1"


@pytest.mark.asyncio
async def test_update_model_providers_removes_no_longer_served_models(reconciler):
    """Test that models no longer served are removed from served_models."""
    # Provider previously served model-1, model-2, model-3
    existing_served_models = [
        ServedModelMapping(model_entity_id="test-ns/model-1", served_model_name="model-1"),
        ServedModelMapping(model_entity_id="test-ns/model-2", served_model_name="model-2"),
        ServedModelMapping(model_entity_id="test-ns/model-3", served_model_name="model-3"),
    ]

    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = existing_served_models

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    # Now only serving model-1 and model-2 (model-3 removed)
    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-1", "model-2"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            await reconciler.reconcile_model_providers([ctx])

    # Verify only model-1 and model-2 are in final served_models
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    served_model_names = {m.served_model_name for m in call_kwargs["served_models"]}
    assert served_model_names == {"model-1", "model-2"}


@pytest.mark.asyncio
async def test_update_model_providers_handles_non_compliant_provider(reconciler):
    """Test handling non-OpenAI compliant provider."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    # Provider returns DiscoveryNonCompliant (confirmed non-compliant)
    with patch.object(reconciler, "_discover_models", return_value=DiscoveryNonCompliant()):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Verify no entities were initialized
    mock_ensure.assert_not_called()

    # Verify provider was updated with empty served_models and appropriate message
    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["served_models"] == []
    assert call_kwargs["status"] == "READY"
    assert "Non-OpenAI compliant" in call_kwargs["status_message"]


@pytest.mark.asyncio
async def test_update_model_providers_handles_update_exception(reconciler):
    """Test handling exception during provider update."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock(side_effect=Exception("Update failed"))

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-1"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            # Should not raise exception
            await reconciler.reconcile_model_providers([ctx])


@pytest.mark.asyncio
async def test_update_model_providers_normalizes_model_names(reconciler):
    """Test that model names are normalized for entity IDs but kept original for served_model_name."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    # Model with special characters that need normalization
    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model:with:colons"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Verify entity was ensured with normalized name (colons become hyphens)
    mock_ensure.assert_called_once()
    assert "model-with-colons" in str(mock_ensure.call_args)  # Normalized

    # Verify served_models keeps original name
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    served_models = call_kwargs["served_models"]
    assert len(served_models) == 1
    assert served_models[0].served_model_name == "model:with:colons"  # Original
    assert "model-with-colons" in served_models[0].model_entity_id  # Normalized


@pytest.mark.asyncio
async def test_update_model_providers_strips_same_workspace_prefix_from_model_id(reconciler):
    """When backend reports workspace/name (e.g. e2e-27cb499c/qwen-2-5-1-5b), use name only for entity ID."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    # Backend reports model id as workspace/name (e.g. NIM_SERVED_MODEL_NAME set to workspace/name)
    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["test-ns/qwen-2-5-1-5b"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Entity name should be the name part only, not test-ns-qwen-2-5-1-5b
    mock_ensure.assert_called_once()
    call_kwargs = mock_ensure.call_args.kwargs
    assert call_kwargs["model_name"] == "qwen-2-5-1-5b"

    # served_models should have model_entity_id = workspace/name (no duplicate prefix in name)
    update_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    served_models = update_kwargs["served_models"]
    assert len(served_models) == 1
    assert served_models[0].model_entity_id == "test-ns/qwen-2-5-1-5b"
    assert served_models[0].served_model_name == "test-ns/qwen-2-5-1-5b"


@pytest.mark.asyncio
async def test_update_model_providers_with_empty_discovery(reconciler):
    """Test provider that discovers no models."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids([])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Verify no entities were initialized
    mock_ensure.assert_not_called()

    # Verify provider was updated with empty served_models
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["served_models"] == []
    assert call_kwargs["status"] == "READY"


@pytest.mark.asyncio
async def test_update_model_providers_multiple_providers(reconciler):
    """Test updating multiple providers."""
    provider1 = MagicMock()
    provider1.workspace = "ns1"
    provider1.name = "provider1"
    provider1.model_deployment_id = None
    provider1.enabled_models = None
    provider1.served_models = []

    provider2 = MagicMock()
    provider2.workspace = "ns2"
    provider2.name = "provider2"
    provider2.model_deployment_id = None
    provider2.enabled_models = None
    provider2.served_models = []

    ctx1 = ModelContext(model_provider=provider1)
    ctx2 = ModelContext(model_provider=provider2)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    async def get_models_side_effect(model_provider: ModelProvider):
        if model_provider.workspace == "ns1":
            return DiscoverySuccess(_discovery_models_from_ids(["model-1"]))
        return DiscoverySuccess(_discovery_models_from_ids(["model-2", "model-3"]))

    with patch.object(reconciler, "_discover_models", side_effect=get_models_side_effect) as mock_get_models:
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            await reconciler.reconcile_model_providers([ctx1, ctx2])

    # Verify both providers were processed
    assert mock_get_models.call_count == 2
    assert reconciler._models_sdk.inference.providers.update_status.call_count == 2


@pytest.mark.asyncio
async def test_reconcile_preserves_served_models_on_transient_error(reconciler):
    """Transient query failure must NOT call update_status — existing served_models are preserved."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.served_models = [
        ServedModelMapping(model_entity_id="test-ns/model-1", served_model_name="model-1"),
    ]

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(reconciler, "_discover_models", return_value=DiscoveryTransientError()):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Transient error must not trigger any status update — served_models are preserved implicitly
    reconciler._models_sdk.inference.providers.update_status.assert_not_called()
    mock_ensure.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_preserves_served_models_when_deployment_base_id_unresolvable(reconciler, caplog):
    """Deployment-backed provider with an unresolvable base_id must NOT wipe served_models."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = "dep-1"
    provider.enabled_models = None
    provider.served_models = [
        ServedModelMapping(model_entity_id="test-ns/base", served_model_name="test-ns/base"),
    ]
    provider.status = ModelProviderStatus.READY

    # Both config and entity missing => _resolve_base_backend_model_id returns None.
    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with (
        patch.object(reconciler, "_discover_models", return_value=DiscoverySuccess([{"id": "test-ns/base"}])),
        patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure,
        caplog.at_level("WARNING"),
    ):
        await reconciler.reconcile_model_providers([ctx])

    reconciler._models_sdk.inference.providers.update_status.assert_not_called()
    mock_ensure.assert_not_called()
    # WARNING must surface the provider id so operators can correlate with
    # downstream "model not found" reports during a flaky prefetch tick.
    assert any("test-ns/test-provider" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records), (
        "expected WARNING mentioning provider id; got: "
        + "; ".join(f"[{r.levelname}] {r.getMessage()}" for r in caplog.records)
    )


@pytest.mark.asyncio
async def test_reconcile_clears_served_models_on_confirmed_non_compliant(reconciler):
    """Confirmed non-compliant (valid HTTP, wrong format) must clear served_models."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.served_models = [
        ServedModelMapping(model_entity_id="test-ns/model-1", served_model_name="model-1"),
    ]

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(reconciler, "_discover_models", return_value=DiscoveryNonCompliant()):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    # Non-compliant must clear served_models
    mock_ensure.assert_not_called()
    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["served_models"] == []
    assert call_kwargs["status"] == "READY"
    assert "Non-OpenAI compliant" in call_kwargs["status_message"]


@pytest.mark.asyncio
async def test_reconcile_prunes_invalid_served_model_entity_ids_before_update_status(reconciler):
    """If a generator emits a malformed model_entity_id, the final gate drops it with a warning.

    We stub ``_generate_external_served_model_mappings`` to emit one valid and one malformed
    entry and verify only the valid one reaches ``update_status``. This keeps IGW from being
    handed an id that would 422 on every subsequent proxy call.
    """
    provider = MagicMock()
    provider.workspace = "ws"
    provider.name = "p"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []
    provider.status = ModelProviderStatus.READY

    ctx = ModelContext(model_provider=provider, model_deployment=None, model_deployment_config=None, model_entity=None)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    bad = ServedModelMapping(model_entity_id="ws/Bad.Name", served_model_name="Bad.Name")
    good = ServedModelMapping(model_entity_id="ws/model-a", served_model_name="model-a")

    with (
        patch.object(reconciler, "_discover_models", return_value=DiscoverySuccess([{"id": "model-a"}])),
        patch.object(reconciler, "_ensure_external_entities", new=AsyncMock(return_value=None)),
        patch.object(
            reconciler,
            "_generate_external_served_model_mappings",
            return_value=[good, bad],
        ),
    ):
        await reconciler.reconcile_model_providers([ctx])

    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    emitted = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs["served_models"]
    assert [m.model_entity_id for m in emitted] == ["ws/model-a"]
    # Passthrough VirtualModel is attempted only for the surviving (non-LoRA) mapping.
    created_names = {
        call.kwargs["name"] for call in reconciler._models_sdk.inference.virtual_models.create.call_args_list
    }
    assert created_names == {"model-a"}


@pytest.mark.asyncio
async def test_reconcile_keeps_valid_lora_composite_through_gate(reconciler):
    """LoRA composite ids must survive the final gate — they're a documented valid shape."""
    provider = MagicMock()
    provider.workspace = "ws"
    provider.name = "p"
    provider.model_deployment_id = "dep-1"
    provider.enabled_models = None
    provider.served_models = []
    provider.status = ModelProviderStatus.READY

    config = MagicMock()
    config.model_entity_id = "ws/base"
    config.nim_deployment = MagicMock(model_namespace="ws", model_name="base", model_revision=None)

    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(
            [
                {"id": "ws/base", "root": "ws/base", "parent": None},
                {"id": "lora-1", "root": "/scratch/x", "parent": "ws/base"},
            ]
        ),
    ):
        await reconciler.reconcile_model_providers([ctx])

    emitted = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs["served_models"]
    eids = {m.model_entity_id for m in emitted}
    assert eids == {"ws/base", "ws/base&adapters/ws/lora-1"}
    # Only the base entity gets a passthrough VirtualModel; LoRA is skipped by design.
    created_names = {
        call.kwargs["name"] for call in reconciler._models_sdk.inference.virtual_models.create.call_args_list
    }
    assert created_names == {"base"}


# ============================================================================
# Per-provider exception isolation
# ============================================================================


@pytest.fixture
def _make_provider():
    """Factory for ModelProvider with explicit status and timestamps."""

    def _factory(
        name="test-provider",
        workspace="test-ns",
        status=ModelProviderStatus.CREATED,
        created_at=None,
        updated_at=None,
        served_models=None,
    ):
        now = datetime.now(timezone.utc)
        return ModelProvider(
            name=name,
            workspace=workspace,
            host_url="https://test-provider.com",
            status=status,
            created_at=created_at or now,
            updated_at=updated_at or now,
            served_models=served_models or [],
        )

    return _factory


@pytest.mark.asyncio
async def test_exception_in_one_provider_does_not_affect_others(reconciler):
    """An unexpected exception during one provider must not prevent processing of remaining providers."""
    good_provider = MagicMock()
    good_provider.workspace = "ns-good"
    good_provider.name = "good-provider"
    good_provider.model_deployment_id = None
    good_provider.enabled_models = None
    good_provider.served_models = []

    bad_provider = MagicMock()
    bad_provider.workspace = "ns-bad"
    bad_provider.name = "bad-provider"

    ctx_bad = ModelContext(model_provider=bad_provider)
    ctx_good = ModelContext(model_provider=good_provider)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    call_count = 0

    async def query_side_effect(provider):
        nonlocal call_count
        call_count += 1
        if provider.workspace == "ns-bad":
            raise RuntimeError("Unexpected failure in reconciliation")
        return DiscoverySuccess(_discovery_models_from_ids(["model-1"]))

    with patch.object(reconciler, "_discover_models", side_effect=query_side_effect):
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            # Must not raise even though bad_provider throws
            await reconciler.reconcile_model_providers([ctx_bad, ctx_good])

    # Both providers were attempted
    assert call_count == 2
    # Good provider was still updated successfully
    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["workspace"] == "ns-good"
    assert call_kwargs["status"] == "READY"


@pytest.mark.asyncio
async def test_reconcile_does_not_propagate_exception(reconciler):
    """reconcile_model_providers must never propagate exceptions to the controller step."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"

    ctx = ModelContext(model_provider=provider)

    with patch.object(reconciler, "_discover_models", side_effect=RuntimeError("kaboom")):
        # Must not raise
        await reconciler.reconcile_model_providers([ctx])


# ============================================================================
# Provider state machine: CREATED -> ERROR -> LOST
# ============================================================================


@pytest.mark.asyncio
async def test_created_provider_escalated_to_error_after_threshold(reconciler, _make_provider):
    """A CREATED provider with updated_at older than the error threshold should transition to ERROR."""
    stale = datetime.now(timezone.utc) - timedelta(seconds=PROVIDER_ERROR_THRESHOLD_SECONDS + 10)
    provider = _make_provider(status=ModelProviderStatus.CREATED, created_at=stale, updated_at=stale)
    ctx = ModelContext(model_provider=provider)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoveryTransientError("connection refused"),
    ):
        await reconciler.reconcile_model_providers([ctx])

    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["status"] == "ERROR"
    assert "connection refused" in call_kwargs["status_message"]


@pytest.mark.asyncio
async def test_created_provider_not_escalated_before_threshold(reconciler, _make_provider):
    """A freshly CREATED provider with transient errors should NOT escalate to ERROR yet."""
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    provider = _make_provider(status=ModelProviderStatus.CREATED, created_at=recent, updated_at=recent)
    ctx = ModelContext(model_provider=provider)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(reconciler, "_discover_models", return_value=DiscoveryTransientError()):
        await reconciler.reconcile_model_providers([ctx])

    # Should NOT update status — still within grace period
    reconciler._models_sdk.inference.providers.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_error_provider_skipped_within_retry_cooldown(reconciler, _make_provider):
    """An ERROR provider whose updated_at is within the retry cooldown should be skipped entirely."""
    now = datetime.now(timezone.utc)
    provider = _make_provider(
        status=ModelProviderStatus.ERROR,
        created_at=now - timedelta(seconds=120),
        updated_at=now - timedelta(seconds=10),
    )
    ctx = ModelContext(model_provider=provider)

    with patch.object(reconciler, "_discover_models") as mock_query:
        await reconciler.reconcile_model_providers([ctx])

    # Discovery should not even be attempted
    mock_query.assert_not_called()


@pytest.mark.asyncio
async def test_error_provider_retried_after_cooldown(reconciler, _make_provider):
    """An ERROR provider past its retry cooldown should attempt discovery and bump updated_at on failure."""
    now = datetime.now(timezone.utc)
    provider = _make_provider(
        status=ModelProviderStatus.ERROR,
        created_at=now - timedelta(seconds=300),
        updated_at=now - timedelta(seconds=PROVIDER_ERROR_RETRY_INTERVAL_SECONDS + 5),
    )
    ctx = ModelContext(model_provider=provider)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoveryTransientError("still down"),
    ):
        await reconciler.reconcile_model_providers([ctx])

    # Should update status to bump updated_at for next retry pacing
    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["status"] == "ERROR"
    assert "still down" in call_kwargs["status_message"]


@pytest.mark.asyncio
async def test_error_provider_transitions_to_lost(reconciler, _make_provider):
    """An ERROR provider whose created_at exceeds the LOST threshold should transition to LOST."""
    now = datetime.now(timezone.utc)
    provider = _make_provider(
        status=ModelProviderStatus.ERROR,
        created_at=now - timedelta(seconds=PROVIDER_LOST_THRESHOLD_SECONDS + 60),
        updated_at=now - timedelta(seconds=PROVIDER_ERROR_RETRY_INTERVAL_SECONDS + 5),
    )
    ctx = ModelContext(model_provider=provider)
    updated_provider = _make_provider(
        status=ModelProviderStatus.LOST,
        created_at=provider.created_at,
        updated_at=datetime.now(timezone.utc),
    )

    reconciler._models_sdk.inference.providers.update_status = AsyncMock(return_value=updated_provider)

    with patch.object(reconciler, "_discover_models") as mock_query:
        await reconciler.reconcile_model_providers([ctx])

    # Should transition to LOST without attempting discovery
    mock_query.assert_not_called()
    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["status"] == "LOST"
    assert "permanently failed" in call_kwargs["status_message"]
    assert ctx.model_provider is updated_provider


@pytest.mark.asyncio
async def test_error_provider_recovers_to_ready(reconciler, _make_provider):
    """An ERROR provider whose discovery succeeds should transition back to READY."""
    now = datetime.now(timezone.utc)
    provider = _make_provider(
        status=ModelProviderStatus.ERROR,
        created_at=now - timedelta(seconds=300),
        updated_at=now - timedelta(seconds=PROVIDER_ERROR_RETRY_INTERVAL_SECONDS + 5),
    )
    ctx = ModelContext(model_provider=provider)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-1"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            await reconciler.reconcile_model_providers([ctx])

    reconciler._models_sdk.inference.providers.update_status.assert_called_once()
    call_kwargs = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs
    assert call_kwargs["status"] == "READY"
    assert len(call_kwargs["served_models"]) == 1


@pytest.mark.asyncio
async def test_lost_provider_skipped_entirely(reconciler, _make_provider):
    """A LOST provider should be skipped entirely — no discovery, no status updates."""
    provider = _make_provider(status=ModelProviderStatus.LOST)
    ctx = ModelContext(model_provider=provider)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(reconciler, "_discover_models") as mock_query:
        await reconciler.reconcile_model_providers([ctx])

    mock_query.assert_not_called()
    reconciler._models_sdk.inference.providers.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_ready_provider_preserves_served_models_on_transient_error(reconciler, _make_provider):
    """A READY provider with transient errors should keep its served_models and stay READY."""
    now = datetime.now(timezone.utc)
    provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        status=ModelProviderStatus.READY,
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(minutes=5),
        served_models=[
            ServedModelMapping(model_entity_id="test-ns/model-1", served_model_name="model-1"),
        ],
    )
    ctx = ModelContext(model_provider=provider)

    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(reconciler, "_discover_models", return_value=DiscoveryTransientError()):
        await reconciler.reconcile_model_providers([ctx])

    # Should NOT update status — existing served_models preserved
    reconciler._models_sdk.inference.providers.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_transient_error_carries_message(reconciler, mock_models_sdk):
    """DiscoveryTransientError should carry the error message from the gateway."""
    mock_models_sdk.inference.gateway.provider.get = AsyncMock(side_effect=Exception("Connection refused"))

    provider = ModelProvider(
        name="test-provider",
        workspace="test-ns",
        host_url="https://test-provider.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    result = await reconciler._discover_models(provider)

    assert isinstance(result, DiscoveryTransientError)
    assert "Connection refused" in result.message


# ============================================================================
# _ensure_passthrough_virtual_model Tests
# ============================================================================


@pytest.mark.asyncio
async def test_ensure_passthrough_virtual_model_creates_when_not_exists(reconciler, mock_models_sdk):
    """Creates a passthrough VirtualModel with the correct arguments."""
    await reconciler._ensure_passthrough_virtual_model("my-ws", "llama-3b")

    mock_models_sdk.inference.virtual_models.create.assert_awaited_once_with(
        workspace="my-ws",
        name="llama-3b",
        default_model_entity="my-ws/llama-3b",
        autoprovisioned=True,
    )


@pytest.mark.asyncio
async def test_ensure_passthrough_virtual_model_ignores_conflict_error(reconciler, mock_models_sdk):
    """ConflictError (409) means the VirtualModel already exists — must not propagate."""
    mock_response = MagicMock()
    mock_response.status_code = 409
    mock_models_sdk.inference.virtual_models.create = AsyncMock(
        side_effect=ConflictError("Conflict", response=mock_response, body={})
    )

    # Should not raise
    await reconciler._ensure_passthrough_virtual_model("my-ws", "llama-3b")


@pytest.mark.asyncio
async def test_ensure_passthrough_virtual_model_logs_warning_on_unexpected_error(reconciler, mock_models_sdk, caplog):
    """Unexpected exceptions are logged as warnings and must not propagate."""
    import logging

    mock_models_sdk.inference.virtual_models.create = AsyncMock(side_effect=RuntimeError("network timeout"))

    with caplog.at_level(logging.WARNING):
        # Should not raise
        await reconciler._ensure_passthrough_virtual_model("my-ws", "llama-3b")

    assert any("my-ws" in r.message and "llama-3b" in r.message for r in caplog.records)


# ============================================================================
# VirtualModel creation in reconcile_model_providers Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reconcile_creates_passthrough_virtual_models_for_all_served_models(reconciler, mock_models_sdk):
    """A passthrough VirtualModel is created for every model in the final served_models list."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    mock_models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-a", "model-b"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            await reconciler.reconcile_model_providers([ctx])

    assert mock_models_sdk.inference.virtual_models.create.await_count == 2
    created_names = {call.kwargs["name"] for call in mock_models_sdk.inference.virtual_models.create.call_args_list}
    assert created_names == {"model-a", "model-b"}
    for call in mock_models_sdk.inference.virtual_models.create.call_args_list:
        assert call.kwargs["default_model_entity"] == f"test-ns/{call.kwargs['name']}"
        assert call.kwargs["workspace"] == "test-ns"
        assert call.kwargs["autoprovisioned"] is True


# ============================================================================
# Autoprovisioned VirtualModel cleanup Tests
# ============================================================================


def _virtual_model(
    name: str,
    *,
    workspace: str = "ws",
    default_model_entity: str | None = None,
    autoprovisioned: bool = True,
):
    vm = MagicMock()
    vm.name = name
    vm.workspace = workspace
    vm.default_model_entity = default_model_entity
    vm.autoprovisioned = autoprovisioned
    return vm


def _provider_context(
    *,
    workspace: str = "ws",
    status: ModelProviderStatus = ModelProviderStatus.READY,
    served_models: list[ServedModelMapping] | None = None,
) -> ModelContext:
    provider = MagicMock()
    provider.workspace = workspace
    provider.name = "provider"
    provider.status = status
    provider.served_models = served_models or []
    return ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )


@pytest.mark.asyncio
async def test_reconcile_with_no_providers_deletes_orphaned_autoprovisioned_virtual_model(reconciler, mock_models_sdk):
    """When the last provider is gone, the final cleanup pass deletes its autoprovisioned VM."""
    mock_models_sdk.inference.virtual_models.list = MagicMock(
        return_value=_AsyncPaginator(
            [
                _virtual_model(
                    "model-a",
                    default_model_entity="ws/model-a",
                    autoprovisioned=True,
                )
            ]
        )
    )

    await reconciler.reconcile_model_providers([])

    mock_models_sdk.inference.virtual_models.list.assert_called_once_with(workspace="-", page_size=200)
    mock_models_sdk.inference.virtual_models.delete.assert_awaited_once_with(name="model-a", workspace="ws")


@pytest.mark.asyncio
async def test_cleanup_keeps_autoprovisioned_virtual_model_served_by_remaining_provider(reconciler, mock_models_sdk):
    """A VM survives while at least one non-LOST provider still serves its model entity."""
    ctx = _provider_context(
        served_models=[
            ServedModelMapping(model_entity_id="ws/model-a", served_model_name="model-a"),
        ]
    )
    mock_models_sdk.inference.virtual_models.list = MagicMock(
        return_value=_AsyncPaginator(
            [
                _virtual_model(
                    "model-a",
                    default_model_entity="ws/model-a",
                    autoprovisioned=True,
                )
            ]
        )
    )

    await reconciler._cleanup_orphaned_virtual_models([ctx])

    mock_models_sdk.inference.virtual_models.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_keeps_autoprovisioned_virtual_model_without_default_model_entity(reconciler, mock_models_sdk):
    """An adopted/customized autoprovisioned VM without a default route is not an orphan mismatch."""
    mock_models_sdk.inference.virtual_models.list = MagicMock(
        return_value=_AsyncPaginator(
            [
                _virtual_model(
                    "model-a",
                    default_model_entity=None,
                    autoprovisioned=True,
                )
            ]
        )
    )

    await reconciler._cleanup_orphaned_virtual_models([])

    mock_models_sdk.inference.virtual_models.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_lost_provider_does_not_protect_autoprovisioned_virtual_model(reconciler, mock_models_sdk):
    """LOST providers retain served_models in storage, but those mappings are ignored for cleanup."""
    ctx = _provider_context(
        status=ModelProviderStatus.LOST,
        served_models=[
            ServedModelMapping(model_entity_id="ws/model-a", served_model_name="model-a"),
        ],
    )
    mock_models_sdk.inference.virtual_models.list = MagicMock(
        return_value=_AsyncPaginator(
            [
                _virtual_model(
                    "model-a",
                    default_model_entity="ws/model-a",
                    autoprovisioned=True,
                )
            ]
        )
    )

    await reconciler._cleanup_orphaned_virtual_models([ctx])

    mock_models_sdk.inference.virtual_models.delete.assert_awaited_once_with(name="model-a", workspace="ws")


@pytest.mark.asyncio
async def test_cleanup_never_deletes_user_created_virtual_model(reconciler, mock_models_sdk):
    """Only autoprovisioned VirtualModels are eligible for orphan cleanup."""
    mock_models_sdk.inference.virtual_models.list = MagicMock(
        return_value=_AsyncPaginator(
            [
                _virtual_model(
                    "model-a",
                    default_model_entity="ws/model-a",
                    autoprovisioned=False,
                )
            ]
        )
    )

    await reconciler._cleanup_orphaned_virtual_models([])

    mock_models_sdk.inference.virtual_models.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_delete_failure_is_logged_and_non_fatal(reconciler, mock_models_sdk, caplog):
    """Delete failures are swallowed so the next reconcile cycle can retry."""
    import logging

    mock_models_sdk.inference.virtual_models.list = MagicMock(
        return_value=_AsyncPaginator(
            [
                _virtual_model(
                    "model-a",
                    default_model_entity="ws/model-a",
                    autoprovisioned=True,
                )
            ]
        )
    )
    mock_models_sdk.inference.virtual_models.delete = AsyncMock(side_effect=RuntimeError("delete failed"))

    with caplog.at_level(logging.WARNING):
        await reconciler._cleanup_orphaned_virtual_models([])

    mock_models_sdk.inference.virtual_models.delete.assert_awaited_once_with(name="model-a", workspace="ws")
    assert any("Failed to delete orphaned autoprovisioned VirtualModel ws/model-a" in r.message for r in caplog.records)


# =============================================================================
# Deployment-backed provider tests (no autocreate, served_models from id/root/parent)
# =============================================================================


@pytest.mark.asyncio
async def test_deployment_backed_never_calls_ensure_model_entity(reconciler, mock_models_sdk):
    """When model_deployment_id is set, _ensure_model_entity_for_provider is never called."""
    config = MagicMock()
    config.model_entity_id = "ws/base-entity"
    provider = MagicMock()
    provider.workspace = "ws"
    provider.name = "deploy-provider"
    provider.model_deployment_id = "ws/my-deployment"
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=MagicMock(),
        model_deployment_config=config,
        model_entity=None,
    )

    mock_models_sdk.inference.providers.update_status = AsyncMock()

    discovered = [
        {"id": "ws/base-entity", "root": "ws/base-entity", "parent": None},
        {"id": "adapter-1", "root": "/scratch/loras/adapter-1", "parent": "ws/base-entity"},
    ]
    with patch.object(reconciler, "_discover_models", return_value=DiscoverySuccess(discovered)):
        with patch.object(reconciler, "_ensure_model_entity_for_provider") as mock_ensure:
            await reconciler.reconcile_model_providers([ctx])

    mock_ensure.assert_not_called()
    call_kwargs = mock_models_sdk.inference.providers.update_status.call_args.kwargs
    assert len(call_kwargs["served_models"]) == 2


@pytest.mark.asyncio
async def test_reconcile_creates_virtual_models_for_previously_served_models(reconciler, mock_models_sdk):
    """Back-fill: VirtualModels are created even for models already in served_models before this feature."""
    existing_served = [
        ServedModelMapping(model_entity_id="test-ns/old-model", served_model_name="old-model"),
    ]

    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = existing_served

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    mock_models_sdk.inference.providers.update_status = AsyncMock()

    # Discover old-model (already served) and new-model (new)
    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["old-model", "new-model"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            await reconciler.reconcile_model_providers([ctx])

    # Both models (old + new) get a VirtualModel create attempt
    assert mock_models_sdk.inference.virtual_models.create.await_count == 2
    created_names = {call.kwargs["name"] for call in mock_models_sdk.inference.virtual_models.create.call_args_list}
    assert created_names == {"old-model", "new-model"}


@pytest.mark.asyncio
async def test_reconcile_does_not_create_virtual_models_for_non_compliant_provider(reconciler, mock_models_sdk):
    """DiscoveryNonCompliant results in served_models=[] — no VirtualModels created."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    mock_models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(reconciler, "_discover_models", return_value=DiscoveryNonCompliant()):
        await reconciler.reconcile_model_providers([ctx])

    mock_models_sdk.inference.virtual_models.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_creates_virtual_models_even_when_update_status_fails(reconciler, mock_models_sdk):
    """VirtualModel creation runs regardless of whether update_status raises."""
    provider = MagicMock()
    provider.workspace = "test-ns"
    provider.name = "test-provider"
    provider.model_deployment_id = None
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=None,
        model_deployment_config=None,
        model_entity=None,
    )

    # update_status raises — VirtualModel creation must still run
    mock_models_sdk.inference.providers.update_status = AsyncMock(side_effect=Exception("service unavailable"))
    mock_models_sdk.inference.virtual_models.list = MagicMock(
        return_value=_AsyncPaginator(
            [
                _virtual_model(
                    "model-x",
                    workspace="test-ns",
                    default_model_entity="test-ns/model-x",
                    autoprovisioned=True,
                )
            ]
        )
    )

    with patch.object(
        reconciler,
        "_discover_models",
        return_value=DiscoverySuccess(_discovery_models_from_ids(["model-x"])),
    ):
        with patch.object(reconciler, "_ensure_model_entity_for_provider"):
            await reconciler.reconcile_model_providers([ctx])

    mock_models_sdk.inference.virtual_models.create.assert_awaited_once_with(
        workspace="test-ns",
        name="model-x",
        default_model_entity="test-ns/model-x",
        autoprovisioned=True,
    )
    mock_models_sdk.inference.virtual_models.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_deployment_backed_served_models_base_lora_prompt_tuned(reconciler):
    """Deployment-backed provider builds served_models with base, LoRA (&adapters/), and prompt-tuned
    formats, and creates passthrough VirtualModels for the base and prompt-tuned entries only.

    LoRA entries must not get a VirtualModel (NAME_PATTERN rejects "&" and "/"), and the passthrough
    loop must not crash on LoRA ids. LoRA is positioned between base and prompt-tuned so that if the
    old parse_entity_ref ValueError regression returns, the prompt-tuned VirtualModel won't be created.
    """
    config = MagicMock()
    config.model_entity_id = "e2e-ws/qwen-lora-base"
    provider = MagicMock()
    provider.workspace = "e2e-ws"
    provider.name = "nim-provider"
    provider.model_deployment_id = "e2e-ws/my-nim"
    provider.enabled_models = None
    provider.served_models = []

    ctx = ModelContext(
        model_provider=provider,
        model_deployment=MagicMock(),
        model_deployment_config=config,
        model_entity=None,
    )

    discovered = [
        {"id": "e2e-ws/qwen-lora-base", "root": "e2e-ws/qwen-lora-base", "parent": None},
        {"id": "qwen-lora-base-lora-e2e-dataset-5c30", "root": "/scratch/loras/...", "parent": "e2e-ws/qwen-lora-base"},
        {"id": "qwen-lora-prompt-tuned", "root": "e2e-ws/qwen-lora-base", "parent": None},
    ]
    reconciler._models_sdk.inference.providers.update_status = AsyncMock()

    with patch.object(reconciler, "_discover_models", return_value=DiscoverySuccess(discovered)):
        await reconciler.reconcile_model_providers([ctx])

    served = reconciler._models_sdk.inference.providers.update_status.call_args.kwargs["served_models"]
    by_entity_id = {m.model_entity_id: m.served_model_name for m in served}
    assert by_entity_id["e2e-ws/qwen-lora-base"] == "e2e-ws/qwen-lora-base"
    lora_entity_id = "e2e-ws/qwen-lora-base&adapters/e2e-ws/qwen-lora-base-lora-e2e-dataset-5c30"
    assert by_entity_id[lora_entity_id] == "qwen-lora-base-lora-e2e-dataset-5c30"
    assert by_entity_id["e2e-ws/qwen-lora-prompt-tuned"] == "qwen-lora-prompt-tuned"
    assert len(served) == 3

    vm_create_calls = reconciler._models_sdk.inference.virtual_models.create.call_args_list
    created_names = {call.kwargs["name"] for call in vm_create_calls}
    assert created_names == {"qwen-lora-base", "qwen-lora-prompt-tuned"}
    for call in vm_create_calls:
        assert call.kwargs["workspace"] == "e2e-ws"
        assert call.kwargs["default_model_entity"] == f"e2e-ws/{call.kwargs['name']}"
        assert call.kwargs["autoprovisioned"] is True


def test_handle_model_deployment_provider_base_only(reconciler):
    """_handle_model_deployment_provider returns only base when only base is discovered."""
    config = MagicMock()
    config.model_entity_id = "ws/base"
    provider = MagicMock()
    provider.workspace = "ws"
    provider.enabled_models = None
    models = [{"id": "ws/base", "root": "ws/base", "parent": None}]
    result = DiscoverySuccess(models)
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )
    out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)
    assert len(out) == 1
    assert out[0].model_entity_id == "ws/base"
    assert out[0].served_model_name == "ws/base"


def test_handle_model_deployment_provider_unmatched_skipped(reconciler):
    """Unmatched discovered entries are not added to served_models."""
    config = MagicMock()
    config.model_entity_id = "ws/base"
    provider = MagicMock()
    provider.workspace = "ws"
    provider.enabled_models = None
    models = [
        {"id": "ws/base", "root": "ws/base", "parent": None},
        {"id": "other-model", "root": "other-root", "parent": None},
    ]
    result = DiscoverySuccess(models)
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )
    out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)
    assert len(out) == 1
    assert out[0].model_entity_id == "ws/base"


def test_resolve_base_backend_model_id_from_nim_deployment_only():
    """When model_entity_id is unset, nim_deployment model_namespace/model_name resolves base id."""
    config = MagicMock()
    config.model_entity_id = None
    config.nim_deployment = MagicMock(model_namespace="my-ws", model_name="qwen-base", model_revision=None)
    assert _resolve_base_backend_model_id(config, None) == "my-ws/qwen-base"


def test_resolve_base_backend_model_id_prefers_model_entity_over_nim():
    """Explicit model_entity_id wins over nim_deployment."""
    config = MagicMock()
    config.model_entity_id = "a/b"
    config.nim_deployment = MagicMock(model_namespace="ignored", model_name="ignored", model_revision=None)
    assert _resolve_base_backend_model_id(config, None) == "a/b"


def test_handle_model_deployment_provider_uses_nim_when_no_model_entity_id(reconciler):
    """Classification works when only nim_deployment references the base model (no model_entity_id)."""
    config = MagicMock()
    config.model_entity_id = None
    config.nim_deployment = MagicMock(model_namespace="ws", model_name="base", model_revision=None)
    provider = MagicMock()
    provider.workspace = "ws"
    provider.enabled_models = None
    models = [
        {"id": "ws/base", "root": "ws/base", "parent": None},
        {"id": "adapter-x", "root": "/scratch/x", "parent": "ws/base"},
    ]
    result = DiscoverySuccess(models)
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )
    out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)
    assert len(out) == 2
    assert {m.model_entity_id for m in out} == {"ws/base", "ws/base&adapters/ws/adapter-x"}


def test_discovery_success_model_ids_property():
    """DiscoverySuccess model_ids property matches id fields."""
    success = DiscoverySuccess(_discovery_models_from_ids(["model-1", "model-2"]))
    assert success.model_ids == ["model-1", "model-2"]
    assert len(success.models) == 2
    assert success.models[0]["id"] == "model-1"


def test_deployment_lora_strips_provider_workspace_prefix_from_adapter_segment(reconciler):
    """NIM echoing a qualified adapter id (``ws/lora-1``) must not produce a double-prefixed composite."""
    config = MagicMock()
    config.model_entity_id = "ws/base"
    config.nim_deployment = MagicMock(model_namespace="ws", model_name="base", model_revision=None)
    provider = MagicMock(workspace="ws", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws/base", "root": "ws/base", "parent": None},
            {"id": "ws/lora-1", "root": "/scratch/x", "parent": "ws/base"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)
    by_eid = {m.model_entity_id: m for m in out}

    assert "ws/base&adapters/ws/lora-1" in by_eid
    # served_model_name keeps the raw NIM id so forwarding hits the backend unchanged.
    assert by_eid["ws/base&adapters/ws/lora-1"].served_model_name == "ws/lora-1"


def test_deployment_lora_decodes_double_dash_into_cross_workspace_composite(reconciler):
    """Wire format: LoRA id ``{adapter_ws}--{adapter_name}`` decodes to a
    cross-workspace composite ``{base_id}&adapters/{adapter_ws}/{adapter_name}``.

    The adapter lives in ``ws-other`` while the base model and provider live in ``ws-base``.
    The reconciler must use ``ws-other`` (recovered from the id) as the adapter workspace
    segment, not ``ws-base``.
    """
    config = MagicMock()
    config.model_entity_id = "ws-base/qwen-base"
    config.nim_deployment = MagicMock(model_namespace="ws-base", model_name="qwen-base", model_revision=None)
    provider = MagicMock(workspace="ws-base", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws-base/qwen-base", "root": "ws-base/qwen-base", "parent": None},
            {"id": "ws-other--shared-lora", "root": "/scratch/x", "parent": "ws-base/qwen-base"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    out = reconciler._generate_deployment_served_model_mappings(provider, "ws-base/p", result, ctx)
    by_eid = {m.model_entity_id: m for m in out}

    assert by_eid["ws-base/qwen-base&adapters/ws-other/shared-lora"].served_model_name == "ws-other--shared-lora"


def test_deployment_lora_same_workspace_double_dash_decodes_round_trip(reconciler):
    """Test same-workspace adapter encoded as ``{ws}--{name}`` round-trips correctly."""
    config = MagicMock()
    config.model_entity_id = "ws/base"
    provider = MagicMock(workspace="ws", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws/base", "root": "ws/base", "parent": None},
            {"id": "ws--my-lora", "root": "/scratch/x", "parent": "ws/base"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)
    by_eid = {m.model_entity_id: m.served_model_name for m in out}

    assert by_eid["ws/base&adapters/ws/my-lora"] == "ws--my-lora"


def test_deployment_lora_qualified_double_dash_decodes_same_name_across_workspaces(reconciler):
    """NIM may prepend the served-model namespace (``{base_ws}/``) to current-format ids.

    Wire format ``{adapter_ws}--{name}`` becomes ``{base_ws}/{adapter_ws}--{name}`` when
    NIM echoes it back qualified. Without the upfront ``removeprefix("{base_ws}/")``,
    ``partition("--")`` would set ``adapter_ws = "{base_ws}/{adapter_ws}"`` (containing a
    ``/``), which fails NAME_PATTERN and silently drops the LoRA mapping.

    Both adapters share the name ``"lora"`` to also pin the cross-workspace
    disambiguation that the ``--`` encoding exists for: a regression that mis-routed
    one of them would collide on the same dict key here, not just route to a wrong
    label.
    """
    config = MagicMock()
    config.model_entity_id = "ws-base/qwen-base"
    config.nim_deployment = MagicMock(model_namespace="ws-base", model_name="qwen-base", model_revision=None)
    provider = MagicMock(workspace="ws-base", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws-base/qwen-base", "root": "ws-base/qwen-base", "parent": None},
            {"id": "ws-base/ws-base--lora", "root": "/scratch/x", "parent": "ws-base/qwen-base"},
            {"id": "ws-base/ws-other--lora", "root": "/scratch/x", "parent": "ws-base/qwen-base"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    out = reconciler._generate_deployment_served_model_mappings(provider, "ws-base/p", result, ctx)
    by_eid = {m.model_entity_id: m.served_model_name for m in out}

    # Both adapters survive (no NAME_PATTERN drops) and route under the recovered adapter workspace.
    assert by_eid["ws-base/qwen-base&adapters/ws-base/lora"] == "ws-base/ws-base--lora"
    assert by_eid["ws-base/qwen-base&adapters/ws-other/lora"] == "ws-base/ws-other--lora"
    # The base_ws qualifier never leaks into the recovered adapter_ws segment.
    for eid in by_eid:
        if "&adapters/" in eid:
            adapter_path = eid.split("&adapters/", 1)[1]
            assert "/" in adapter_path, f"{adapter_path!r} should be ws/name"
            recovered_ws, _, _ = adapter_path.partition("/")
            assert "/" not in recovered_ws, f"adapter_ws {recovered_ws!r} must not contain a slash"


def test_deployment_lora_no_double_dash_falls_back_to_base_model_workspace(reconciler, caplog):
    """Backward compat: a LoRA id without ``--`` anchors on the BASE MODEL's workspace.

    Pre-AALGO-129 sidecars nested adapters under the model entity (so the
    adapter shared the model's workspace), and the new sidecar's
    ``_resolve_adapter_workspace`` fallback also collapses missing
    ``adapter.workspace`` onto the base model's workspace. Either way, the
    correct anchor for the legacy id is the base model's workspace.

    In this test the provider and the base model live in the same workspace,
    so the same-workspace and base-workspace interpretations are
    indistinguishable; the cross-workspace test below pins the actual
    contract.
    """
    config = MagicMock()
    config.model_entity_id = "ws/base"
    provider = MagicMock(workspace="ws", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws/base", "root": "ws/base", "parent": None},
            {"id": "legacy-lora", "root": "/scratch/x", "parent": "ws/base"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    with caplog.at_level("WARNING"):
        out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)

    by_eid = {m.model_entity_id: m.served_model_name for m in out}
    assert by_eid["ws/base&adapters/ws/legacy-lora"] == "legacy-lora"
    assert any("no '--' delimiter" in rec.message for rec in caplog.records)


def test_deployment_lora_no_double_dash_uses_base_workspace_when_provider_differs(reconciler, caplog):
    """Cross-workspace: provider in ``ws-prov``, base model in ``ws-base``.

    A legacy LoRA id (no ``--``) must route under ``ws-base/`` because that's
    where the adapter actually lives — using the provider's workspace here
    would build ``ws-base/llama&adapters/ws-prov/legacy-lora``, which is a
    non-existent entity and 404s on the &adapters route.

    Both bare and qualified id shapes are exercised:
    - ``"legacy-lora"``         → adapter dir name with no qualifier.
    - ``"ws-base/legacy-lora"`` → NIM echoing the served-model namespace prefix.
    Both must end up routed under ``ws-base/``.
    """
    config = MagicMock()
    config.model_entity_id = "ws-base/llama"
    provider = MagicMock(workspace="ws-prov", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws-base/llama", "root": "ws-base/llama", "parent": None},
            {"id": "legacy-lora", "root": "/scratch/x", "parent": "ws-base/llama"},
            {"id": "ws-base/qualified-lora", "root": "/scratch/x", "parent": "ws-base/llama"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    with caplog.at_level("WARNING"):
        out = reconciler._generate_deployment_served_model_mappings(provider, "ws-prov/p", result, ctx)

    by_eid = {m.model_entity_id: m.served_model_name for m in out}
    assert by_eid["ws-base/llama&adapters/ws-base/legacy-lora"] == "legacy-lora"
    assert by_eid["ws-base/llama&adapters/ws-base/qualified-lora"] == "ws-base/qualified-lora"
    assert all("ws-prov" not in eid.split("&adapters/")[-1] for eid in by_eid if "&adapters/" in eid), (
        "adapter segment must never contain provider workspace"
    )
    assert any("base model workspace" in rec.message for rec in caplog.records)


def test_deployment_lora_invalid_segments_skipped(reconciler, caplog):
    """A LoRA id whose decoded segments fail NAME_PATTERN is skipped with a warning, never emitted."""
    config = MagicMock()
    config.model_entity_id = "ws/base"
    provider = MagicMock(workspace="ws", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws/base", "root": "ws/base", "parent": None},
            {"id": "BAD--adapter", "root": "/scratch/x", "parent": "ws/base"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    with caplog.at_level("WARNING"):
        out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)

    eids = {m.model_entity_id for m in out}
    assert eids == {"ws/base"}
    assert any("NAME_PATTERN" in rec.message for rec in caplog.records)


def test_deployment_lora_double_dash_only_partitions_first_occurrence(reconciler):
    """``str.partition`` splits on the first ``--`` only — adapter names with literal ``--`` cannot
    occur in practice (NAME_PATTERN forbids consecutive hyphens) but we assert the behavior here so
    a future regression that relaxes the pattern surfaces in tests rather than at runtime.
    """
    config = MagicMock()
    config.model_entity_id = "ws/base"
    provider = MagicMock(workspace="ws", enabled_models=None)
    # ``adapter-ws--lora--v2`` would partition as ("adapter-ws", "--", "lora--v2"); ``lora--v2``
    # fails NAME_PATTERN (consecutive hyphens) and is skipped — no malformed composite emitted.
    result = DiscoverySuccess(
        [
            {"id": "ws/base", "root": "ws/base", "parent": None},
            {"id": "adapter-ws--lora--v2", "root": "/scratch/x", "parent": "ws/base"},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)
    eids = {m.model_entity_id for m in out}
    assert eids == {"ws/base"}


def test_deployment_prompt_tuned_strips_provider_workspace_prefix(reconciler):
    """NIM echoing a qualified prompt-tuned id (``ws/tuned``) must produce ``ws/tuned``, not ``ws/ws/tuned``."""
    config = MagicMock()
    config.model_entity_id = "ws/base"
    config.nim_deployment = MagicMock(model_namespace="ws", model_name="base", model_revision=None)
    provider = MagicMock(workspace="ws", enabled_models=None)
    result = DiscoverySuccess(
        [
            {"id": "ws/base", "root": "ws/base", "parent": None},
            {"id": "ws/tuned", "root": "ws/base", "parent": None},
        ]
    )
    ctx = ModelContext(
        model_provider=provider, model_deployment=None, model_deployment_config=config, model_entity=None
    )

    out = reconciler._generate_deployment_served_model_mappings(provider, "ws/p", result, ctx)
    by_eid = {m.model_entity_id: m for m in out}

    assert "ws/tuned" in by_eid
    assert by_eid["ws/tuned"].served_model_name == "ws/tuned"


# =============================================================================
# served_model_entity_id validation
# =============================================================================


@pytest.mark.parametrize(
    ("model_entity_id", "expected"),
    [
        # Accepted shapes: plain ws/name and LoRA composite ws/base&adapters/ws/adapter.
        ("ws/model", True),
        ("my-ws/llama-3-2", True),
        ("ws/base&adapters/ws/lora-1", True),
        ("ws1/base&adapters/ws2/adapter-name", True),
        # Rejected: structural issues (empty / missing segments).
        ("", False),
        ("bare-name", False),
        ("/name", False),
        ("ws/", False),
        ("ws/&adapters/ws/adapter", False),
        ("ws/base&adapters/", False),
        ("ws/base&adapters/ws", False),
        ("ws/base&adapters//adapter", False),
        ("ws/base&adapters/ws/", False),
        # Rejected: NAME_PATTERN violations on each segment.
        ("ws/Bad-Name", False),
        ("ws/9bad", False),
        ("BAD-WS/name", False),
        ("ws/base&adapters/BAD/adapter", False),
        ("ws/base&adapters/ws/Bad-Adapter", False),
    ],
)
def test_is_valid_served_model_entity_id(model_entity_id, expected):
    assert _is_valid_served_model_entity_id(model_entity_id) is expected
