# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# /// script
# dependencies = [
#   "data-designer",
# ]
# ///
import data_designer.config as dd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    config_builder = dd.DataDesignerConfigBuilder(
        model_configs=[
            dd.ModelConfig(
                alias="text",
                model="meta/llama-3.1-8b-instruct",
                provider="default/nvidia-build",
                inference_parameters=dd.ChatCompletionInferenceParams(),
            ),
        ],
    )

    # Diversity driver — sampled but dropped from final output
    config_builder.add_column(
        dd.SamplerColumnConfig(
            name="category",
            drop=True,
            sampler_type="category",
            params=dd.CategorySamplerParams(
                values=[
                    "Science",
                    "History",
                    "Geography",
                    "Art & Literature",
                    "Sports",
                    "Pop Culture",
                    "Nature & Animals",
                ],
            ),
        )
    )

    config_builder.add_column(
        dd.LLMTextColumnConfig(
            name="question",
            model_alias="text",
            system_prompt=(
                "You are a trivia question writer. Write clear, specific, and engaging trivia questions. "
                "Output only the question text — no preamble, no numbering, no answer."
            ),
            prompt=(
                "Write a single trivia question in the category: {{ category }}. "
                "The question should have one unambiguous correct answer."
            ),
        )
    )

    config_builder.add_column(
        dd.LLMTextColumnConfig(
            name="answer",
            model_alias="text",
            system_prompt=(
                "You are a trivia answer provider. Give concise, accurate answers. "
                "Output only the answer — no explanation, no full sentence unless required for clarity."
            ),
            prompt="Answer this trivia question concisely: {{ question }}",
        )
    )

    return config_builder
