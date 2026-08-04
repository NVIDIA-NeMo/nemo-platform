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
import json
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
    analyze_headers_prompt,
    assess_severity_prompt,
    attribute_attack_prompt,
    check_url_brand_prompt,
    draft_warning_prompt,
    incident_response_prompt,
    review_messages_prompt,
    trace_thread_prompt,
    triage_batch_prompt,
    triage_message_prompt,
)
from .utils import extract_iocs

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


class TriageBatchConfig(FunctionBaseConfig, name="triage_batch"):
    _type: str = "triage_batch"
    llm: LLMRef = Field(description="The LLM to use for batch quarantine decisions.")
    prompt: str = Field(default=triage_batch_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=TriageBatchConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def triage_batch(config: TriageBatchConfig, builder: Builder) -> Any:
    """Register the batch quarantine-decision tool."""

    async def _triage_batch(text: str) -> str:
        """Name which of the selected messages to quarantine."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _triage_batch,
        description=(
            "Use this when the analyst asks which of several selected messages should be "
            "quarantined, blocked, or removed. Answers with the positions of those messages."
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


class AssessSeverityConfig(FunctionBaseConfig, name="assess_severity"):
    _type: str = "assess_severity"
    llm: LLMRef = Field(description="The LLM to use for severity rating.")
    prompt: str = Field(default=assess_severity_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=AssessSeverityConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def assess_severity(config: AssessSeverityConfig, builder: Builder) -> Any:
    """Register the threat severity rating tool."""

    async def _assess_severity(text: str) -> str:
        """Rate how serious a threat is."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _assess_severity,
        description=(
            "Use this when the analyst asks how serious, severe, urgent or high-priority a "
            "message is, or how it should be triaged relative to other work. Answers with a "
            "low, medium or high severity rating."
        ),
    )


class AttributeAttackConfig(FunctionBaseConfig, name="attribute_attack"):
    _type: str = "attribute_attack"
    llm: LLMRef = Field(description="The LLM to use for attack attribution.")
    prompt: str = Field(default=attribute_attack_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=AttributeAttackConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def attribute_attack(config: AttributeAttackConfig, builder: Builder) -> Any:
    """Register the attack-type attribution tool."""

    async def _attribute_attack(text: str) -> str:
        """Name the attack category for a message."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _attribute_attack,
        description=(
            "Use this when the analyst asks what kind or category of attack a message is, or how "
            "to classify the threat. Names one of business email compromise, credential theft, "
            "malware, spam, or benign."
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


class AnalyzeHeadersConfig(FunctionBaseConfig, name="analyze_headers"):
    _type: str = "analyze_headers"
    llm: LLMRef = Field(description="The LLM to use for header analysis.")
    prompt: str = Field(default=analyze_headers_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=AnalyzeHeadersConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def analyze_headers(config: AnalyzeHeadersConfig, builder: Builder) -> Any:
    """Register the SMTP authentication header tool."""

    async def _analyze_headers(text: str) -> str:
        """Name which sender authentication check failed."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _analyze_headers,
        description=(
            "Use this when the analyst asks about raw message headers, sender authentication, or "
            "why a message failed authentication. Names which of SPF, DKIM or DMARC failed."
        ),
    )


class CheckUrlBrandConfig(FunctionBaseConfig, name="check_url_brand"):
    _type: str = "check_url_brand"
    llm: LLMRef = Field(description="The LLM to use for lookalike domain analysis.")
    prompt: str = Field(default=check_url_brand_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=CheckUrlBrandConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def check_url_brand(config: CheckUrlBrandConfig, builder: Builder) -> Any:
    """Register the brand impersonation tool."""

    async def _check_url_brand(text: str) -> str:
        """Name the brand a lookalike domain impersonates."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _check_url_brand,
        description=(
            "Use this when the analyst asks about a link or domain -- who it is pretending to be, "
            "whether it is a lookalike, or which brand it impersonates. Answers with the brand name."
        ),
    )


class IncidentResponseConfig(FunctionBaseConfig, name="incident_response"):
    _type: str = "incident_response"
    llm: LLMRef = Field(description="The LLM to use for incident response planning.")
    prompt: str = Field(default=incident_response_prompt, description=_PROMPT_FIELD_DESCRIPTION)


@register_function(config_type=IncidentResponseConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def incident_response(config: IncidentResponseConfig, builder: Builder) -> Any:
    """Register the post-incident remediation tool."""

    async def _incident_response(text: str) -> str:
        """Give ordered remediation steps for an incident."""
        return await _invoke_llm(config, builder, text)

    yield FunctionInfo.from_fn(
        _incident_response,
        description=(
            "Use this when something has already gone wrong -- someone clicked a link, entered "
            "credentials, sent a payment, or opened an attachment -- and the analyst needs to know "
            "what to do now. Gives ordered remediation steps."
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


class ExtractIocsConfig(FunctionBaseConfig, name="extract_iocs"):
    _type: str = "extract_iocs"


@register_function(config_type=ExtractIocsConfig)
async def extract_iocs_function(config: ExtractIocsConfig, builder: Builder) -> Any:
    """Register the deterministic IOC extraction tool."""

    async def _extract_iocs(text: str) -> str:
        """
        Extract indicators of compromise from text.

        Args:
            text: The email body, headers, or free text to scan

        Returns:
            JSON string with sorted, de-duplicated urls and domains lists
        """
        return json.dumps(extract_iocs(text))

    yield FunctionInfo.from_fn(
        _extract_iocs,
        description=(
            "Use this when the analyst asks only for the indicators of compromise, URLs, links or "
            "domains in a message, with no judgement attached. Deterministic, no model call."
        ),
    )
