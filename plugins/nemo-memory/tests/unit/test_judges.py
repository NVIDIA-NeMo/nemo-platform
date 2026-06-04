# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the per-model memory-triage judges.

Mocks the Anthropic and OpenAI SDKs at the response-object boundary
(real Pydantic types from the SDKs, no real HTTP calls). Covers the
happy path, the fenced/preamble JSON variants the prompt explicitly
forbids but models still produce, the reasoning-content control-byte
quirk documented in nemo-inference, and the error surface.
"""

from unittest.mock import AsyncMock

import anthropic
import openai
import pytest
from nemo_memory_plugin.triage.judges import (
    AnthropicJudge,
    JudgeContext,
    OpenAICompatibleJudge,
    _extract_json,
    _parse_judgment,
)
from nemo_memory_plugin.triage.proposal import Verdict
from nemo_memory_plugin.triage.store import MemoryEntry
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entry(content: str = "Some durable fact.", corroboration: int = 1) -> MemoryEntry:
    return MemoryEntry(
        id="abc123",
        content=content,
        corroboration_count=corroboration,
    )


def _context() -> JudgeContext:
    return JudgeContext(
        store_name="pi-hermes:user",
        corpus_size=71,
        corroboration_summary="58 of 71 entries are single-observation.",
    )


def _anthropic_message(text: str) -> anthropic.types.Message:
    """Build a real Anthropic ``Message`` response object."""
    return anthropic.types.Message(
        id="msg_x",
        type="message",
        role="assistant",
        model="claude-sonnet-4-5",
        content=[anthropic.types.TextBlock(type="text", text=text, citations=None)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=anthropic.types.Usage(input_tokens=0, output_tokens=0),
    )


def _openai_completion(text: str) -> ChatCompletion:
    """Build a real OpenAI ``ChatCompletion`` response object."""
    return ChatCompletion(
        id="cc_x",
        object="chat.completion",
        created=0,
        model="m",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage(role="assistant", content=text),
            )
        ],
    )


def _good_json(verdict: str = "keep") -> str:
    return f'{{"verdict": "{verdict}", "quality": 0.8, "necessity": 0.6, "justification": "concrete and used often"}}'


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == '{"a": 1}'

    def test_fenced_json(self):
        assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_fence_without_language(self):
        assert _extract_json('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_preamble_then_object(self):
        assert _extract_json('Here is your answer:\n{"a": 1}') == '{"a": 1}'

    def test_strips_control_bytes_in_strings(self):
        # A literal U+0001 byte inside a string is rejected by json.loads,
        # but our parser strips bad C0 bytes before validation.
        raw = '{"a": "x\x01y"}'
        # Should accept on the plain path (whole-string parse).
        out = _extract_json(raw)
        assert out == raw

    def test_unparseable_raises(self):
        with pytest.raises(ValueError):
            _extract_json("not json at all")


# ---------------------------------------------------------------------------
# _parse_judgment
# ---------------------------------------------------------------------------


class TestParseJudgment:
    def test_happy_path(self):
        j = _parse_judgment(_good_json(), model="sonnet", elapsed_sec=1.2)
        assert j.model == "sonnet"
        assert j.verdict == Verdict.KEEP
        assert j.quality == pytest.approx(0.8)
        assert j.necessity == pytest.approx(0.6)
        assert j.elapsed_sec == 1.2
        assert j.justification == "concrete and used often"

    def test_all_five_verdict_values_parse(self):
        for v in ("keep", "promote_to_prompt", "refine", "merge", "drop"):
            j = _parse_judgment(_good_json(verdict=v), model="m", elapsed_sec=0)
            assert j.verdict.value == v

    def test_verdict_is_normalized_to_lowercase(self):
        j = _parse_judgment(
            '{"verdict": "KEEP", "quality": 0.5, "necessity": 0.5, "justification": ""}',
            model="m",
            elapsed_sec=0,
        )
        assert j.verdict == Verdict.KEEP

    def test_scores_clamped_to_unit_interval(self):
        j = _parse_judgment(
            '{"verdict": "keep", "quality": 1.5, "necessity": -0.3, "justification": ""}',
            model="m",
            elapsed_sec=0,
        )
        assert j.quality == 1.0
        assert j.necessity == 0.0

    def test_refined_text_populated_for_refine(self):
        raw = (
            '{"verdict": "refine", "quality": 0.7, "necessity": 0.7, '
            '"justification": "tighten phrasing", "refined_text": "Concise rewrite."}'
        )
        j = _parse_judgment(raw, model="m", elapsed_sec=0)
        assert j.verdict == Verdict.REFINE
        assert j.refined_text == "Concise rewrite."

    def test_merge_with_populated_for_merge(self):
        raw = (
            '{"verdict": "merge", "quality": 0.6, "necessity": 0.4, '
            '"justification": "duplicate", "merge_with": ["other-id"]}'
        )
        j = _parse_judgment(raw, model="m", elapsed_sec=0)
        assert j.merge_with == ["other-id"]

    def test_unknown_verdict_raises(self):
        raw = '{"verdict": "delete", "quality": 0.5, "necessity": 0.5}'
        with pytest.raises(ValueError, match="invalid verdict"):
            _parse_judgment(raw, model="m", elapsed_sec=0)

    def test_missing_verdict_raises(self):
        raw = '{"quality": 0.5, "necessity": 0.5}'
        with pytest.raises(ValueError, match="invalid verdict"):
            _parse_judgment(raw, model="m", elapsed_sec=0)

    def test_missing_quality_raises(self):
        raw = '{"verdict": "keep", "necessity": 0.5}'
        with pytest.raises(ValueError, match="quality"):
            _parse_judgment(raw, model="m", elapsed_sec=0)

    def test_non_object_raises(self):
        with pytest.raises(ValueError, match="expected JSON object"):
            _parse_judgment("[1, 2, 3]", model="m", elapsed_sec=0)

    def test_handles_fenced_response(self):
        raw = f"```json\n{_good_json()}\n```"
        j = _parse_judgment(raw, model="m", elapsed_sec=0)
        assert j.verdict == Verdict.KEEP
        # raw_response preserves the fence for audit.
        assert j.raw_response == raw

    def test_handles_control_bytes_in_content(self):
        # Reasoning models sometimes embed raw C0 controls inside JSON
        # strings. The parser strips them transparently.
        raw = '{"verdict": "keep", "quality": 0.5, "necessity": 0.5, "justification": "tab\x01here is bad"}'
        j = _parse_judgment(raw, model="m", elapsed_sec=0)
        assert j.verdict == Verdict.KEEP


# ---------------------------------------------------------------------------
# AnthropicJudge
# ---------------------------------------------------------------------------


class TestAnthropicJudge:
    @pytest.mark.asyncio
    async def test_returns_parsed_judgment(self):
        client = AsyncMock(spec=anthropic.AsyncAnthropic)
        client.messages = AsyncMock()
        client.messages.create = AsyncMock(return_value=_anthropic_message(_good_json()))

        judge = AnthropicJudge(client=client, model="claude-sonnet-4-5")
        j = await judge.judge(_entry(), _context())

        assert j.model == "claude-sonnet-4-5"
        assert j.verdict == Verdict.KEEP
        assert j.elapsed_sec >= 0
        # Verify the call shape: system + user message, correct model.
        call = client.messages.create.await_args
        assert call is not None
        assert call.kwargs["model"] == "claude-sonnet-4-5"
        assert call.kwargs["system"]
        assert call.kwargs["messages"][0]["role"] == "user"
        assert "durable memory entry" in call.kwargs["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_empty_content_raises(self):
        # A message with no text blocks should surface as ValueError, not
        # AttributeError or IndexError.
        empty = anthropic.types.Message(
            id="msg",
            type="message",
            role="assistant",
            model="m",
            content=[],
            stop_reason="end_turn",
            stop_sequence=None,
            usage=anthropic.types.Usage(input_tokens=0, output_tokens=0),
        )
        client = AsyncMock(spec=anthropic.AsyncAnthropic)
        client.messages = AsyncMock()
        client.messages.create = AsyncMock(return_value=empty)
        judge = AnthropicJudge(client=client)
        with pytest.raises(ValueError, match="no text blocks"):
            await judge.judge(_entry(), _context())


# ---------------------------------------------------------------------------
# OpenAICompatibleJudge
# ---------------------------------------------------------------------------


class TestOpenAICompatibleJudge:
    @pytest.mark.asyncio
    async def test_returns_parsed_judgment(self):
        client = AsyncMock(spec=openai.AsyncOpenAI)
        client.chat = AsyncMock()
        client.chat.completions = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=_openai_completion(_good_json("drop")))

        judge = OpenAICompatibleJudge(client=client, model="nvidia/nemotron-3-nano-30b-a3b")
        j = await judge.judge(_entry(corroboration=3), _context())

        assert j.model == "nvidia/nemotron-3-nano-30b-a3b"
        assert j.verdict == Verdict.DROP
        # Verify the call shape: system + user, correct model, max_tokens set.
        call = client.chat.completions.create.await_args
        assert call is not None
        assert call.kwargs["model"] == "nvidia/nemotron-3-nano-30b-a3b"
        assert call.kwargs["messages"][0]["role"] == "system"
        assert call.kwargs["messages"][1]["role"] == "user"
        # Corroboration count is interpolated into the user message.
        assert "3 independent session" in call.kwargs["messages"][1]["content"]

    @pytest.mark.asyncio
    async def test_empty_content_raises(self):
        client = AsyncMock(spec=openai.AsyncOpenAI)
        client.chat = AsyncMock()
        client.chat.completions = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=_openai_completion(""))
        judge = OpenAICompatibleJudge(client=client, model="m")
        with pytest.raises(ValueError, match="empty content"):
            await judge.judge(_entry(), _context())

    @pytest.mark.asyncio
    async def test_no_choices_raises(self):
        empty = ChatCompletion(
            id="cc_x",
            object="chat.completion",
            created=0,
            model="m",
            choices=[],
        )
        client = AsyncMock(spec=openai.AsyncOpenAI)
        client.chat = AsyncMock()
        client.chat.completions = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=empty)
        judge = OpenAICompatibleJudge(client=client, model="m")
        with pytest.raises(ValueError, match="no choices"):
            await judge.judge(_entry(), _context())
