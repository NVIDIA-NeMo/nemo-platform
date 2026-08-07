# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate environment FileSet packages on disk."""

from __future__ import annotations

from pathlib import Path

import yaml

from nmp.rl.schemas.environment import (
    ENVIRONMENT_MANIFEST_ADAPTER,
    AdapterWheelsV1Manifest,
    EnvironmentFormat,
    EnvironmentManifest,
    GymVerifiersDatasetRow,
    WheelsV1Manifest,
)
from nmp.rl.tasks.environment.allowlist import IMAGE_ADAPTER_ALLOWLIST


class EnvironmentPackageValidationError(ValueError):
    """Raised when an environment package fails validation."""


def load_manifest(env_root: Path) -> EnvironmentManifest:
    manifest_path = env_root / "nemo-environment.yaml"
    if not manifest_path.is_file():
        raise EnvironmentPackageValidationError(
            f"Missing nemo-environment.yaml at environment root: {env_root}"
        )
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise EnvironmentPackageValidationError("nemo-environment.yaml must be a mapping")
    return ENVIRONMENT_MANIFEST_ADAPTER.validate_python(raw)


def validate_package_layout(env_root: Path, manifest: EnvironmentManifest) -> None:
    """Validate on-disk layout for the declared environment format."""
    if not env_root.is_dir():
        raise EnvironmentPackageValidationError(f"Environment root is not a directory: {env_root}")

    for jsonl in env_root.rglob("*.jsonl"):
        raise EnvironmentPackageValidationError(
            f"Prompt JSONL must not live in the environment package: {jsonl.relative_to(env_root)}"
        )

    for rel in manifest.config_paths:
        cfg = env_root / rel
        if not cfg.is_file():
            raise EnvironmentPackageValidationError(f"Missing config file: {rel}")
        if cfg.is_symlink():
            raise EnvironmentPackageValidationError(f"Symlinks are not allowed: {rel}")
        resolved = cfg.resolve()
        if not str(resolved).startswith(str(env_root.resolve())):
            raise EnvironmentPackageValidationError(f"config_paths escapes environment root: {rel}")

    fmt = manifest.format
    if fmt in (EnvironmentFormat.WHEELS_V1, EnvironmentFormat.ADAPTER_WHEELS_V1):
        wheels_dir = env_root / "wheels"
        if not wheels_dir.is_dir():
            raise EnvironmentPackageValidationError("Missing wheels/ directory")
        wheels = [p for p in wheels_dir.iterdir() if p.is_file()]
        if not wheels:
            raise EnvironmentPackageValidationError("wheels/ must be non-empty")
        for whl in wheels:
            if whl.suffix != ".whl":
                raise EnvironmentPackageValidationError(f"Non-wheel file in wheels/: {whl.name}")

    if isinstance(manifest, AdapterWheelsV1Manifest):
        if manifest.adapter.agent not in IMAGE_ADAPTER_ALLOWLIST:
            raise EnvironmentPackageValidationError(
                f"adapter.agent {manifest.adapter.agent!r} is not on the image allowlist"
            )


def validate_dataset_rows(
    rows: list[dict],
    *,
    expected_vf_env_id: str | None,
    expected_agent: str | None,
) -> list[GymVerifiersDatasetRow]:
    parsed: list[GymVerifiersDatasetRow] = []
    for row in rows:
        item = GymVerifiersDatasetRow.model_validate(row)
        if expected_agent and item.agent_ref.name != expected_agent:
            raise EnvironmentPackageValidationError(
                f"agent_ref.name {item.agent_ref.name!r} != expected {expected_agent!r}"
            )
        if expected_vf_env_id and item.vf_env_id != expected_vf_env_id:
            raise EnvironmentPackageValidationError(
                f"vf_env_id {item.vf_env_id!r} != expected {expected_vf_env_id!r}"
            )
        parsed.append(item)
    return parsed


def offline_wheel_install_required(manifest: EnvironmentManifest) -> bool:
    return manifest.format in (EnvironmentFormat.WHEELS_V1, EnvironmentFormat.ADAPTER_WHEELS_V1)
