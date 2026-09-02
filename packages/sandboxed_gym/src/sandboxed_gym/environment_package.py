# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed contracts and layered validation for Gym environment FileSets."""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

#: Package identity file at the FileSet root. Submit and the Gym host both key off this name.
ENVIRONMENT_MANIFEST_FILENAME = "nemo-environment.yaml"
NATIVE_V1_FORMAT = "native-v1"
WHEELS_V1_FORMAT = "wheels-v1"
#: Flat directory of ``.whl`` files that wheels-v1 installs with ``--no-index --find-links``.
WHEELS_V1_SUBDIR = "wheels"
#: Subdirectory for a custom Gym agent.
CUSTOM_AGENT_SUBDIR = "responses_api_agents"
#: Subdirectory for a custom Gym resources server.
CUSTOM_RESOURCES_SERVER_SUBDIR = "resources_servers"
#: Operator-owned Gym model configs. A customer FileSet that ships this tree is rejected.
OPERATOR_MODEL_SUBDIR = "responses_api_models"
NATIVE_V1_UNSUPPORTED_MESSAGE = "native-v1 environment packages are not supported; use a wheels-v1 package"


class EnvironmentPackageError(ValueError):
    """Raised when an environment FileSet violates its packaging contract."""


class EnvironmentFormat(StrEnum):
    """Supported environment dependency-resolution strategies."""

    NATIVE_V1 = NATIVE_V1_FORMAT
    WHEELS_V1 = WHEELS_V1_FORMAT


class EnvironmentMetadata(BaseModel):
    """Identity and optional provenance carried by an environment package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    hub_id: str | None = Field(default=None, max_length=512)
    vf_env_id: str | None = Field(default=None, max_length=512)
    adapter_agent: str | None = Field(default=None, max_length=255)


def _validate_relative_config_path(value: str) -> str:
    """Reject absolute, escaped, or traversing config paths before any filesystem access."""
    if not value or value != value.strip():
        raise ValueError("config paths must be non-empty and cannot have surrounding whitespace")
    if "\\" in value:
        raise ValueError("config paths must use POSIX '/' separators")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("config paths must be relative to the environment root")
    if path == PurePosixPath(".") or ".." in path.parts:
        raise ValueError("config paths cannot contain '.' or '..' traversal")
    return value


class _ManifestBase(BaseModel):
    """Fields shared by every complete Gym environment package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_paths: tuple[str, ...] = Field(min_length=1)
    metadata: EnvironmentMetadata

    @field_validator("config_paths")
    @classmethod
    def _validate_config_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize relative config paths and reject duplicates."""
        validated = tuple(_validate_relative_config_path(value) for value in values)
        if len(set(validated)) != len(validated):
            raise ValueError("config_paths cannot contain duplicates")
        return validated


class NativeV1Manifest(_ManifestBase):
    """A complete environment whose dependencies resolve through a package index."""

    format: Literal[EnvironmentFormat.NATIVE_V1] = EnvironmentFormat.NATIVE_V1

    @field_validator("config_paths")
    @classmethod
    def _under_gym_component_directories(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Keep native-v1 configs inside Gym's agent/resources-server trees, not the model tree."""
        allowed = (f"{CUSTOM_AGENT_SUBDIR}/", f"{CUSTOM_RESOURCES_SERVER_SUBDIR}/")
        for value in values:
            if not value.startswith(allowed):
                raise ValueError(f"native-v1 config_paths must be under {allowed}: {value!r}")
        return values


class WheelsV1Manifest(_ManifestBase):
    """A complete environment whose dependencies resolve from its wheelhouse."""

    format: Literal[EnvironmentFormat.WHEELS_V1] = EnvironmentFormat.WHEELS_V1


EnvironmentManifest = Annotated[NativeV1Manifest | WheelsV1Manifest, Field(discriminator="format")]
_ENVIRONMENT_MANIFEST_ADAPTER = TypeAdapter(EnvironmentManifest)


@dataclass(frozen=True)
class NativeV1Package:
    """Validated native source package. Parsed and layout-checked, then rejected at execution."""

    root: Path
    manifest: NativeV1Manifest
    config_paths: tuple[Path, ...]


@dataclass(frozen=True)
class WheelsV1Package:
    """Validated environment plus wheelhouse ready for host installation."""

    root: Path
    manifest: WheelsV1Manifest
    config_paths: tuple[Path, ...]
    wheelhouse_path: Path
    wheel_files: tuple[Path, ...]


