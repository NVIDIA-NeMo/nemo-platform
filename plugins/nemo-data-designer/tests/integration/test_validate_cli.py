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


def _write_local_first_config(tmp_path: Path) -> Path:
    """Config that uses an IGW-only provider — must validate clean for local + remote."""
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
        dd.LLMTextColumnConfig(name="story", prompt="About {{{{ foo }}}}", model_alias="text")
    )
    return builder
""",
        name="igw_provider_config.py",
    )


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


def test_validate_local_only_succeeds_with_igw_provider(tmp_path: Path) -> None:
    config_path = _write_local_first_config(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path), "--execution-context", "local"],
            client_context,
        )

    assert result.exit_code == 0, result.output
    assert "Local execution" in result.output
    assert "Configuration is valid" in result.output


def test_validate_local_only_fails_for_unknown_alias(tmp_path: Path) -> None:
    config_path = _write_unknown_alias_config(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path), "--execution-context", "local"],
            client_context,
        )

    assert result.exit_code == 1, result.output
    assert "not-a-real-alias" in result.output


def test_validate_remote_only_aggregates_multiple_errors(tmp_path: Path) -> None:
    """A single ``validate`` invocation surfaces both the unsupported seed type
    and the tool-config rejection without short-circuiting.
    """
    config_path = _write_unsupported_seed_with_tool_configs(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path), "--execution-context", "remote"],
            client_context,
        )

    assert result.exit_code == 1, result.output
    output = result.output
    assert "Remote execution" in output
    assert "Tool configs" in output
    # Either the seed-type or DataFrame rejection message must surface alongside.
    assert ("seed" in output.lower()) or ("DataFrame" in output) or ("df" in output)


def test_validate_default_runs_every_context(tmp_path: Path) -> None:
    config_path = _write_local_first_config(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path)],
            client_context,
        )

    assert result.exit_code == 0, result.output
    assert "Local execution" in result.output
    assert "Remote execution" in result.output


def test_validate_default_exits_nonzero_when_any_context_fails(tmp_path: Path) -> None:
    """An IGW-unknown provider validates fine for local (after IGW lookup fails),
    but explicit local-only success isn't the point here — we just want to see
    that omitting the flag exits nonzero when *any* context fails.
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


def test_validate_json_output_round_trips(tmp_path: Path) -> None:
    config_path = _write_local_first_config(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path), "--execution-context", "local", "--output", "json"],
            client_context,
        )

    assert result.exit_code == 0, result.output
    payload = u.parse_cli_json_object(result.output)
    assert payload["ok"] is True
    assert isinstance(payload["results"], list)
    assert payload["results"][0]["context"] == "local"
    assert payload["results"][0]["ok"] is True
    assert payload["results"][0]["errors"] == []
    # Confirm the surface is a JSON object, not the rich text rendering.
    assert "Local execution" not in result.output


def test_validate_json_output_reports_failures(tmp_path: Path) -> None:
    config_path = _write_unsupported_seed_with_tool_configs(tmp_path)

    with (
        u.make_mock_client_context() as client_context,
        u.setup_mock_providers(client_context),
    ):
        result = u.invoke_cli(
            ["validate", str(config_path), "--execution-context", "remote", "--output", "json"],
            client_context,
        )

    # Pull JSON from the output, ignoring any leading non-JSON cruft.
    assert result.exit_code == 1
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    [remote_result] = payload["results"]
    assert remote_result["context"] == "remote"
    assert remote_result["ok"] is False
    assert len(remote_result["errors"]) >= 2
    for err in remote_result["errors"]:
        # Each error is a structured object carrying at least a message string.
        assert isinstance(err["message"], str)
        assert err["message"]
