# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data Designer config builder for synthetic eval data.

Run via the venv Python until `nemo data-designer preview-local` is available
in the installed CLI version (currently 2.1.0 ships only `data-designer jobs`):

    .venv/bin/python agents/<name>.dd.py

When `preview-local` lands, swap the bottom of this file for:

    # nemo data-designer preview-local agents/<name>.dd.py --num-records 10

Substitute:
    AGENT_DESCRIPTION  one-sentence agent role from the spec
    CATEGORIES         the spec's category list
    MODEL              API-Catalog format with slashes (NOT entity-name format)
    PROVIDER           workspace/provider-name as registered in nemo
"""

import data_designer.config as dd
from nemo_platform_plugin.client.client import NemoClient

AGENT_DESCRIPTION = "<one-sentence role from spec>"
CATEGORIES: list[str | int | float] = ["<category-1>", "<category-2>", "<category-3>"]
MODEL = "meta/llama-3.3-70b-instruct"
PROVIDER = "default/nim-llm"


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder(
        model_configs=[
            dd.ModelConfig(
                alias="generator",
                model=MODEL,
                provider=PROVIDER,
                skip_health_check=True,
            )
        ]
    )

    builder.add_column(
        dd.SamplerColumnConfig(
            name="category",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=CATEGORIES),
        )
    )

    builder.add_column(
        dd.LLMTextColumnConfig(
            name="user_question",
            model_alias="generator",
            prompt=(
                "Generate a realistic user question about {{ category }} for an agent that "
                f"{AGENT_DESCRIPTION}. The question should sound like a real employee asking for help."
            ),
        )
    )

    builder.add_column(
        dd.LLMTextColumnConfig(
            name="expected_response",
            model_alias="generator",
            prompt=(
                "Write the ideal agent response to this question: {{ user_question }}. "
                "The response should be helpful, accurate, and professional."
            ),
        )
    )

    return builder


if __name__ == "__main__":
    client = NemoClient(base_url="http://localhost:8080", workspace="default")
    builder = load_config_builder()
    results = client.data_designer.preview(builder, num_records=10)
    results.display_sample_record()