EnvironmentPackage = NativeV1Package | WheelsV1Package


def parse_environment_manifest(raw_yaml: bytes | str) -> EnvironmentManifest:
    """Parse manifest content without inspecting files or importing customer code."""
    import yaml

    try:
        raw_manifest = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise EnvironmentPackageError(f"{ENVIRONMENT_MANIFEST_FILENAME} is not valid YAML") from exc

    if not isinstance(raw_manifest, dict):
        raise EnvironmentPackageError(f"{ENVIRONMENT_MANIFEST_FILENAME} must be a mapping")

    try:
        return _ENVIRONMENT_MANIFEST_ADAPTER.validate_python(raw_manifest)
    except ValidationError as exc:
        raise EnvironmentPackageError(f"{ENVIRONMENT_MANIFEST_FILENAME} is invalid: {exc}") from exc


def load_environment_manifest(environment_root: str | Path) -> EnvironmentManifest:
    """Load and type-check ``nemo-environment.yaml`` without importing customer code."""
    root = _validated_root(environment_root)
    manifest_path = root / ENVIRONMENT_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise EnvironmentPackageError(f"environment manifest does not exist or is not a file: {manifest_path}")
    return parse_environment_manifest(manifest_path.read_bytes())


def validate_environment_manifest_against_listing(
    manifest: EnvironmentManifest,
    paths: Iterable[str],
) -> None:
    """Validate package rules decidable from a remote FileSet listing."""
    entries = {path.removeprefix("./") for path in paths}

    # Model YAML is operator-owned (image + VirtualModel). A customer copy would silently
    # shadow it once FileSet composition lands, so refuse it at submit.
    customer_model_files = sorted(path for path in entries if path.startswith(f"{OPERATOR_MODEL_SUBDIR}/"))
    if customer_model_files:
        raise EnvironmentPackageError(
            f"Custom {OPERATOR_MODEL_SUBDIR} directory is not supported; model configuration is operator-owned: "
            f"{', '.join(customer_model_files)}"
        )

    # Prompts are a dataset, not an environment. Mixing them here would stage eval data into
    # the read-only Gym mount and skip the dataset FileSet path.
    prompt_files = sorted(path for path in entries if path.endswith(".jsonl"))
    if prompt_files:
        raise EnvironmentPackageError(
            "JSONL files must not live in an environment package: "
            f"{', '.join(prompt_files)}; use a separate dataset FileSet"
        )

    # Fail at submit if the manifest names configs the FileSet does not actually contain.
    missing_configs = sorted(path for path in manifest.config_paths if path not in entries)
    if missing_configs:
        raise EnvironmentPackageError(
            f"The `config_paths` field references files that are not in the package: {', '.join(missing_configs)}"
        )

    if not isinstance(manifest, WheelsV1Manifest):
        return

    # wheels-v1 installs with ``--find-links wheels/``. Nested dirs and non-wheels would be
    # skipped by that installer and look like a successful empty install.
    wheel_entries = sorted(path for path in entries if path.startswith(f"{WHEELS_V1_SUBDIR}/"))
    nested_entries = [path for path in wheel_entries if "/" in path.removeprefix(f"{WHEELS_V1_SUBDIR}/")]
    if nested_entries:
        raise EnvironmentPackageError(
            f"{WHEELS_V1_SUBDIR}/ must be flat; nested entries are not supported: {', '.join(nested_entries)}"
        )

    if not wheel_entries:
        raise EnvironmentPackageError(
            f"{WHEELS_V1_FORMAT} installs environment dependencies from a non-empty {WHEELS_V1_SUBDIR}/ directory"
        )

    non_wheels = [path for path in wheel_entries if not path.endswith(".whl")]
    if non_wheels:
        raise EnvironmentPackageError(f"non-wheel files in {WHEELS_V1_SUBDIR}/: {', '.join(non_wheels)}")


def duplicate_wheel_distributions(wheelhouse_path: Path) -> dict[str, list[str]]:
    """Return distributions represented by more than one wheel version."""
    versions: dict[str, list[str]] = defaultdict(list)
    for wheel in sorted(wheelhouse_path.glob("*.whl")):
        parts = wheel.name.split("-")
        if len(parts) < 5:
            continue
        normalized_name = re.sub(r"[-_.]+", "-", parts[0]).lower()
        versions[normalized_name].append(parts[1])
    return {name: found for name, found in versions.items() if len(found) > 1}


