# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-model judges for the memory-triage council.

Two judge implementations cover the three council slots defined in
``DESIGN.md``:

- :class:`AnthropicJudge` for the reference slot (``claude-sonnet-4-5``).
  Uses the same async Anthropic client the surrounding
  ``improvement/analysis/llm.py`` already uses.
- :class:`OpenAICompatibleJudge` for the candidate and diversity slots
  (``nvidia/nemotron-3-nano-30b-a3b`` and ``nvidia/moonshotai/kimi-k2.6``),
  both reachable via ``inference-api.nvidia.com`` with an OpenAI-shaped
  chat-completions API.

Both classes implement the :class:`Judge` protocol so the council
orchestrator (Phase 1 ``triage.py``) treats them interchangeably.

Two repo-known quirks are handled here so callers do not have to:

1. Nemotron-Nano (and similar reasoning models) sometimes emit raw
   control bytes inside ``reasoning_content``. Our JSON parser uses
   ``strict=False`` and strips C0 controls before parsing as a fallback.
   See ``.agents/skills/nemo-inference/SKILL.md``.
2. Models occasionally wrap JSON in fenced code blocks even when the
   system prompt says "no preamble". :func:`_extract_json` peels those
   off, mirroring the helper in ``analysis/llm.py``.
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import anthropic
import openai
from nemo_memory_plugin.triage.proposal import Judgment, Verdict
from nemo_memory_plugin.triage.store import MemoryEntry

# Lowest C0 control range, minus the three whitespace controls JSON
# already tolerates (tab \t, newline \n, carriage return \r). Anything
# else in 0x00-0x1F or the DEL byte 0x7F is invalid in standard JSON
# strings and breaks ``json.loads`` even with ``strict=False`` in some
# Python versions; strip them before parsing.
_BAD_CONTROL_BYTES = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


@dataclass
class JudgeContext:
    """Context handed to every judge for every entry.

    ``store_name`` lands in the proposal artifact for review.
    ``corpus_size`` and ``corroboration_summary`` give the judge a prior
    so it can calibrate (e.g. "58/71 entries are single-observation;
    this one is too, so it is not unusually weak").
    """

    store_name: str
    corpus_size: int
    corroboration_summary: str = ""


_SYSTEM = (
    "You are a JSON-only assistant evaluating durable memory entries for an AI agent. "
    "Output exactly one JSON object, no preamble, no markdown, no code fences."
)

_PROMPT_TEMPLATE = """You are evaluating a single durable memory entry for quality and necessity.

## Store

{store_name}: an agent memory store with {corpus_size} entries total.
{corroboration_summary}

## Entry to evaluate

[corroboration: this entry was observed in {corroboration} independent session(s)]

```
{content}
```

## Your task

Score and decide.

QUALITY (0.0 to 1.0): is the entry specific, verifiable, retrievable?
- 1.0 = concrete fact with named entities, specific commands, version numbers, or precise quotes.
- 0.5 = useful general guidance, but not unambiguously retrievable.
- 0.0 = vague, restates the obvious, or could apply to any thoughtful engineer.

NECESSITY (0.0 to 1.0): would agent behavior change if this entry were removed?
- 1.0 = removing it would change a concrete decision the agent makes.
- 0.5 = removing it would change tone but not outcomes.
- 0.0 = no behavior change; the entry restates content already in the system prompt or covered by other entries.

VERDICT (exactly one of these five values):
- "keep": entry is good as-is. If the only "improvement" you can think of is rephrasing the same content with different sentence structure, this is the correct verdict, not refine.
- "promote_to_prompt": high quality and applies broadly enough to belong in the always-on system prompt rather than being retrieved.
- "refine": ONLY when the original has a concrete defect that the refined version fixes. Provide refined_text. A defect is one of:
  - The entry combines multiple distinct topics that should be separated into their own entries.
  - The entry contains genuinely vague language where specific terms exist (e.g., "a thing" where a named entity could be used).
  - The entry is more than twice as long as needed to convey the same signal.
  Your justification MUST name which defect is being fixed. DO NOT use refine if:
  - Your refined_text conveys the same content with merely different sentence structure, word order, or voice.
  - Your refined_text drops a direct quote, specific example, or named entity that was present in the original.
  - The diff between original and refined_text is purely stylistic (synonym swaps, paraphrase, sentence reordering).
  If the original has no nameable defect and the only available "improvement" is paraphrase, return "keep".
- "merge": same signal as some other entry. Only set this if a duplicate is obvious from the entry content alone. Rare in a single-entry judge.
- "drop": not worth keeping.

## Output format

Return ONLY a JSON object with these fields. Do not include any text outside the JSON.

{{
  "verdict": "keep|promote_to_prompt|refine|merge|drop",
  "quality": 0.0,
  "necessity": 0.0,
  "justification": "one or two sentences explaining the verdict",
  "refined_text": "...only when verdict is refine; otherwise omit or set null...",
  "merge_with": []
}}
"""


