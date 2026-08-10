# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import nemo_data_designer_plugin.testing.utils as u
import pytest

pytestmark = pytest.mark.integration


def test_preview_local_verb_is_not_registered(tmp_path: Path) -> None:
    config_path = _write_sampler_config(tmp_path)

    with u.make_mock_client_context(workspace="default") as client_context:
        result = u.invoke_cli(["preview", "run", str(config_path)], client_context)

    assert result.exit_code != 0
    assert "No such command" in result.output


def test_create_local_verb_is_not_registered(tmp_path: Path) -> None:
    config_path = _write_sampler_config(tmp_path)

    with u.make_mock_client_context(workspace="default") as client_context:
        result = u.invoke_cli(["create", "run", str(config_path)], client_context)

    assert result.exit_code != 0
    assert "No such command" in result.output


def _write_sampler_config(tmp_path: Path) -> Path:
    return u.write_config_file(
        tmp_path,
        """
import data_designer.config as dd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder()
    builder.add_column(
        dd.SamplerColumnConfig(
            name="topic",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["math"]),
        )
    )
    builder.add_column(dd.ExpressionColumnConfig(name="description", expr="Topic: {{ topic }}"))
    return builder
""",
        name="sampler_config.py",
    )
