# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest
from sandboxed_gym.environment_package import (
    EnvironmentFormat,
    EnvironmentMetadata,
    EnvironmentPackageError,
    NativeV1Manifest,
    NativeV1Package,
    WheelsV1Manifest,
    WheelsV1Package,
    duplicate_wheel_distributions,
    load_environment_manifest,
    load_environment_package,
    parse_environment_manifest,
    require_supported_runtime_format,
    validate_environment_manifest_against_listing,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
WHEELS_V1_ENVIRONMENT = FIXTURES_DIR / "wheels_v1_environment"


def _write_manifest(root: Path, text: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "nemo-environment.yaml").write_text(text, encoding="utf-8")


def _complete_manifest(format_name: str, config_path: str) -> str:
    return f"format: {format_name}\nconfig_paths:\n  - {config_path}\nmetadata:\n  name: test-environment\n"


def _write_config(root: Path, relative_path: str) -> Path:
    config = root / relative_path
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("test: {}\n", encoding="utf-8")
    return config


def test_loads_complete_wheels_v1_fixture() -> None:
    package = load_environment_package(WHEELS_V1_ENVIRONMENT)

    assert isinstance(package, WheelsV1Package)
    assert package.manifest == WheelsV1Manifest(
        format=EnvironmentFormat.WHEELS_V1,
        config_paths=("resources_servers/wheels_v1_example/configs/wheels_v1_example.yaml",),
        metadata=EnvironmentMetadata(name="wheels-v1-environment"),
    )
    assert package.config_paths == (
        (WHEELS_V1_ENVIRONMENT / "resources_servers/wheels_v1_example/configs/wheels_v1_example.yaml").resolve(),
    )
    assert package.wheelhouse_path == (WHEELS_V1_ENVIRONMENT / "wheels").resolve()
    assert package.wheel_files == (
        (WHEELS_V1_ENVIRONMENT / "wheels/example_dependency-1.0-py3-none-any.whl").resolve(),
    )
    require_supported_runtime_format(package)


def test_native_v1_is_validated_then_rejected_as_unsupported(tmp_path: Path) -> None:
    config_path = "resources_servers/custom/configs/custom.yaml"
    _write_config(tmp_path, config_path)
    _write_manifest(tmp_path, _complete_manifest("native-v1", config_path))

    package = load_environment_package(tmp_path)

    assert isinstance(package, NativeV1Package)
    with pytest.raises(EnvironmentPackageError, match="native-v1 environment packages are not supported"):
        require_supported_runtime_format(package)


def test_native_validation_does_not_import_customer_code(tmp_path: Path) -> None:
    marker = tmp_path / "customer-code-ran"
    config = tmp_path / "resources_servers/custom/configs/custom.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("custom: {}\n", encoding="utf-8")
    app = config.parent.parent / "app.py"
    app.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
    _write_manifest(
        tmp_path, _complete_manifest("native-v1", config_path="resources_servers/custom/configs/custom.yaml")
    )

    package = load_environment_package(tmp_path)

    assert isinstance(package, NativeV1Package)
    assert not marker.exists()


@pytest.mark.parametrize(
    "manifest",
    [
        "format: native-v1\n",
        _complete_manifest("unknown-v1", "resources_servers/test/configs/test.yaml"),
        _complete_manifest("native-v1", "resources_servers/test/configs/test.yaml") + "unexpected: true\n",
        _complete_manifest("[native-v1, wheels-v1]", "resources_servers/test/configs/test.yaml"),
    ],
)
def test_rejects_invalid_or_combined_manifest_contracts(tmp_path: Path, manifest: str) -> None:
    _write_manifest(tmp_path, manifest)

    with pytest.raises(EnvironmentPackageError, match="is invalid"):
        load_environment_manifest(tmp_path)


@pytest.mark.parametrize(
    "config_path",
    [
        "/etc/passwd",
        "../outside.yaml",
        "configs/../../outside.yaml",
        r"configs\windows.yaml",
        " configs/test.yaml",
        "configs/test.yaml ",
    ],
)
def test_rejects_unsafe_native_config_paths(tmp_path: Path, config_path: str) -> None:
    _write_manifest(
        tmp_path,
        f"format: native-v1\nconfig_paths:\n  - {config_path!r}\nmetadata:\n  name: test-environment\n",
    )

    with pytest.raises(EnvironmentPackageError, match="is invalid"):
        load_environment_manifest(tmp_path)


def test_rejects_duplicate_native_config_paths(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        "format: native-v1\n"
        "config_paths:\n"
        "  - resources_servers/test/configs/test.yaml\n"
        "  - resources_servers/test/configs/test.yaml\n"
        "metadata:\n"
        "  name: test-environment\n",
    )

    with pytest.raises(EnvironmentPackageError, match="duplicates"):
        load_environment_manifest(tmp_path)


def test_rejects_missing_native_config(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        _complete_manifest("native-v1", "resources_servers/missing/configs/missing.yaml"),
    )

    with pytest.raises(EnvironmentPackageError, match="does not exist or is not a file"):
        load_environment_package(tmp_path)


def test_rejects_native_config_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.yaml"
    outside.write_text("outside: true\n", encoding="utf-8")
    config_path = "resources_servers/test/configs/escape.yaml"
    config = tmp_path / config_path
    config.parent.mkdir(parents=True)
    config.symlink_to(outside)
    _write_manifest(tmp_path, _complete_manifest("native-v1", config_path))

    with pytest.raises(EnvironmentPackageError, match="config symlinks are not allowed"):
        load_environment_package(tmp_path)


def test_rejects_native_config_symlink_within_root(tmp_path: Path) -> None:
    target = tmp_path / "resources_servers/test/configs/actual.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("actual: true\n", encoding="utf-8")
    alias_path = "resources_servers/test/configs/alias.yaml"
    (tmp_path / alias_path).symlink_to(target)
    _write_manifest(tmp_path, _complete_manifest("native-v1", alias_path))

    with pytest.raises(EnvironmentPackageError, match="config symlinks are not allowed"):
        load_environment_package(tmp_path)


def test_rejects_wheelhouse_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-wheels"
    outside.mkdir()
    (outside / "dependency-1.0-py3-none-any.whl").write_bytes(b"fixture")
    (tmp_path / "wheels").symlink_to(outside, target_is_directory=True)
    config_path = "resources_servers/test/configs/test.yaml"
    _write_config(tmp_path, config_path)
    _write_manifest(tmp_path, _complete_manifest("wheels-v1", config_path))

    with pytest.raises(EnvironmentPackageError, match="wheelhouse symlinks are not allowed"):
        load_environment_package(tmp_path)


def test_rejects_wheel_file_symlink(tmp_path: Path) -> None:
    config_path = "resources_servers/test/configs/test.yaml"
    _write_config(tmp_path, config_path)
    _write_manifest(tmp_path, _complete_manifest("wheels-v1", config_path))
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-dependency-1.0-py3-none-any.whl"
    outside.write_bytes(b"fixture")
    (wheels / "dependency-1.0-py3-none-any.whl").symlink_to(outside)

    with pytest.raises(EnvironmentPackageError, match="wheel symlinks are not allowed"):
        load_environment_package(tmp_path)


def test_rejects_empty_wheels_v1_package(tmp_path: Path) -> None:
    config_path = "resources_servers/test/configs/test.yaml"
    _write_config(tmp_path, config_path)
    _write_manifest(tmp_path, _complete_manifest("wheels-v1", config_path))
    (tmp_path / "wheels").mkdir()

    with pytest.raises(EnvironmentPackageError, match="non-empty wheels/ directory"):
        load_environment_package(tmp_path)


def test_rejects_malformed_yaml(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "format: [native-v1\n")

    with pytest.raises(EnvironmentPackageError, match="not valid YAML"):
        load_environment_manifest(tmp_path)


def test_parse_manifest_bytes_without_filesystem_access() -> None:
    manifest = parse_environment_manifest(
        _complete_manifest("native-v1", "resources_servers/test/configs/test.yaml").encode()
    )

    assert manifest == NativeV1Manifest(
        format=EnvironmentFormat.NATIVE_V1,
        config_paths=("resources_servers/test/configs/test.yaml",),
        metadata=EnvironmentMetadata(name="test-environment"),
    )


def test_listing_rejects_prompt_jsonl() -> None:
    manifest = parse_environment_manifest(_complete_manifest("native-v1", "resources_servers/test/configs/test.yaml"))

    with pytest.raises(EnvironmentPackageError, match="prompt JSONL"):
        validate_environment_manifest_against_listing(
            manifest,
            ["resources_servers/test/configs/test.yaml", "training.jsonl"],
        )


@pytest.mark.parametrize(
    ("wheel_entries", "error"),
    [
        ([], "non-empty wheels/ directory"),
        (["wheels/nested/dependency-1.0-py3-none-any.whl"], "must be flat"),
        (["wheels/requirements.txt"], "non-wheel files"),
    ],
)
def test_listing_rejects_invalid_wheelhouse_entries(wheel_entries: list[str], error: str) -> None:
    config_path = "resources_servers/test/configs/test.yaml"
    manifest = parse_environment_manifest(_complete_manifest("wheels-v1", config_path))

    with pytest.raises(EnvironmentPackageError, match=error):
        validate_environment_manifest_against_listing(manifest, [config_path, *wheel_entries])


def test_duplicate_wheel_distributions_are_rejected(tmp_path: Path) -> None:
    config_path = "resources_servers/test/configs/test.yaml"
    _write_config(tmp_path, config_path)
    _write_manifest(tmp_path, _complete_manifest("wheels-v1", config_path))
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "dependency-1.0-py3-none-any.whl").write_bytes(b"fixture")
    (wheels / "dependency-2.0-py3-none-any.whl").write_bytes(b"fixture")

    assert duplicate_wheel_distributions(wheels) == {"dependency": ["1.0", "2.0"]}
    with pytest.raises(EnvironmentPackageError, match="multiple versions"):
        load_environment_package(tmp_path)


def test_listing_rejects_customer_model_configuration() -> None:
    config_path = "resources_servers/custom/configs/custom.yaml"
    manifest = parse_environment_manifest(_complete_manifest("wheels-v1", config_path))

    with pytest.raises(EnvironmentPackageError, match="model configuration is operator-owned"):
        validate_environment_manifest_against_listing(
            manifest,
            [
                config_path,
                "responses_api_models/customer/configs/customer.yaml",
                "wheels/dependency-1.0-py3-none-any.whl",
            ],
        )
