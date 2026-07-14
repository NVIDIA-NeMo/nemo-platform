# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for the Guardrails checks endpoint.

These tests verify that ``/apis/guardrails/v2/workspaces/{workspace}/checks``
runs content-safety rails through the real platform subprocess while using mock
providers for deterministic rail-model responses.
"""

from collections.abc import Callable
from typing import Any, TypeAlias, cast

import nemo_platform
import pytest
from nemo_platform.types.guardrail import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionUserMessageParam,
    GuardrailCheckResponse,
    GuardrailsDataParam,
)

from e2e.guardrails.utils import (
    BACKEND_RESPONSE,
    CONTENT_SAFETY_INPUT_FLOW,
    CONTENT_SAFETY_OUTPUT_FLOW,
    GuardrailsChatTestCase,
)

# `guardrails` is assembled dynamically from test fixture data (`content_safety_config()`,
# ad-hoc `extra_guardrails` overrides), so we build it as a plain dict and cast it once at
# the SDK call boundary rather than threading `GuardrailsDataParam`'s nested TypedDicts
# through the test fixtures.
_CheckMessage: TypeAlias = ChatCompletionUserMessageParam | ChatCompletionAssistantMessageParam


def _post_check(
    test_case: GuardrailsChatTestCase,
    *,
    config_data: dict[str, Any] | None = None,
    extra_guardrails: dict[str, Any] | None = None,
) -> GuardrailCheckResponse:
    guardrails: dict[str, Any]
    if test_case.config_mode == "referenced":
        guardrails = {"config_id": test_case.config_ref}
    else:
        if config_data is None:
            raise ValueError("config_data is required for inline checks")
        guardrails = {"config": config_data}

    if extra_guardrails:
        guardrails.update(extra_guardrails)

    return test_case.sdk.guardrail.check(
        workspace=test_case.workspace,
        model=test_case.backend_model_ref,
        messages=_check_messages(test_case),
        guardrails=cast(GuardrailsDataParam, guardrails),
    )


def _check_messages(test_case: GuardrailsChatTestCase) -> list[_CheckMessage]:
    messages: list[_CheckMessage] = [{"role": "user", "content": test_case.user_input}]
    if "output" in test_case.rail_types:
        messages.append({"role": "assistant", "content": BACKEND_RESPONSE})
    return messages


def _rail_status(response: GuardrailCheckResponse, rail_name: str) -> str:
    return response.rails_status[rail_name].status


def _activated_rails_by_name(response: GuardrailCheckResponse) -> dict[str, Any]:
    log = response.guardrails_data.log if response.guardrails_data else None
    activated_rails = log.activated_rails if log else None
    return {rail.name: rail for rail in activated_rails or []}


def test_checks_allows_safe_input(
    guardrails_check_test_case: Callable[..., tuple[GuardrailsChatTestCase, dict[str, Any]]],
) -> None:
    test_case, _config_data = guardrails_check_test_case(
        config_mode="referenced", outcome="safe", rail_types=("input",)
    )

    response = _post_check(test_case)

    assert response.status == "success"
    assert _rail_status(response, CONTENT_SAFETY_INPUT_FLOW) == "success"


def test_checks_blocks_unsafe_input(
    guardrails_check_test_case: Callable[..., tuple[GuardrailsChatTestCase, dict[str, Any]]],
) -> None:
    test_case, _config_data = guardrails_check_test_case(
        config_mode="referenced", outcome="unsafe_input", rail_types=("input",)
    )

    response = _post_check(test_case)

    assert response.status == "blocked"
    assert _rail_status(response, CONTENT_SAFETY_INPUT_FLOW) == "blocked"


def test_checks_blocks_unsafe_llm_output(
    guardrails_check_test_case: Callable[..., tuple[GuardrailsChatTestCase, dict[str, Any]]],
) -> None:
    test_case, _config_data = guardrails_check_test_case(
        config_mode="referenced", outcome="unsafe_output", rail_types=("output",)
    )

    response = _post_check(test_case)

    assert response.status == "blocked"
    assert _rail_status(response, CONTENT_SAFETY_OUTPUT_FLOW) == "blocked"


def test_checks_reports_guardrails_metadata_when_requested(
    guardrails_check_test_case: Callable[..., tuple[GuardrailsChatTestCase, dict[str, Any]]],
) -> None:
    test_case, _config_data = guardrails_check_test_case(
        config_mode="referenced", outcome="unsafe_output", rail_types=("input", "output")
    )

    response = _post_check(
        test_case,
        extra_guardrails={"options": {"log": {"activated_rails": True}}},
    )

    activated_rails = _activated_rails_by_name(response)
    assert activated_rails[CONTENT_SAFETY_INPUT_FLOW].stop is False
    assert activated_rails[CONTENT_SAFETY_OUTPUT_FLOW].stop is True


def test_checks_blocks_unsafe_input_with_inline_config(
    guardrails_check_test_case: Callable[..., tuple[GuardrailsChatTestCase, dict[str, Any]]],
) -> None:
    test_case, config_data = guardrails_check_test_case(
        config_mode="inline", outcome="unsafe_input", rail_types=("input",)
    )

    response = _post_check(test_case, config_data=config_data)

    assert response.status == "blocked"
    assert _rail_status(response, CONTENT_SAFETY_INPUT_FLOW) == "blocked"


def test_checks_rejects_unknown_config_id(
    guardrails_check_test_case: Callable[..., tuple[GuardrailsChatTestCase, dict[str, Any]]],
) -> None:
    test_case, _config_data = guardrails_check_test_case(
        config_mode="referenced", outcome="safe", rail_types=("input",)
    )

    with pytest.raises(nemo_platform.APIStatusError) as exc_info:
        _post_check(
            test_case,
            extra_guardrails={"config_id": f"{test_case.workspace}/missing-guardrails-config"},
        )

    assert exc_info.value.status_code == 400
