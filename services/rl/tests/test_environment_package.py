# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for environment FileSet manifest schemas and package validation."""

from __future__ import annotations

from pathlib import Path

import pytest
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


def test_split_train_validation_never_overlaps() -> None:
    """The old `or all_rows` fallback made train and validation identical."""
    from nmp.rl.tasks.environment.convert import split_train_validation

    rows = [{"task_idx": i} for i in range(10)]
    train, val = split_train_validation(rows, 0.2)
    assert val is not None
    assert len(train) == 8 and len(val) == 2
    train_ids = {r["task_idx"] for r in train}
    val_ids = {r["task_idx"] for r in val}
    assert not (train_ids & val_ids)

    assert split_train_validation(rows, 0.0) == (rows, None)
    assert split_train_validation([], 0.5) == ([], None)


@pytest.mark.parametrize(("n_rows", "fraction"), [(1, 0.2), (5, 1.0), (10, 1.0)])
def test_split_train_validation_rejects_empty_training_set(n_rows: int, fraction: float) -> None:
    from nmp.rl.tasks.environment.convert import split_train_validation

    rows = [{"task_idx": i} for i in range(n_rows)]
    with pytest.raises(ValueError, match="leaves no training rows"):
        split_train_validation(rows, fraction)


def test_validation_fraction_cli_rejects_out_of_range() -> None:
    import argparse

    from nmp.rl.tasks.environment.__main__ import _validation_fraction

    assert _validation_fraction("0.2") == 0.2
    assert _validation_fraction("0") == 0.0
    for bad in ("1.0", "2.5", "-0.1"):
        with pytest.raises(argparse.ArgumentTypeError):
            _validation_fraction(bad)


def test_wheel_version_prefers_numeric_order_over_lexicographic() -> None:
    from nmp.rl.tasks.environment.convert import _wheel_version

    wheels = [
        Path("ascii_tree-0.9.0-py3-none-any.whl"),
        Path("ascii_tree-0.10.0-py3-none-any.whl"),
        Path("ascii_tree-0.2.0-py3-none-any.whl"),
    ]
    assert sorted(wheels)[-1].name.startswith("ascii_tree-0.9.0")
    assert max(wheels, key=_wheel_version).name.startswith("ascii_tree-0.10.0")


def test_config_paths_containment_rejects_sibling_prefix_dir(tmp_path: Path) -> None:
    """A sibling whose name merely starts with the root's name is not contained."""
    env_root = tmp_path / "environment"
    (env_root / "configs").mkdir(parents=True)
    sibling = tmp_path / "environment-attacker"
    sibling.mkdir()
    (sibling / "evil.yaml").write_text("a: 1", encoding="utf-8")
    # An intermediate symlinked directory escapes the final-component is_symlink() check.
    (env_root / "configs" / "escape").symlink_to(sibling, target_is_directory=True)
    (env_root / "wheels").mkdir()
    (env_root / "wheels" / "x-1.0-py3-none-any.whl").write_bytes(b"x")
    (env_root / "nemo-environment.yaml").write_text(
        "format: adapter-wheels-v1\n"
        "adapter:\n  agent: verifiers_agent\n"
        "config_paths:\n  - configs/escape/evil.yaml\n"
        "metadata:\n  name: e\n",
        encoding="utf-8",
    )
    manifest = load_manifest(env_root)
    with pytest.raises(EnvironmentPackageValidationError, match="escapes environment root"):
        validate_package_layout(env_root, manifest)