def validate_environment_package_layout(
    environment_root: str | Path,
    manifest: EnvironmentManifest,
) -> None:
    """Validate filesystem-specific package rules after FileSet staging."""
    root = _validated_root(environment_root)
    for relative_path in manifest.config_paths:
        unresolved = root / relative_path
        if unresolved.is_symlink():
            raise EnvironmentPackageError(f"config symlinks are not allowed: {relative_path}")
        _resolve_contained_file(root, relative_path)

    if isinstance(manifest, WheelsV1Manifest):
        unresolved_wheelhouse = root / WHEELS_V1_SUBDIR
        if unresolved_wheelhouse.is_symlink():
            raise EnvironmentPackageError(f"wheelhouse symlinks are not allowed: {WHEELS_V1_SUBDIR}")
        wheelhouse = _resolve_contained_directory(root, WHEELS_V1_SUBDIR)
        for wheel in wheelhouse.glob("*.whl"):
            if wheel.is_symlink():
                raise EnvironmentPackageError(f"wheel symlinks are not allowed: {wheel.relative_to(root).as_posix()}")
            _require_contained(root, wheel.resolve(), wheel.relative_to(root).as_posix())

    validate_environment_manifest_against_listing(
        manifest,
        (path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()),
    )

    if isinstance(manifest, WheelsV1Manifest):
        duplicates = duplicate_wheel_distributions(root / WHEELS_V1_SUBDIR)
        if duplicates:
            details = ", ".join(f"{name} ({', '.join(versions)})" for name, versions in sorted(duplicates.items()))
            raise EnvironmentPackageError(
                f"wheels/ vendors multiple versions of the same distribution: {details}; "
                "regenerate the package with one resolved version per distribution"
            )


def load_environment_package(environment_root: str | Path) -> EnvironmentPackage:
    """Validate one mutually exclusive native-v1 or wheels-v1 package."""
    root = _validated_root(environment_root)
    manifest = load_environment_manifest(root)
    validate_environment_package_layout(root, manifest)
    config_paths = tuple((root / relative).resolve() for relative in manifest.config_paths)
    if isinstance(manifest, NativeV1Manifest):
        return NativeV1Package(root=root, manifest=manifest, config_paths=config_paths)

    wheelhouse_path = (root / WHEELS_V1_SUBDIR).resolve()
    wheel_files = tuple(path.resolve() for path in sorted(wheelhouse_path.glob("*.whl")))
    return WheelsV1Package(
        root=root,
        manifest=manifest,
        config_paths=config_paths,
        wheelhouse_path=wheelhouse_path,
        wheel_files=wheel_files,
    )


def require_supported_runtime_format(package: EnvironmentPackage) -> None:
    """Reject formats that are valid packages but not executable on this branch."""
    if isinstance(package, NativeV1Package):
        raise EnvironmentPackageError(NATIVE_V1_UNSUPPORTED_MESSAGE)


def _validated_root(environment_root: str | Path) -> Path:
    """Resolve the package root and refuse a missing or non-directory path."""
    root = Path(environment_root)
    if not root.is_dir():
        raise EnvironmentPackageError(f"environment root does not exist or is not a directory: {root}")
    return root.resolve()


def _resolve_contained_file(root: Path, relative_path: str) -> Path:
    """Resolve a package file and refuse symlink/path escape outside ``root``."""
    candidate = (root / relative_path).resolve()
    _require_contained(root, candidate, relative_path)
    if not candidate.is_file():
        raise EnvironmentPackageError(f"environment path does not exist or is not a file: {relative_path}")
    return candidate


def _resolve_contained_directory(root: Path, relative_path: str) -> Path:
    """Resolve a package directory and refuse symlink/path escape outside ``root``."""
    candidate = (root / relative_path).resolve()
    _require_contained(root, candidate, relative_path)
    if not candidate.is_dir():
        raise EnvironmentPackageError(f"environment path does not exist or is not a directory: {relative_path}")
    return candidate


def _require_contained(root: Path, candidate: Path, relative_path: str) -> None:
    """Raise if ``candidate`` resolved outside the environment root."""
    if not candidate.is_relative_to(root):
        raise EnvironmentPackageError(f"environment path escapes its root: {relative_path}")
