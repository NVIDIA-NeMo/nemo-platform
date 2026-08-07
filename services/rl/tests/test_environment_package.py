# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for environment FileSet manifest schemas and package validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from nmp.rl.schemas.environment import (
    AdapterWheelsV1Manifest,
    EnvironmentFormat,
    GymVerifiersDatasetRow,
)
from nmp.rl.tasks.environment.package import (
    build_verifiers_agent_yaml,
    write_adapter_wheels_package,
)
from nmp.rl.tasks.environment.validate import (
    EnvironmentPackageValidationError,
    load_manifest,
    offline_wheel_install_required,
    validate_package_layout,
)


def test_adapter_wheels_manifest_roundtrip() -> None:
    raw = {
        "format": "adapter-wheels-v1",
        "adapter": {
            "agent": "verifiers_agent",
            "agent_type": "responses_api_agents",
            "image_config_root": "responses_api_agents/verifiers_agent",
        },
        "config_paths": ["configs/verifiers_agent.yaml"],
        "metadata": {
            "name": "ascii-tree",
            "hub_id": "primeintellect/ascii-tree",
            "vf_env_id": "ascii-tree",
            "adapter_agent": "verifiers_agent",
        },
    }
    manifest = AdapterWheelsV1Manifest.model_validate(raw)
    assert manifest.format == EnvironmentFormat.ADAPTER_WHEELS_V1
    assert manifest.adapter.agent == "verifiers_agent"


def test_config_paths_reject_traversal() -> None:
    with pytest.raises(ValueError, match="relative and contained"):
        AdapterWheelsV1Manifest.model_validate(
            {
                "format": "adapter-wheels-v1",
                "adapter": {"agent": "verifiers_agent"},
                "config_paths": ["../escape.yaml"],
                "metadata": {"name": "x"},
            }
        )


def test_write_adapter_package_layout(tmp_path: Path) -> None:
    wheels = tmp_path / "src_wheels"
    wheels.mkdir()
    (wheels / "fake-1.0.0-py3-none-any.whl").write_bytes(b"PK\x03\x04")

    env_root = tmp_path / "env"
    manifest = write_adapter_wheels_package(
        out_dir=env_root,
        hub_id="primeintellect/ascii-tree",
        wheels_src=wheels,
    )
    assert (env_root / "nemo-environment.yaml").is_file()
    assert (env_root / "configs" / "verifiers_agent.yaml").is_file()
    assert list((env_root / "wheels").glob("*.whl"))
    validate_package_layout(env_root, manifest)
    loaded = load_manifest(env_root)
    assert loaded.metadata.vf_env_id == "ascii-tree"


def test_reject_jsonl_in_environment_package(tmp_path: Path) -> None:
    env_root = tmp_path / "env"
    wheels = tmp_path / "w"
    wheels.mkdir()
    (wheels / "a-1.0-py3-none-any.whl").write_bytes(b"PK")
    manifest = write_adapter_wheels_package(
        out_dir=env_root,
        hub_id="primeintellect/test",
        wheels_src=wheels,
    )
    (env_root / "training.jsonl").write_text("{}\n")
    with pytest.raises(EnvironmentPackageValidationError, match="JSONL"):
        validate_package_layout(env_root, manifest)


def test_offline_install_required_for_adapter_wheels() -> None:
    m = AdapterWheelsV1Manifest.model_validate(
        {
            "format": "adapter-wheels-v1",
            "adapter": {"agent": "verifiers_agent"},
            "config_paths": ["configs/verifiers_agent.yaml"],
            "metadata": {"name": "t"},
        }
    )
    assert offline_wheel_install_required(m) is True


def test_gym_verifiers_dataset_row() -> None:
    row = GymVerifiersDatasetRow.model_validate(
        {
            "task_idx": 0,
            "vf_env_id": "ascii-tree",
            "responses_create_params": {"input": [{"role": "user", "content": "hi"}]},
            "agent_ref": {"type": "responses_api_agents", "name": "verifiers_agent"},
            "example_id": 0,
        }
    )
    assert row.agent_ref.name == "verifiers_agent"


def test_verifiers_agent_yaml_shape() -> None:
    doc = build_verifiers_agent_yaml("ascii-tree", {})
    assert "verifiers_agent" in doc
    assert doc["verifiers_agent"]["responses_api_agents"]["verifiers_agent"]["vf_env_id"] == "ascii-tree"


def test_bootstrap_adapter_wheels_validate_only(tmp_path: Path) -> None:
    from nmp.rl.tasks.environment.bootstrap import bootstrap_environment_package

    wheels = tmp_path / "src_wheels"
    wheels.mkdir()
    (wheels / "fake-1.0.0-py3-none-any.whl").write_bytes(b"PK\x03\x04")
    env_root = tmp_path / "env"
    write_adapter_wheels_package(
        out_dir=env_root,
        hub_id="primeintellect/ascii-tree",
        wheels_src=wheels,
    )
    result = bootstrap_environment_package(env_root, install_wheels=False)
    assert result.manifest.format.value == "adapter-wheels-v1"
    assert result.image_config_root == "responses_api_agents/verifiers_agent"


def test_convert_with_wheels_dir_writes_layout(tmp_path: Path) -> None:
    from nmp.rl.tasks.environment.convert import ConvertEnvironmentSpec, convert_prime_environment

    wheels = tmp_path / "prebuilt"
    wheels.mkdir()
    (wheels / "ascii_tree-0.0.0-py3-none-any.whl").write_bytes(b"PK\x03\x04")
    out = tmp_path / "env"
    ds = tmp_path / "dataset"
    result = convert_prime_environment(
        ConvertEnvironmentSpec(
            hub_id="primeintellect/ascii-tree",
            out_dir=out,
            dataset_dir=ds,
            wheels_dir=wheels,
            dataset_size=0,
        )
    )
    manifest = load_manifest(result.environment_root)
    validate_package_layout(result.environment_root, manifest)
    assert list((result.environment_root / "wheels").glob("*.whl"))
    assert result.dataset_dir.is_dir()
    assert result.training_jsonl.is_file()


def test_convert_rejects_empty_wheels_dir(tmp_path: Path) -> None:
    from nmp.rl.tasks.environment.convert import ConvertEnvironmentSpec, convert_prime_environment

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no \\*\\.whl"):
        convert_prime_environment(
            ConvertEnvironmentSpec(
                hub_id="primeintellect/ascii-tree",
                out_dir=tmp_path / "env",
                dataset_dir=tmp_path / "dataset",
                wheels_dir=empty,
                dataset_size=0,
            )
        )
