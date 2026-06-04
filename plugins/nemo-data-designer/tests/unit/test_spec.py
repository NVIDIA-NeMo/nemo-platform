# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile

import data_designer.config as dd
import pandas as pd
import pytest
from nemo_data_designer_plugin.functions._types import PreviewSpec
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


def test_dataframe_seeds_are_rejected_with_clear_error() -> None:
    config = DataDesignerJobConfig(
        num_records=42,
        config=dd.DataDesignerConfig(
            columns=[dd.ExpressionColumnConfig(name="value", expr="1")],
            seed_config=dd.SeedConfig(
                source=dd.DataFrameSeedSource(df=pd.DataFrame(data={"value": [1, 2, 3]})),
            ),
        ),
    )
    payload = config.model_dump(mode="json")

    with pytest.raises(ValidationError) as job_exc_info:
        DataDesignerJobConfig.model_validate(payload)
    with pytest.raises(ValidationError) as preview_exc_info:
        PreviewSpec.model_validate({"config": payload["config"]})

    assert "Dataframe seed sources" in str(job_exc_info.value) or "seed_type=hf" in str(job_exc_info.value)
    assert "missing" not in str(job_exc_info.value)
    assert "Dataframe seed sources" in str(preview_exc_info.value) or "seed_type=hf" in str(preview_exc_info.value)
    assert "missing" not in str(preview_exc_info.value)


def test_local_file_seeds_are_rejected() -> None:
    with tempfile.NamedTemporaryFile(suffix=".parquet") as tmpfile:
        config = DataDesignerJobConfig(
            num_records=42,
            config=dd.DataDesignerConfig(
                columns=[dd.ExpressionColumnConfig(name="value", expr="1")],
                seed_config=dd.SeedConfig(
                    source=dd.LocalFileSeedSource(path=tmpfile.name),
                ),
            ),
        )
        payload = config.model_dump(mode="json")

        with pytest.raises(ValidationError):
            DataDesignerJobConfig.model_validate(payload)
        with pytest.raises(ValidationError):
            PreviewSpec.model_validate({"config": payload["config"]})
