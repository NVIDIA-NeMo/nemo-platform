# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from typing import Any, TypeAlias

from nemo_platform.types.guardrail import (
    ActivatedRail as PlatformActivatedRail,
)
from nemo_platform.types.guardrail import (
    GenerationLog as PlatformGenerationLog,
)
from nemo_platform.types.guardrail import (
    GenerationStats as PlatformGenerationStats,
)
from nemo_platform.types.guardrail import (
    LLMCallInfo as PlatformLLMCallInfo,
)
from nemoguardrails.logging.explain import LLMCallInfo as LibraryLLMCallInfo
from nemoguardrails.rails.llm.options import (
    ActivatedRail as LibraryActivatedRail,
)
from nemoguardrails.rails.llm.options import (
    GenerationLog as LibraryGenerationLog,
)
from nemoguardrails.rails.llm.options import (
    GenerationResponse as LibraryGenerationResponse,
)
from nemoguardrails.rails.llm.options import (
    GenerationStats as LibraryGenerationStats,
)

GenerateAsyncResponse: TypeAlias = (
    str | dict[str, Any] | tuple[dict[str, Any], dict[str, Any]] | LibraryGenerationResponse
)


class GenerationResponseMapper:
    """Transforms nemoguardrails Generation-related models into the corresponding nemo_platform models."""

    @staticmethod
    def parse(value: GenerateAsyncResponse) -> LibraryGenerationResponse:
        """Parse a `LLMRails.generate_async` response into a GenerationResponse object."""
        if isinstance(value, LibraryGenerationResponse):
            return value

        # Accept plain string payloads as shorthand for a response content.
        if isinstance(value, str):
            return LibraryGenerationResponse.model_validate({"response": value})

        # Some callers can provide a tuple of message dictionaries.
        if isinstance(value, tuple):
            return LibraryGenerationResponse.model_validate({"response": list(value)})

        return LibraryGenerationResponse.model_validate(value)

    @staticmethod
    def to_platform_generation_log(log: LibraryGenerationLog | None) -> PlatformGenerationLog | None:
        """Translate nemoguardrails GenerationLog into platform GenerationLog."""
        if log is None:
            return None

        return PlatformGenerationLog(
            activated_rails=GenerationResponseMapper.to_platform_activated_rails(log.activated_rails),
            llm_calls=GenerationResponseMapper.to_platform_llm_calls(log.llm_calls),
            internal_events=GenerationResponseMapper.to_platform_internal_events(log.internal_events),
            colang_history=log.colang_history,
            stats=GenerationResponseMapper.to_platform_generation_stats(log.stats),
        )

    @staticmethod
    def to_platform_generation_stats(stats: LibraryGenerationStats | None) -> PlatformGenerationStats | None:
        """Translate nemoguardrails GenerationStats into platform GenerationStats."""
        if stats is None:
            return None

        return PlatformGenerationStats.model_validate(stats.model_dump(exclude_none=True))

    @staticmethod
    def to_platform_activated_rails(
        rails: list[LibraryActivatedRail] | None,
    ) -> list[PlatformActivatedRail] | None:
        """Translate nemoguardrails ActivatedRail list into platform ActivatedRail list."""
        if rails is None:
            return None

        return [PlatformActivatedRail.model_validate(rail.model_dump(exclude_none=True)) for rail in rails]

    @staticmethod
    def to_platform_llm_calls(
        llm_calls: list[LibraryLLMCallInfo] | None,
    ) -> list[PlatformLLMCallInfo] | None:
        """Translate nemoguardrails LLMCallInfo list into platform LLMCallInfo list."""
        if llm_calls is None:
            return None

        return [PlatformLLMCallInfo.model_validate(llm_call.model_dump(exclude_none=True)) for llm_call in llm_calls]

    @staticmethod
    def to_platform_internal_events(events: list[dict[str, object]] | None) -> list[dict[str, object]] | None:
        """Translate nemoguardrails internal events into JSON-compatible platform log data."""
        if events is None:
            return None

        # Tool-call events can contain dict subclasses (for example AttributeDict)
        # from nemoguardrails internals. Normalize them to plain JSON data before
        # validating into the platform SDK model.
        return PlatformGenerationLog.model_validate(
            {"internal_events": json.loads(json.dumps(events))}
        ).internal_events
