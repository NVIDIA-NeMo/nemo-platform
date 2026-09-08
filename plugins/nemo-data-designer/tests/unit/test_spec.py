# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile

import data_designer.config as dd
import pandas as pd
import pytest
from nemo_data_designer_plugin.jobs.spec import DataDesignerJobConfig
from pydantic import ValidationError


def test_dataframe_seeds_are_rejected() -> None:
    config = DataDesignerJobConfig(
        num_records=42,
        config=dd.DataDesignerConfig(
            columns=[
                dd.LLMTextColumnConfig(
                    name="storytime",
                    model_alias="text",
                    prompt="Tell me a story",
                )
            ],
            seed_config=dd.SeedConfig(
                source=dd.DataFrameSeedSource(df=pd.DataFrame()),
            ),
        ),
    )

    # The before-validator translates plugin errors into ``ValueError`` so that
    # Pydantic wraps them in ``ValidationError`` (the v2 contract). Earlier
    # versions raised the plugin's ``NDDInvalidConfigError`` straight out of
    # ``model_validate``, which Pydantic does not wrap and which therefore
    # escaped framework-level ``except ValidationError`` handlers.
    with pytest.raises(ValidationError) as exc_info:
        DataDesignerJobConfig.model_validate(config.model_dump())

    assert "seed data" in str(exc_info.value)


def test_local_file_seeds_are_rejected() -> None:
    with tempfile.NamedTemporaryFile(suffix=".parquet") as tmpfile:
        config = DataDesignerJobConfig(
            num_records=42,
            config=dd.DataDesignerConfig(
                columns=[
                    dd.LLMTextColumnConfig(
                        name="storytime",
                        model_alias="text",
                        prompt="Tell me a story",
                    )
                ],
                seed_config=dd.SeedConfig(
                    source=dd.LocalFileSeedSource(path=tmpfile.name),
                ),
            ),
        )

        with pytest.raises(ValidationError) as exc_info:
            DataDesignerJobConfig.model_validate(config.model_dump())

        assert "seed data" in str(exc_info.value)
