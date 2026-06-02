# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import nemo_data_designer_plugin.testing.utils as u
import pandas as pd
import pytest
from data_designer.cli.utils.sample_records_pager import PAGER_FILENAME
from data_designer.config.analysis.dataset_profiler import DatasetProfilerResults

pytestmark = pytest.mark.integration


def test_preview_run_saves_expected_artifacts(tmp_path: Path) -> None:
    config_path = _write_sampler_config(tmp_path)
    artifact_path = tmp_path / "preview-artifacts"

    with u.make_mock_client_context(workspace="default") as client_context:
        result = u.invoke_cli(
            [
                "preview",
                "run",
                str(config_path),
                "--num-records",
                "3",
                "--save-results",
                "--artifact-path",
                str(artifact_path),
            ],
            client_context,
        )

    assert result.exit_code == 0, result.output
    results_dir = u.find_single_preview_results_dir(artifact_path)
    dataset = u.read_saved_preview_dataset(results_dir)

    assert dataset["topic"].tolist() == ["math", "math", "math"]
    assert dataset["description"].tolist() == ["Topic: math", "Topic: math", "Topic: math"]
    assert (results_dir / "sample_records" / "record_0.html").exists()
    assert (results_dir / "sample_records" / PAGER_FILENAME).exists()


def test_preview_run_supports_local_file_seed_source(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.parquet"
    u.SEED_DATA.to_parquet(seed_path, index=False)
    config_path = u.write_config_file(
        tmp_path,
        f"""
import data_designer.config as dd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder()
    builder.with_seed_dataset(dd.LocalFileSeedSource(path={str(seed_path)!r}))
    builder.add_column(dd.ExpressionColumnConfig(name="full_name", expr={u.FULL_NAME_EXPR!r}))
    return builder
""",
        name="local_seed_config.py",
    )
    artifact_path = tmp_path / "preview-artifacts"

    with u.make_mock_client_context(workspace="default") as client_context:
        result = u.invoke_cli(
            [
                "preview",
                "run",
                str(config_path),
                "--num-records",
                "3",
                "--save-results",
                "--artifact-path",
                str(artifact_path),
            ],
            client_context,
        )

    assert result.exit_code == 0, result.output
    dataset = u.read_saved_preview_dataset(u.find_single_preview_results_dir(artifact_path))
    assert set(dataset["full_name"].tolist()) == u.FULL_NAMES


def test_preview_run_rejects_dataframe_seed_with_clear_error(tmp_path: Path) -> None:
    config_path = u.write_config_file(
        tmp_path,
        """
import data_designer.config as dd
import pandas as pd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder()
    builder.with_seed_dataset(dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})))
    builder.add_column(dd.ExpressionColumnConfig(name="value", expr="{{ a }}"))
    return builder
""",
        name="dataframe_seed_config.py",
    )

    with u.make_mock_client_context(workspace="default") as client_context:
        result = u.invoke_cli(
            ["preview", "run", str(config_path), "--num-records", "3"],
            client_context,
        )

    # The helpful diagnostic must reach the user via stdout/stderr, not just via
    # the raw exception object. Earlier versions of this plugin returned a raw
    # ``NDDInvalidConfigError`` from a Pydantic before-validator; Pydantic v2 only
    # wraps ``ValueError`` / ``AssertionError`` / ``PydanticCustomError`` from
    # before-validators, so the original exception escaped ``model_validate`` raw,
    # past the framework's ``except ValidationError`` clause, leaving the user
    # with empty output and exit code 1. The validator now translates plugin
    # errors into ``ValueError`` so Pydantic wraps them properly; this test
    # asserts the resulting user-visible message.
    assert result.exit_code != 0
    assert "Dataframe seed sources (seed_type=df) are not supported on the NeMo Platform" in result.output
    assert "Field required" not in result.output
    assert "No such file" not in result.output


def test_create_run_rejects_dataframe_seed_with_clear_error(tmp_path: Path) -> None:
    """``create run`` of a ``df``-seed config produces a clear, user-visible error.

    Same root cause as the ``preview run`` case above: the ``df`` seed is rejected
    by a Pydantic before-validator on ``DataDesignerJobConfig``. The user-visible
    message comes through ``CreateRenderer.on_error``, which catches the exception
    and formats it for the terminal.
    """
    config_path = u.write_config_file(
        tmp_path,
        """
import data_designer.config as dd
import pandas as pd


def load_config_builder() -> dd.DataDesignerConfigBuilder:
    builder = dd.DataDesignerConfigBuilder()
    builder.with_seed_dataset(dd.DataFrameSeedSource(df=pd.DataFrame(data={"a": [1, 2, 3]})))
    builder.add_column(dd.ExpressionColumnConfig(name="value", expr="{{ a }}"))
    return builder
""",
        name="dataframe_seed_create_config.py",
    )

    with u.make_mock_client_context(workspace="default") as client_context:
        result = u.invoke_cli(
            ["create", "run", str(config_path), "--num-records", "3"],
            client_context,
        )

    assert result.exit_code != 0
    # ``CreateRenderer.on_error`` runs the message through Rich, which line-wraps
    # to the terminal width, so we assert on fragments rather than the full
    # ``"Dataframe seed sources (seed_type=df) are not supported..."`` substring.
    assert "Dataframe seed sources" in result.output
    assert "seed_type=df" in result.output
    assert "Field required" not in result.output


def test_create_run_reports_artifacts_and_dataset_path(tmp_path: Path) -> None:
    config_path = _write_sampler_config(tmp_path)

    with u.make_mock_client_context(workspace="default") as client_context:
        result = u.invoke_cli(
            ["create", "run", str(config_path), "--num-records", "3"],
            client_context,
            output_format="json",
        )

    assert result.exit_code == 0, result.output
    payload = u.parse_cli_json_object(result.output)
    assert payload["exit_code"] == 0
    assert payload["workspace"] == "default"
    assert payload["num_records"] == 3
    assert payload["results"]["artifacts"]["name"] == "artifacts"
    assert payload["results"]["analysis"]["name"] == "analysis"

    dataset_path = u.read_file_url(payload["dataset_path"])
    artifacts_path = u.read_file_url(payload["results"]["artifacts"]["artifact_url"])
    analysis_path = u.read_file_url(payload["results"]["analysis"]["artifact_url"])
    assert dataset_path == artifacts_path / "dataset" / "parquet-files"

    dataset = pd.read_parquet(dataset_path)
    assert dataset["topic"].tolist() == ["math", "math", "math"]
    assert dataset["description"].tolist() == ["Topic: math", "Topic: math", "Topic: math"]

    analysis = DatasetProfilerResults.model_validate_json(analysis_path.read_text(encoding="utf-8"))
    assert analysis.num_records == 3


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
