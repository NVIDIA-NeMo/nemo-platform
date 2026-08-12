# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Capability tools for the email security analyst.

One tool per thing an analyst can ask for. The agent picks between them from the operator's
question, which is the behavior this sample exists to demonstrate -- so the ``description`` on each
tool matters as much as its prompt: it is the only routing signal the model gets.

Every tool belongs in the workflow's ``return_direct`` list. That ends the graph on the tool result
instead of running a second generation over it, which is what makes each prompt's first-line
contract a guarantee rather than a hope.
"""

import asyncio
import logging
from typing import Any

from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.component_ref import LLMRef
from nat.data_models.function import FunctionBaseConfig
from nat.data_models.optimizable import OptimizableField, OptimizableMixin, SearchSpace
from pydantic import Field

from .prompt import (
    draft_warning_prompt,
    review_messages_prompt,
    trace_thread_prompt,
    triage_message_prompt,
)

logger = logging.getLogger(__name__)

_PROMPT_FIELD_DESCRIPTION = "The prompt template for this capability. Use {body} to insert the material."


async def _invoke_llm(config: Any, builder: Builder, text: str) -> str:
    """Run this tool's prompt over the supplied material."""
    llm = await builder.get_llm(llm_name=config.llm, wrapper_type=LLMFrameworkEnum.LANGCHAIN)

    try:
        response = await asyncio.wait_for(llm.ainvoke(config.prompt.replace("{body}", text)), timeout=60)
        return str(response.content)
    except Exception as e:
        logger.error("LLM prediction failed", exc_info=e)
        raise RuntimeError("LLM prediction failed") from e


class ReviewMessagesConfig(FunctionBaseConfig, name="review_messages"):
    _type: str = "review_messages"
    llm: LLMRef = Field(description="The LLM to use for the general review.")
    prompt: str = Field(default=review_messages_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=ReviewMessagesConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def review_messages(config: ReviewMessagesConfig, builder: Builder) -> Any:
    """Register the no-question general review tool."""

    async def _review_messages(text: str) -> str:
        """Review selected messages and report which to quarantine."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _review_messages,
        description=(
            "Use this when the analyst selected one or more messages but asked no specific "
            "question. Reviews every selected message and reports which to quarantine, plus a "
            "verdict, attack type, indicators and recommended action for each. This is the default "
            "when there is no question to answer."
        ),
    )


class TriageMessageConfig(FunctionBaseConfig, OptimizableMixin, name="triage_message"):
    _type: str = "triage_message"
    llm: LLMRef = Field(description="The LLM to use for verdict triage.")
    prompt: str = OptimizableField(
        description=_PROMPT_FIELD_DESCRIPTION,
        default=triage_message_prompt,
        space=SearchSpace(
            is_prompt=True,
            prompt_purpose=(
                "Allow an LLM to decide whether an email is phishing or benign and explain the "
                "signals behind the verdict."
            ),
        ),
    )


@register_function(config_type=TriageMessageConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def triage_message(config: TriageMessageConfig, builder: Builder) -> Any:
    """Register the phishing/benign verdict tool."""

    async def _triage_message(text: str) -> str:
        """Decide whether a message is phishing or benign."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _triage_message,
        description=(
            "Use this when the analyst asks whether a single message is legitimate, whether it is "
            "phishing, or whether they should trust it or act on it. Answers with a phishing or "
            "benign verdict and the reasoning behind it."
        ),
    )


class TraceThreadConfig(FunctionBaseConfig, name="trace_thread"):
    _type: str = "trace_thread"
    llm: LLMRef = Field(description="The LLM to use for thread analysis.")
    prompt: str = Field(default=trace_thread_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=TraceThreadConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def trace_thread(config: TraceThreadConfig, builder: Builder) -> Any:
    """Register the thread injection-point tool."""

    async def _trace_thread(text: str) -> str:
        """Find where an attacker entered a reply thread."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _trace_thread,
        description=(
            "Use this when the analyst asks where a conversation went wrong, where an attacker "
            "entered a thread, or which message in a sequence is the malicious one. Answers with "
            "the position of that message."
        ),
    )


class DraftWarningConfig(FunctionBaseConfig, name="draft_warning"):
    _type: str = "draft_warning"
    llm: LLMRef = Field(description="The LLM to use for drafting staff communications.")
    prompt: str = Field(default=draft_warning_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=DraftWarningConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def draft_warning(config: DraftWarningConfig, builder: Builder) -> Any:
    """Register the staff warning drafting tool."""

    async def _draft_warning(text: str) -> str:
        """Draft a short warning to send to staff."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _draft_warning,
        description=(
            "Use this when the analyst asks for a message to send to other people -- a warning to "
            "staff, a notice to the team, or an alert about an email doing the rounds. Drafts the "
            "communication itself."
        ),
    )
