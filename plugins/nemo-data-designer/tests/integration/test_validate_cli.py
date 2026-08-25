# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for ``nemo data-designer validate``.

The CLI command is a thin shell over
:func:`nemo_data_designer_plugin.sdk.validation.validate_config`; these tests
assert the public CLI behavior (stdout / exit code / JSON shape) against an
in-process mock platform.
"""

from __future__ import annotations

import json
from pathlib import Path

import nemo_data_designer_plugin.testing.utils as u
import pytest

pytestmark = pytest.mark.integration


def _write_unknown_alias_config(tmp_path: Path) -> Path:
    return u.write_config_file(
        tmp_path,
        f"""
import data_designer.config as dd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder(
        model_configs=[
            dd.ModelConfig(
                alias="text", model={u.ENABLED_MODEL_NAME!r},
                provider={u.OPEN_PROVIDER_NAME!r},
            )
        ]
    )
    builder.add_column(
        dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )
    builder.add_column(
        dd.LLMTextColumnConfig(name="x", prompt="hi", model_alias="not-a-real-alias")
    )
    return builder
""",
        name="unknown_alias_config.py",
    )


def _write_unsupported_seed_with_tool_configs(tmp_path: Path) -> Path:
    """Config that violates two remote rules at once: tool configs + df seed."""
    return u.write_config_file(
        tmp_path,
        f"""
import data_designer.config as dd
import pandas as pd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder(
        model_configs=[
            dd.ModelConfig(
                alias="text", model={u.ENABLED_MODEL_NAME!r},
                provider={u.OPEN_PROVIDER_NAME!r},
            )
        ],
        tool_configs=[dd.ToolConfig(tool_alias="hello", providers=[{u.OPEN_PROVIDER_NAME!r}])],
    )
    builder.with_seed_dataset(dd.DataFrameSeedSource(df=pd.DataFrame({{"a": [1, 2, 3]}})))
    builder.add_column(
        dd.SamplerColumnConfig(
            name="foo",
            sampler_type=dd.SamplerType.CATEGORY,
            params=dd.CategorySamplerParams(values=["a", "b"]),
        )
    )
    return builder
""",
        name="multi_error_config.py",
    )


def test_validate_aggregates_multiple_errors(tmp_path: Path) -> None:
    """A single ``validate`` invocation surfaces both the unsupported seed type
    and the tool-config rejection without short-circuiting.
    """
    config_path = _write_unsupported_seed_with_tool_configs(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path)],
            client_context,
        )

    assert result.exit_code == 1, result.output
    output = result.output
    assert "Tool configs" in output
    # Either the seed-type or DataFrame rejection message must surface alongside.
    assert ("seed" in output.lower()) or ("DataFrame" in output) or ("df" in output)


def test_validate_json_output_reports_failures(tmp_path: Path) -> None:
    config_path = _write_unsupported_seed_with_tool_configs(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path), "--output", "json"],
            client_context,
        )

    # Pull JSON from the output, ignoring any leading non-JSON cruft.
    assert result.exit_code == 1
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert len(payload["errors"]) >= 2
    for err in payload["errors"]:
        # Each error is a structured object carrying at least a message string.
        assert isinstance(err["message"], str)
        assert err["message"]