def _build_prompt(entry: MemoryEntry, context: JudgeContext) -> str:
    return _PROMPT_TEMPLATE.format(
        store_name=context.store_name,
        corpus_size=context.corpus_size,
        corroboration_summary=context.corroboration_summary or "(no corpus-level corroboration summary)",
        corroboration=entry.corroboration_count,
        content=entry.content,
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Return the JSON substring from a possibly-fenced model response.

    Mirrors the helper in ``improvement/analysis/llm.py``. The model may
    return clean JSON, JSON wrapped in ```json``` fences, or JSON with
    preamble text before the first ``{``. We try each shape in turn and
    raise ``ValueError`` only when none of them parse.
    """
    stripped = text.strip()
    # Whole-string case.
    try:
        json.loads(_BAD_CONTROL_BYTES.sub("", stripped))
        return stripped
    except json.JSONDecodeError:
        pass

    # Fenced case.
    match = _FENCE_RE.search(stripped)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(_BAD_CONTROL_BYTES.sub("", candidate))
            return candidate
        except json.JSONDecodeError:
            pass

    # First-brace case (preamble before the object).
    for i, ch in enumerate(stripped):
        if ch == "{":
            candidate = stripped[i:]
            try:
                json.loads(_BAD_CONTROL_BYTES.sub("", candidate))
                return candidate
            except json.JSONDecodeError:
                break

    raise ValueError(f"could not extract JSON from response: {text[:200]!r}")


def _parse_judgment(
    raw_response: str,
    model: str,
    elapsed_sec: float,
) -> Judgment:
    """Turn a raw model response into a :class:`Judgment`.

    Raises ``ValueError`` on shape problems (unknown verdict, missing
    required field, non-numeric score). The orchestrator is responsible
    for deciding whether to retry or skip the vote. Scores are clamped
    to ``[0.0, 1.0]`` because some models return values outside the band.
    """
    json_text = _extract_json(raw_response)
    data: Any = json.loads(_BAD_CONTROL_BYTES.sub("", json_text), strict=False)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object, got {type(data).__name__}")

    try:
        verdict_str = str(data["verdict"]).strip().lower()
        verdict = Verdict(verdict_str)
    except (KeyError, ValueError) as err:
        raise ValueError(f"missing or invalid verdict in response: {data!r}") from err

    try:
        quality = float(data["quality"])
        necessity = float(data["necessity"])
    except (KeyError, TypeError, ValueError) as err:
        raise ValueError(f"missing or invalid quality/necessity in response: {data!r}") from err

    quality = max(0.0, min(1.0, quality))
    necessity = max(0.0, min(1.0, necessity))

    justification = str(data.get("justification", "")).strip()
    refined_text = data.get("refined_text")
    if refined_text is not None:
        refined_text = str(refined_text).strip() or None

    merge_with_raw = data.get("merge_with") or []
    merge_with = [str(x) for x in merge_with_raw if x]

    return Judgment(
        model=model,
        verdict=verdict,
        quality=quality,
        necessity=necessity,
        justification=justification,
        raw_response=raw_response,
        refined_text=refined_text,
        merge_with=merge_with,
        elapsed_sec=elapsed_sec,
    )


# ---------------------------------------------------------------------------
# Judge protocol + implementations
# ---------------------------------------------------------------------------


@runtime_checkable
class Judge(Protocol):
    """One model's seat at the council table."""

    model: str

    async def judge(self, entry: MemoryEntry, context: JudgeContext) -> Judgment: ...


class AnthropicJudge:
    """Reference judge slot. Uses the Anthropic Messages API.

    Defaults to ``claude-sonnet-4-5``; override via ``model`` to bench a
    different Anthropic model. ``max_tokens`` is set high enough to
    accommodate refined-text payloads on the verbose end of the
    distribution.
    """

    def __init__(
        self,
        client: anthropic.AsyncAnthropic,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 1024,
    ) -> None:
        self._client = client
        self.model = model
        self._max_tokens = max_tokens

    async def judge(self, entry: MemoryEntry, context: JudgeContext) -> Judgment:
        start = time.monotonic()
        prompt = _build_prompt(entry, context)
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.monotonic() - start

        # The Anthropic SDK returns a list of content blocks; for a JSON-
        # only response we expect a single text block. Iterate defensively
        # so a malformed response surfaces as a parse error rather than an
        # AttributeError.
        text_parts: list[str] = []
        for block in response.content:
            if isinstance(block, anthropic.types.TextBlock):
                text_parts.append(block.text)
        if not text_parts:
            raise ValueError(f"anthropic response had no text blocks: {response!r}")
        raw = "".join(text_parts)

        return _parse_judgment(raw, self.model, elapsed)


class OpenAICompatibleJudge:
    """Candidate and diversity judge slots.

    Used for any model reachable via an OpenAI-shaped chat-completions
    API. In the Phase 1 council that means ``nvidia/nemotron-3-nano-30b-a3b``
    and ``nvidia/moonshotai/kimi-k2.6``, both served by
    ``inference-api.nvidia.com``. The same class also works against any
    other OpenAI-compatible endpoint by varying the client's ``base_url``.

    ``max_tokens`` defaults to 1024 to give reasoning models the headroom
    the inference skill flags as a hard minimum for Nemotron-Nano
    (max_tokens >= ~200 to avoid truncated reasoning).
    """

    def __init__(
        self,
        client: openai.AsyncOpenAI,
        model: str,
        max_tokens: int = 1024,
    ) -> None:
        self._client = client
        self.model = model
        self._max_tokens = max_tokens

    async def judge(self, entry: MemoryEntry, context: JudgeContext) -> Judgment:
        start = time.monotonic()
        prompt = _build_prompt(entry, context)
        response = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        elapsed = time.monotonic() - start

        if not response.choices:
            raise ValueError(f"openai-compatible response had no choices: {response!r}")
        message = response.choices[0].message
        raw = message.content or ""
        if not raw:
            raise ValueError(f"openai-compatible response had empty content: {response!r}")

        return _parse_judgment(raw, self.model, elapsed)
