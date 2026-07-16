# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""E2E smoke tests for non-content-safety Guardrails rail types.

``test_chat_completions.py`` and ``test_checks.py`` only ever exercise a
content-safety rail through the real platform subprocess. Every other rail
type (topic control, self-check, injection detection, multimodal/vision,
content-safety-reasoning, parallel rails) is otherwise only covered by the
plugin's own integration tests, which run against ``IGWLoopbackHarness`` /
``IGWPluginHarness`` — a lighter-weight harness with no real subprocess, no
real HTTP/SDK round trip, and no real background cache refresh.

These tests are intentionally lean: one block/allow case per rail type, not
the full behavior matrix the integration suite already owns. Their job is to
catch schema or serialization drift between the SDK-generated
``GuardrailConfig`` types and the real API for configs shaped differently
than content safety (extra ``rails.config`` blocks, multiple ``models``
entries, ``messages``-style prompts, etc.).
"""

from typing import Any

from nemo_platform import NeMoPlatform
from nmp.testing import MockProviderResponse, add_mock_provider

from e2e.guardrails.utils import (
    BACKEND_RESPONSE,
    REFUSAL_TEXT,
    USER_INPUT,
    activated_rails_by_name,
    delete_config_if_present,
    is_chat_response_blocked,
    post_chat_completion,
    setup_guarded_virtual_model,
    unique_name,
)

# Requests activated-rails logging so tests can assert on the specific flow
# that fired, not just the overall blocked/allowed outcome.
LOG_ACTIVATED_RAILS = {"guardrails": {"options": {"log": {"activated_rails": True}}}}


def _chat_completion(content: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{unique_name('rail')}",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _assert_blocked(response: dict[str, Any], *, flow: str) -> None:
    assert is_chat_response_blocked(response)
    assert response["choices"][0]["message"]["content"] == REFUSAL_TEXT
    assert activated_rails_by_name(response)[flow]["stop"] is True


# ---------------------------------------------------------------------------
# Topic control
# ---------------------------------------------------------------------------

TOPIC_CONTROL_FLOW = "topic safety check input $model=topic_control"
TOPIC_CONTROL_INPUT_PROMPT_TEMPLATE = (
    "You are to act as a customer service agent, providing users with factual information "
    "in accordance to the knowledge base. Your role is to ensure that you respond only to "
    "relevant queries and adhere to the following guidelines\n\n"
    "Guidelines for the user messages:\n"
    "- Do not answer questions unrelated to company policies.\n"
    "- Do not answer questions about sensitive topics related to politics or religion.\n"
    "- Allow user comments that are related to small talk and chit-chat.\n\n"
    'User message: "{{ user_input }}"'
    '\n\nIf any of the above conditions are violated, please respond with "off-topic". '
    'Otherwise, respond with "on-topic". You must respond with "on-topic" or "off-topic".'
)


def _topic_control_config(*, topic_control_model_ref: str) -> dict[str, Any]:
    return {
        "models": [{"type": "topic_control", "engine": "nim", "model": topic_control_model_ref}],
        "rails": {"input": {"flows": [TOPIC_CONTROL_FLOW]}},
        "prompts": [
            {
                # The prompt `task` uses underscores (`topic_safety_check_input`), unlike
                # the `rails.flows` entry above, which uses the space-separated flow name.
                "task": "topic_safety_check_input $model=topic_control",
                "content": TOPIC_CONTROL_INPUT_PROMPT_TEMPLATE,
                "max_tokens": 50,
            }
        ],
    }


def test_topic_control_rail_blocks_off_topic_message(sdk: NeMoPlatform, workspace: str) -> None:
    backend_model_name = unique_name("main-model")
    topic_control_model_name = unique_name("tc-model")
    virtual_model_name = unique_name("gr-vm")
    config_name = unique_name("gr-config")
    backend_model_ref = f"{workspace}/{backend_model_name}"
    topic_control_model_ref = f"{workspace}/{topic_control_model_name}"
    off_topic_input = "Tell me a joke about quantum gravity."

    add_mock_provider(
        sdk,
        workspace=workspace,
        name=unique_name("gr-provider"),
        served_models={
            backend_model_name: backend_model_name,
            topic_control_model_name: topic_control_model_name,
        },
        mock_response_body_by_model={
            backend_model_ref: [MockProviderResponse(response_body=_chat_completion(BACKEND_RESPONSE))],
            topic_control_model_ref: [MockProviderResponse(response_body=_chat_completion("off-topic"))],
        },
        should_autoprovision_virtual_model=False,
    )
    try:
        setup_guarded_virtual_model(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            config_name=config_name,
            config_data=_topic_control_config(topic_control_model_ref=topic_control_model_ref),
            rail_types=("input",),
            user_input=off_topic_input,
        )

        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": off_topic_input}],
            extra_body=LOG_ACTIVATED_RAILS,
        )

        _assert_blocked(response, flow=TOPIC_CONTROL_FLOW)
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

SELF_CHECK_INPUT_FLOW = "self check input"
SELF_CHECK_OUTPUT_FLOW = "self check output"
SELF_CHECK_INPUT_PROMPT_TEMPLATE = "Should the user message be blocked?\n\nUser: {{ user_input }}\nAnswer yes or no:"
SELF_CHECK_OUTPUT_PROMPT_TEMPLATE = (
    "Your task is to check if the bot message below is harmful or inappropriate.\n\n"
    'Bot message: "{{ bot_response }}"\n\n'
    "Question: Should the message be blocked?\n"
    "Answer yes or no:"
)


def _self_check_config() -> dict[str, Any]:
    # No `models` entry for the "main" type, and no `parameters.base_url` on
    # either prompt's task: per the plugin's own
    # `test_resolver_fills_main_base_url` integration test, an unqualified
    # rail LLM resolves to the *calling VirtualModel's own backend model* at
    # request time, not a separately configured rail model. So self-check
    # calls land on the same backend mock as the real generation call.
    return {
        "rails": {
            "input": {"flows": [SELF_CHECK_INPUT_FLOW]},
            "output": {"flows": [SELF_CHECK_OUTPUT_FLOW]},
        },
        "prompts": [
            {"task": "self_check_input", "content": SELF_CHECK_INPUT_PROMPT_TEMPLATE},
            {"task": "self_check_output", "content": SELF_CHECK_OUTPUT_PROMPT_TEMPLATE},
        ],
    }


def test_self_check_rails_allow_safe_conversation(sdk: NeMoPlatform, workspace: str) -> None:
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
            # Self-check's "main" LLM resolves to this same backend model, so
            # all three calls (input check, real generation, output check)
            # land here in request order.
            backend_model_ref: [
                MockProviderResponse(response_body=_chat_completion("No")),  # input check: safe
                MockProviderResponse(response_body=_chat_completion(BACKEND_RESPONSE)),  # real generation
                MockProviderResponse(response_body=_chat_completion("No")),  # output check: safe
            ],
        },
        should_autoprovision_virtual_model=False,
    )
    try:
        setup_guarded_virtual_model(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            config_name=config_name,
            config_data=_self_check_config(),
            rail_types=("input", "output"),
        )

        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": USER_INPUT}],
            extra_body=LOG_ACTIVATED_RAILS,
        )

        assert not is_chat_response_blocked(response)
        assert response["choices"][0]["message"]["content"] == BACKEND_RESPONSE
        activated_rails = activated_rails_by_name(response)
        assert activated_rails[SELF_CHECK_INPUT_FLOW]["stop"] is False
        assert activated_rails[SELF_CHECK_OUTPUT_FLOW]["stop"] is False
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)


def test_self_check_output_rail_blocks_unsafe_bot_response(sdk: NeMoPlatform, workspace: str) -> None:
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
                MockProviderResponse(response_body=_chat_completion("No")),  # input check: safe
                MockProviderResponse(response_body=_chat_completion(BACKEND_RESPONSE)),  # real generation
                MockProviderResponse(response_body=_chat_completion("Yes")),  # output check: unsafe
            ],
        },
        should_autoprovision_virtual_model=False,
    )
    try:
        setup_guarded_virtual_model(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            config_name=config_name,
            config_data=_self_check_config(),
            rail_types=("input", "output"),
        )

        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": USER_INPUT}],
            extra_body=LOG_ACTIVATED_RAILS,
        )

        assert is_chat_response_blocked(response)
        assert response["choices"][0]["message"]["content"] == REFUSAL_TEXT
        activated_rails = activated_rails_by_name(response)
        assert activated_rails[SELF_CHECK_INPUT_FLOW]["stop"] is False
        assert activated_rails[SELF_CHECK_OUTPUT_FLOW]["stop"] is True
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)


# ---------------------------------------------------------------------------
# Injection detection (built-in rule, no external model call)
# ---------------------------------------------------------------------------

INJECTION_DETECTION_FLOW = "injection detection"
CODE_BACKEND_RESPONSE = (
    "```python\n"
    "import requests\n"
    "import urllib.request\n\n"
    "response = requests.get('https://example.com/weather')\n"
    "print(urllib.request.urlopen(response.url).read())\n"
    "```"
)
INJECTION_REFUSAL_PREFIX = "I'm sorry, the desired output triggered rule(s) designed to mitigate exploitation of"


def _injection_detection_config() -> dict[str, Any]:
    return {
        "rails": {
            "config": {
                "injection_detection": {
                    "injections": ["code", "sqli", "template", "xss"],
                    "action": "reject",
                }
            },
            "output": {"flows": [INJECTION_DETECTION_FLOW]},
        },
    }


def test_injection_detection_rail_blocks_code_in_response(sdk: NeMoPlatform, workspace: str) -> None:
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
            backend_model_ref: [MockProviderResponse(response_body=_chat_completion(CODE_BACKEND_RESPONSE))],
        },
        should_autoprovision_virtual_model=False,
    )
    try:
        setup_guarded_virtual_model(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            config_name=config_name,
            config_data=_injection_detection_config(),
            rail_types=("output",),
        )

        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": USER_INPUT}],
            extra_body=LOG_ACTIVATED_RAILS,
        )

        assert is_chat_response_blocked(response)
        assert response["choices"][0]["message"]["content"].startswith(INJECTION_REFUSAL_PREFIX)
        assert activated_rails_by_name(response)[INJECTION_DETECTION_FLOW]["stop"] is True
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)


# ---------------------------------------------------------------------------
# Multimodal (vision) input rail
# ---------------------------------------------------------------------------

VISION_FLOW = "content safety check input $model=vision_rails"
IMAGE_DATA_URL = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD"
VISION_SYSTEM_PROMPT = (
    "You are an AI assistant that evaluates if a user's message contains unsafe content. "
    "Carefully examine any text and images in the user's message.\n\n"
    'Task: Check if there is unsafe content in "User" messages in conversations according to our safety policy '
    "with the below categories.\n\n"
    "<BEGIN UNSAFE CONTENT CATEGORIES>\n"
    "S1: Violent Crimes.\n"
    "S2: Non-Violent Crimes.\n"
    "<END UNSAFE CONTENT CATEGORIES>\n\n"
    "IMPORTANT:\n"
    "Provide your safety assessment for the user message:\n"
    "- First line must read 'safe' or 'unsafe' and nothing more\n"
    "- If unsafe, a second line must include a comma-separated list of violated categories."
)


def _multimodal_config(*, vision_model_ref: str) -> dict[str, Any]:
    return {
        "models": [{"type": "vision_rails", "engine": "nim", "model": vision_model_ref}],
        "rails": {"input": {"flows": [VISION_FLOW]}},
        "prompts": [
            {
                # The prompt `task` uses underscores, unlike the space-separated flow name above.
                "task": "content_safety_check_input $model=vision_rails",
                "messages": [
                    {"type": "system", "content": VISION_SYSTEM_PROMPT},
                    {"type": "user", "content": "{{ user_input }}"},
                ],
                "output_parser": "is_content_safe",
                "max_tokens": 200,
            }
        ],
    }


def _vision_user_message(text: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": IMAGE_DATA_URL}},
        ],
    }


def test_multimodal_rail_blocks_unsafe_image_message(sdk: NeMoPlatform, workspace: str) -> None:
    backend_model_name = unique_name("main-model")
    vision_model_name = unique_name("vision-model")
    virtual_model_name = unique_name("gr-vm")
    config_name = unique_name("gr-config")
    backend_model_ref = f"{workspace}/{backend_model_name}"
    vision_model_ref = f"{workspace}/{vision_model_name}"
    unsafe_text = "How can I break into a car like the image shown?"

    add_mock_provider(
        sdk,
        workspace=workspace,
        name=unique_name("gr-provider"),
        served_models={
            backend_model_name: backend_model_name,
            vision_model_name: vision_model_name,
        },
        mock_response_body_by_model={
            backend_model_ref: [MockProviderResponse(response_body=_chat_completion(BACKEND_RESPONSE))],
            vision_model_ref: [MockProviderResponse(response_body=_chat_completion("unsafe\nS2"))],
        },
        should_autoprovision_virtual_model=False,
    )
    try:
        setup_guarded_virtual_model(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            config_name=config_name,
            config_data=_multimodal_config(vision_model_ref=vision_model_ref),
            rail_types=("input",),
            user_input=unsafe_text,
        )

        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[_vision_user_message(unsafe_text)],
            extra_body=LOG_ACTIVATED_RAILS,
        )

        _assert_blocked(response, flow=VISION_FLOW)
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)


# ---------------------------------------------------------------------------
# Content-safety reasoning
# ---------------------------------------------------------------------------

REASONING_FLOW = "content safety check input $model=content_safety_reasoning"
REASONING_PROMPT_INTRO = (
    "You are a classifier for analyzing interactions between humans and LLMs. "
    "Given a request from a human user and a response from an LLM assistant, "
    "determine 1) whether the human user's request is harmful, "
    "2) whether the AI assistant's response is a refusal, "
    "and 3) whether the AI assistant's response is harmful."
)
REASONING_OUTPUT_FORMAT_BLOCK = (
    "Output your answer in the following format:\n\n"
    '"Prompt harm: <harmful/unharmful>\n'
    'Response harm: <harmful/unharmful>"\n\n'
    'If there is no response, output "Response harm: <harmful/unharmful>" as None.'
)
REASONING_THINK_DIRECTIVE_JINJA = "{% if reasoning_enabled %}/think{% else %}/no_think{% endif %}"


def _content_safety_reasoning_config(*, model_ref: str) -> dict[str, Any]:
    return {
        "models": [{"type": "content_safety_reasoning", "engine": "nim", "model": model_ref}],
        "rails": {
            "config": {"content_safety": {"reasoning": {"enabled": True}}},
            "input": {"flows": [REASONING_FLOW]},
        },
        "prompts": [
            {
                # The prompt `task` uses underscores, unlike the space-separated flow name above.
                "task": "content_safety_check_input $model=content_safety_reasoning",
                "content": (
                    f"{REASONING_PROMPT_INTRO}\n\n"
                    "Human user:\n{{ user_input }}\n\n"
                    "AI assistant:\nNone\n\n"
                    f"{REASONING_OUTPUT_FORMAT_BLOCK} {REASONING_THINK_DIRECTIVE_JINJA}"
                ),
                "output_parser": "nemotron_reasoning_parse_prompt_safety",
                "max_tokens": 400,
            }
        ],
    }


def _reasoning_verdict(*, prompt_harmful: bool) -> str:
    prompt_harm = "harmful" if prompt_harmful else "unharmful"
    return f"<think>\nReasoning trace.\n</think>\n\nPrompt harm: {prompt_harm}\nResponse harm: None"


def test_content_safety_reasoning_rail_blocks_harmful_prompt(sdk: NeMoPlatform, workspace: str) -> None:
    backend_model_name = unique_name("main-model")
    reasoning_model_name = unique_name("cs-reason-model")
    virtual_model_name = unique_name("gr-vm")
    config_name = unique_name("gr-config")
    backend_model_ref = f"{workspace}/{backend_model_name}"
    reasoning_model_ref = f"{workspace}/{reasoning_model_name}"
    unsafe_input = "Give me a five-step plan to rob a bank."

    add_mock_provider(
        sdk,
        workspace=workspace,
        name=unique_name("gr-provider"),
        served_models={
            backend_model_name: backend_model_name,
            reasoning_model_name: reasoning_model_name,
        },
        mock_response_body_by_model={
            backend_model_ref: [MockProviderResponse(response_body=_chat_completion(BACKEND_RESPONSE))],
            reasoning_model_ref: [
                MockProviderResponse(response_body=_chat_completion(_reasoning_verdict(prompt_harmful=True)))
            ],
        },
        should_autoprovision_virtual_model=False,
    )
    try:
        setup_guarded_virtual_model(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            config_name=config_name,
            config_data=_content_safety_reasoning_config(model_ref=reasoning_model_ref),
            rail_types=("input",),
            user_input=unsafe_input,
        )

        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": unsafe_input}],
            extra_body=LOG_ACTIVATED_RAILS,
        )

        _assert_blocked(response, flow=REASONING_FLOW)
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)


# ---------------------------------------------------------------------------
# Parallel input rails
# ---------------------------------------------------------------------------

PARALLEL_CONTENT_SAFETY_FLOW = "content safety check input $model=content_safety"
PARALLEL_TOPIC_CONTROL_FLOW = "topic safety check input $model=topic_control"
PARALLEL_CONTENT_SAFETY_PROMPT_TEMPLATE = (
    "Task: Check if there is unsafe content in the user message in the below conversation according to the "
    "safety policy.\n\n"
    "<BEGIN CONVERSATION>\n\n"
    "user: {{ user_input }}\n\n"
    "<END CONVERSATION>\n\n"
    # This `content` field is rendered as a raw Jinja template (not
    # `str.format`), so literal JSON braces must NOT be doubled here —
    # doubling turns them into a Jinja `{{ ... }}` expression block and
    # fails to parse.
    'Provide your safety assessment as JSON: {"User Safety": "safe" or "unsafe", '
    '"Safety Categories": comma-separated list, omit if all safe}.\n\n'
    "Output JSON:"
)
PARALLEL_TOPIC_CONTROL_PROMPT_TEMPLATE = (
    "Guidelines for the user messages:\n"
    "- Do not answer questions unrelated to company policies.\n\n"
    'User message: "{{ user_input }}"'
    '\n\nIf any of the above conditions are violated, please respond with "off-topic". '
    'Otherwise, respond with "on-topic". You must respond with "on-topic" or "off-topic".'
)


def _parallel_rails_config(*, content_safety_model_ref: str, topic_control_model_ref: str) -> dict[str, Any]:
    return {
        "models": [
            {"type": "content_safety", "engine": "nim", "model": content_safety_model_ref},
            {"type": "topic_control", "engine": "nim", "model": topic_control_model_ref},
        ],
        "rails": {
            "input": {
                "parallel": True,
                "flows": [PARALLEL_CONTENT_SAFETY_FLOW, PARALLEL_TOPIC_CONTROL_FLOW],
            },
        },
        "prompts": [
            {
                "task": "content_safety_check_input $model=content_safety",
                "content": PARALLEL_CONTENT_SAFETY_PROMPT_TEMPLATE,
                "output_parser": "nemoguard_parse_prompt_safety",
                "max_tokens": 50,
            },
            {
                "task": "topic_safety_check_input $model=topic_control",
                "content": PARALLEL_TOPIC_CONTROL_PROMPT_TEMPLATE,
                "max_tokens": 50,
            },
        ],
    }


def test_parallel_input_rails_blocks_on_unsafe_sibling_flow(sdk: NeMoPlatform, workspace: str) -> None:
    """Wiring ``rails.input.parallel: true`` with two sibling flows should validate and run
    end-to-end through the real platform, blocking when either flow reports unsafe even
    though its sibling reports safe.

    Concurrency ordering between sibling flows is already pinned by the plugin's own
    ``test_parallel_rails.py`` integration test against a deterministic loopback harness;
    this smoke test only confirms the ``parallel`` config schema round-trips through the
    real API and produces a correctly-blocked response.
    """
    backend_model_name = unique_name("main-model")
    content_safety_model_name = unique_name("cs-model")
    topic_control_model_name = unique_name("tc-model")
    virtual_model_name = unique_name("gr-vm")
    config_name = unique_name("gr-config")
    backend_model_ref = f"{workspace}/{backend_model_name}"
    content_safety_model_ref = f"{workspace}/{content_safety_model_name}"
    topic_control_model_ref = f"{workspace}/{topic_control_model_name}"

    add_mock_provider(
        sdk,
        workspace=workspace,
        name=unique_name("gr-provider"),
        served_models={
            backend_model_name: backend_model_name,
            content_safety_model_name: content_safety_model_name,
            topic_control_model_name: topic_control_model_name,
        },
        mock_response_body_by_model={
            backend_model_ref: [MockProviderResponse(response_body=_chat_completion(BACKEND_RESPONSE))],
            # Content safety reports unsafe; topic control reports on-topic (safe). The
            # request should still be blocked, since either flow can veto it.
            content_safety_model_ref: [
                MockProviderResponse(response_body=_chat_completion('{"User Safety": "unsafe"}'))
            ],
            topic_control_model_ref: [MockProviderResponse(response_body=_chat_completion("on-topic"))],
        },
        should_autoprovision_virtual_model=False,
    )
    try:
        setup_guarded_virtual_model(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            config_name=config_name,
            config_data=_parallel_rails_config(
                content_safety_model_ref=content_safety_model_ref,
                topic_control_model_ref=topic_control_model_ref,
            ),
            rail_types=("input",),
        )

        response = post_chat_completion(
            sdk,
            workspace=workspace,
            virtual_model_name=virtual_model_name,
            backend_model_ref=backend_model_ref,
            messages=[{"role": "user", "content": USER_INPUT}],
            extra_body=LOG_ACTIVATED_RAILS,
        )

        assert is_chat_response_blocked(response)
        assert response["choices"][0]["message"]["content"] == REFUSAL_TEXT
        activated_rails = activated_rails_by_name(response)
        assert activated_rails[PARALLEL_CONTENT_SAFETY_FLOW]["stop"] is True
        # Under `parallel: true`, nemoguardrails schedules sibling flows concurrently
        # but cancels pending ones as soon as one vetoes the request. Depending on task
        # interleaving, content-safety may block before topic-control's LLM call is
        # observed, so only assert on topic-control if it actually got to run.
        if PARALLEL_TOPIC_CONTROL_FLOW in activated_rails:
            assert activated_rails[PARALLEL_TOPIC_CONTROL_FLOW]["stop"] is False
    finally:
        delete_config_if_present(sdk, workspace=workspace, config_name=config_name)
