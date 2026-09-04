# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""E2E coverage for automatic model selection in ``nemo setup --auto``.

Selection has to hold up on a cold start against a real platform: a provider is
created, its models are discovered, their passthrough VirtualModels are
published a moment later, and only a model that answers a live inference
request may be persisted as the default.

Provider registration from environment credentials and writing the CLI config
are the only stubbed steps; discovery, routing and probing go through the
platform.
"""

import threading
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from nemo_platform import NeMoPlatform
from nemo_platform_ext.cli.commands import setup as setup_commands
from nemo_platform_ext.cli.commands.setup import ModelPair
from nmp.testing import MockProviderResponse, add_mock_provider

pytestmark = [pytest.mark.timeout(300)]

SETUP_MOD = "nemo_platform_ext.cli.commands.setup"


def _unique_suffix() -> str:
    """Return a suffix that cannot be read as a parameter count (ex. ``12345b``)."""
    return f"x{uuid.uuid4().hex[:6]}"


def _chat_response(content: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _publish_route(sdk: NeMoPlatform, workspace: str, entity: str) -> None:
    """Create the passthrough VirtualModel the gateway routes *entity* through."""
    sdk.inference.virtual_models.create(
        workspace=workspace,
        name=entity,
        default_model_entity=f"{workspace}/{entity}",
        autoprovisioned=False,
    )


def _serve_model_without_a_route(sdk: NeMoPlatform, workspace: str, provider: str, entities: list[str]) -> None:
    """Advertise *entities* on *provider* without creating their VirtualModels.

    This is the state discovery sees on a cold start: a provider reports the
    models it serves before their passthrough routes are reconciled.
    """
    sdk.inference.providers.update_status(
        name=provider,
        workspace=workspace,
        served_models=[
            {"model_entity_id": f"{workspace}/{entity}", "served_model_name": entity} for entity in entities
        ],
    )


def _run_auto_setup(sdk: NeMoPlatform, workspace: str, provider_name: str) -> ModelPair | None:
    """Run ``_run_auto_mode`` for *provider_name* and return the persisted pair."""
    with (
        patch.dict("os.environ", {"NEMO_DEFAULT_MODEL": "", "NEMO_FAST_MODEL": ""}),
        patch(f"{SETUP_MOD}._auto_setup", return_value=provider_name),
        patch(f"{SETUP_MOD}._save_model_pair") as save_pair,
        patch(f"{SETUP_MOD}._maybe_install_skills"),
        patch(f"{SETUP_MOD}._maybe_deploy_agent"),
        patch(f"{SETUP_MOD}._verify_platform_health", return_value=True),
    ):
        setup_commands._run_auto_mode(
            MagicMock(),
            sdk,
            workspace,
            str(sdk.base_url),
            install_skills=False,
            deploy_agent=False,
        )

    if not save_pair.call_args_list:
        return None
    return save_pair.call_args.args[1]


def test_auto_setup_persists_a_default_the_account_can_serve(sdk: NeMoPlatform, workspace: str):
    """The largest model that answers becomes the default, the smallest the fast model."""
    suffix = _unique_suffix()
    ultra = f"nvidia-nemotron-ultra-500b-{suffix}"
    large = f"nvidia-nemotron-super-120b-{suffix}"
    nano = f"nvidia-nemotron-nano-9b-{suffix}"

    provider = add_mock_provider(
        sdk,
        workspace=workspace,
        name=f"selection-{suffix}",
        mock_response_body_by_model={
            # Discovery advertises a model this account cannot run.
            f"{workspace}/{ultra}": [
                MockProviderResponse(
                    response_code=404,
                    response_body={"detail": "Function not found for account"},
                )
            ],
            f"{workspace}/{large}": [MockProviderResponse(response_body=_chat_response("OK"))],
            f"{workspace}/{nano}": [MockProviderResponse(response_body=_chat_response("OK"))],
        },
        served_models={name: name for name in (ultra, large, nano)},
    )

    saved = _run_auto_setup(sdk, workspace, provider.name)

    assert saved == ModelPair(default=f"{workspace}/{large}", fast=f"{workspace}/{nano}")


def test_auto_setup_waits_for_a_late_published_model_route(sdk: NeMoPlatform, workspace: str):
    """A discovered model the gateway 404s becomes the default once its route exists."""
    suffix = _unique_suffix()
    entity = f"nvidia-nemotron-nano-9b-{suffix}"
    # Only the embedding model has a route up front, and it is filtered out of
    # the candidates, so selection has to wait for the chat model's route.
    embedding = f"nvidia-nv-embedqa-e5-{suffix}"

    provider = add_mock_provider(
        sdk,
        workspace=workspace,
        name=f"late-route-{suffix}",
        mock_response_body=_chat_response("OK"),
        served_models={embedding: embedding},
        should_autoprovision_virtual_model=False,
    )
    _serve_model_without_a_route(sdk, workspace, provider.name, [embedding, entity])

    publish_route = threading.Timer(2.0, _publish_route, args=(sdk, workspace, entity))
    publish_route.start()
    try:
        saved = _run_auto_setup(sdk, workspace, provider.name)
    finally:
        publish_route.cancel()

    assert saved == ModelPair(default=f"{workspace}/{entity}", fast=f"{workspace}/{entity}")


def test_auto_setup_saves_nothing_when_no_model_answers(sdk: NeMoPlatform, workspace: str):
    """A provider whose models all fail leaves the default unset rather than broken."""
    suffix = _unique_suffix()
    entity = f"nvidia-nemotron-nano-9b-{suffix}"

    provider = add_mock_provider(
        sdk,
        workspace=workspace,
        name=f"unusable-{suffix}",
        mock_response_body={"detail": "Function not found for account"},
        mock_status=404,
        served_models={entity: entity},
    )

    assert _run_auto_setup(sdk, workspace, provider.name) is None
