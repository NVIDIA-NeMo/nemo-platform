# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for real IGW background cache refresh of Guardrails configs.

These are the real-subprocess counterpart to the plugin's own
``test_middleware_config_caching.py`` integration tests, which manually call
``harness.refresh_caches()`` because their harness has no background
controller loop. Here we let IGW's real background cache-refresh task pick up
a GuardrailConfig update or delete for a guarded VirtualModel that
is already warm, polling until the change takes effect within a bounded
timeout.
"""

import time
from typing import Any, cast

import nemo_platform
import pytest
from nemo_platform import NeMoPlatform
from nmp.testing import MockProviderResponse, add_mock_provider

from e2e.guardrails.utils import (
    BACKEND_RESPONSE,
    USER_INPUT,
    activated_rails_by_name,
    delete_config_if_present,
    is_chat_response_blocked,
    post_chat_completion,
    setup_guarded_virtual_model,
    unique_name,
)

CACHE_REFRESH_TIMEOUT_SECONDS = 30.0
CACHE_REFRESH_POLL_INTERVAL_SECONDS = 1.0
INJECTION_DETECTION_FLOW = "injection detection"
LOG_ACTIVATED_RAILS = {"guardrails": {"options": {"log": {"activated_rails": True}}}}


def _yara_output_config(*, match_word: str) -> dict[str, Any]:
    """An output-rail injection-detection config with one custom YARA rule.

    Whether a request is blocked depends only on whether ``match_word``
    appears (case-insensitively) in the fixed backend response, so flipping
    ``match_word`` between config versions is enough to prove which config
    version a request actually ran against. No external model call is needed,
    which keeps the cache-refresh assertion isolated from mock-model timing.
    """
    return {
        "rails": {
            "config": {
                "injection_detection": {
                    "injections": ["reject_match"],
                    "yara_rules": {
                        "reject_match": (
                            "rule reject_match {\n"
                            " strings:\n"
                            f'  $string = "{match_word}" nocase\n'
                            " condition:\n"
                            "  $string\n"
                            "}"
                        )
                    },
                    "action": "reject",
                }
            },
            "output": {"flows": [INJECTION_DETECTION_FLOW]},
        },
    }


def _setup_backend_and_vm(sdk: NeMoPlatform, workspace: str) -> tuple[str, str, str]:
    """Register a mock backend model and a guarded VM using a v1 (never-matching) config.

    Returns ``(virtual_model_name, backend_model_ref, config_name)``.
    """
    backend_model_name = unique_name("main-model")
    virtual_model_name = unique_name("gr-vm")
    config_name = unique_name("gr-config")
    backend_model_ref = f"{workspace}/{backend_model_name}"

    add_mock_provider(
        sdk,
        workspace=workspace,
        name=unique_name("gr-provider"),
        served_models={backend_model_name: backend_model_name},
        mock_response_body_by_model={
            backend_model_ref: [
                MockProviderResponse(
                    response_body={
                        "id": "chatcmpl-cache-refresh",
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": BACKEND_RESPONSE},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                ),
            ],
        },
        should_autoprovision_virtual_model=False,
    )

    setup_guarded_virtual_model(
        sdk,
        workspace=workspace,
        virtual_model_name=virtual_model_name,
        backend_model_ref=backend_model_ref,
        config_name=config_name,
        # By default, set a YARA rule that will not match the fixed backend response,
        # so all requests using this VM are allowed.
        config_data=_yara_output_config(match_word="fake dangerous phrase"),
        rail_types=("output",),
    )
    return virtual_model_name, backend_model_ref, config_name


def test_config_update_reflected_after_real_background_refresh(
    sdk: NeMoPlatform,
    workspace: str,
) -> None:
    """Updating a referenced GuardrailConfig should change rail behavior once IGW's
    real background cache refresh (not a manually-forced one) re-resolves the VM.
    """
    virtual_model_name, backend_model_ref, config_name = _setup_backend_and_vm(sdk, workspace)
    try:
        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": USER_INPUT}],
        )
        assert not is_chat_response_blocked(response)
        assert response["choices"][0]["message"]["content"] == BACKEND_RESPONSE

        # Update the config with a YARA rule that matches the fixed backend response,
        # so all requests using this VM are blocked.
        sdk.guardrail.configs.update(
            name=config_name,
            workspace=workspace,
            data=_yara_output_config(match_word="paris"),
        )

        deadline = time.time() + CACHE_REFRESH_TIMEOUT_SECONDS
        response = None
        while time.time() < deadline:
            response = post_chat_completion(
                sdk,
                workspace=workspace,
                virtual_model_name=virtual_model_name,
                backend_model_ref=backend_model_ref,
                messages=[{"role": "user", "content": USER_INPUT}],
                extra_body=LOG_ACTIVATED_RAILS,
            )
            if is_chat_response_blocked(response):
                break
            time.sleep(CACHE_REFRESH_POLL_INTERVAL_SECONDS)

        assert response is not None and is_chat_response_blocked(response), (
            f"Updated GuardrailConfig was not reflected via the real IGW background "
            f"cache refresh within {CACHE_REFRESH_TIMEOUT_SECONDS}s"
        )
        # Confirm the block came from the updated YARA rule, not some other failure.
        assert activated_rails_by_name(response)[INJECTION_DETECTION_FLOW]["stop"] is True
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)


def test_config_delete_blocks_requests_after_real_background_refresh(
    sdk: NeMoPlatform,
    workspace: str,
) -> None:
    """Deleting a referenced GuardrailConfig should fail the VM closed (503) once
    IGW's real background cache refresh notices the config is gone.
    """
    virtual_model_name, backend_model_ref, config_name = _setup_backend_and_vm(sdk, workspace)
    try:
        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": USER_INPUT}],
        )
        assert not is_chat_response_blocked(response)

        sdk.guardrail.configs.delete(name=config_name, workspace=workspace)

        deadline = time.time() + CACHE_REFRESH_TIMEOUT_SECONDS
        last_status: int | None = None
        while time.time() < deadline:
            try:
                post_chat_completion(
                    sdk,
                    workspace=workspace,
                    virtual_model_name=virtual_model_name,
                    backend_model_ref=backend_model_ref,
                    messages=[{"role": "user", "content": USER_INPUT}],
                )
            except nemo_platform.APIStatusError as exc:
                last_status = exc.status_code
                if exc.status_code == 503:
                    detail = cast(dict[str, Any], exc.body).get("detail")
                    assert isinstance(detail, str)
                    assert "Middleware configuration unavailable" in detail
                    return
            time.sleep(CACHE_REFRESH_POLL_INTERVAL_SECONDS)

        pytest.fail(
            f"Deleted GuardrailConfig did not fail the VM closed within "
            f"{CACHE_REFRESH_TIMEOUT_SECONDS}s; last observed status: {last_status}"
        )
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)
