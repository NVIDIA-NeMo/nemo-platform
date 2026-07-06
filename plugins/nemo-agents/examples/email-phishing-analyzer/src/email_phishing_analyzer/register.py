# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from NeMo-Agent-Toolkit:
# examples/evaluation_and_profiling/email_phishing_analyzer/src/nat_email_phishing_analyzer/register.py
#
# Install this package (``uv pip install -e plugins/nemo-agents/examples/email-phishing-analyzer``)
# so NAT discovers the ``nat.components`` entry point and both the
# ``_type: email_phishing_analyzer`` tool and the ``_type: email_phishing_classification``
# evaluator become available.

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

# Importing the evaluator module triggers its ``@register_evaluator`` decorator so
# ``_type: email_phishing_classification`` resolves when NAT loads this entry point.
from . import classification_evaluator  # noqa: F401  (registration side effect)
from .prompt import phishing_prompt
from .utils import smart_parse

logger = logging.getLogger(__name__)


class EmailPhishingAnalyzerConfig(FunctionBaseConfig, OptimizableMixin, name="email_phishing_analyzer"):
    llm: LLMRef = Field(description="The LLM to use for email phishing analysis.")
    prompt: str = OptimizableField(
        description="The prompt template for analyzing email phishing. Use {body} to insert the email text.",
        default=phishing_prompt,
        space=SearchSpace(
            is_prompt=True,
            prompt_purpose="Allow an LLM to look at an email body and determine if it is a phishing attempt.",
        ),
    )


@register_function(config_type=EmailPhishingAnalyzerConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def email_phishing_analyzer(config: EmailPhishingAnalyzerConfig, builder: Builder) -> Any:
    """Register the email phishing analysis tool."""

    async def _analyze_email_phishing(text: str) -> str:
        """Analyze an email body for signs of phishing using an LLM.

        Args:
            text: The email body text to analyze.

        Returns:
            A JSON string with ``is_likely_phishing`` and ``explanation`` fields.
        """
        llm = await builder.get_llm(llm_name=config.llm, wrapper_type=LLMFrameworkEnum.LANGCHAIN)

        try:
            response = await llm.ainvoke(config.prompt.replace("{body}", text))
            response = str(response.content)
        except Exception as e:
            logger.error("Error during LLM prediction: %s", e)
            return f"Error: LLM prediction failed {e}"

        try:
            analysis = smart_parse(response)
            result = {
                "is_likely_phishing": analysis.get("is_likely_phishing", False),
                "explanation": analysis.get("explanation", "No detailed explanation provided"),
            }
            return json.dumps(result)
        except json.JSONDecodeError:
            return "Error: Could not parse LLM response as JSON"

    yield FunctionInfo.from_fn(
        _analyze_email_phishing,
        description=(
            "This tool analyzes email content to detect signs of phishing attempts. It evaluates factors "
            "like urgency, generic greetings, grammar mistakes, unusual requests, and emotional manipulation."
        ),
    )
