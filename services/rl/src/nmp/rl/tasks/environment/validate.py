# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate environment FileSet packages on disk."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

import yaml
from nmp.rl.schemas.environment import (
    ENVIRONMENT_MANIFEST_ADAPTER,
    AdapterWheelsV1Manifest,
    EnvironmentFormat,
    EnvironmentManifest,
    GymVerifiersDatasetRow,
)
from nmp.rl.tasks.environment.allowlist import IMAGE_ADAPTER_ALLOWLIST

logger = logging.getLogger(__name__)


class EnvironmentPackageValidationError(ValueError):
    """Raised when an environment package fails validation."""


def duplicate_wheel_distributions(wheels_dir: Path) -> dict[str, list[str]]:
    """Return ``{normalized distribution: [versions]}`` for anything vendored twice.

    A ``--find-links`` directory carrying several versions of one project is legal, so
    this is not an error -- but it means the package no longer pins what gets installed,
    and a consumer that pins every file outright cannot satisfy it at all.
    """
    versions: dict[str, list[str]] = defaultdict(list)
    for wheel in sorted(wheels_dir.glob("*.whl")):
        parts = wheel.name.split("-")
        if len(parts) < 5:
            continue
        versions[re.sub(r"[-_.]+", "-", parts[0]).lower()].append(parts[1])
    return {name: found for name, found in versions.items() if len(found) > 1}


def load_manifest(env_root: Path) -> EnvironmentManifest:
    manifest_path = env_root / "nemo-environment.yaml"
    if not manifest_path.is_file():
        raise EnvironmentPackageValidationError(f"Missing nemo-environment.yaml at environment root: {env_root}")
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
        # Compare by path components, not string prefix: "/job/environment-attacker"
        # startswith("/job/environment") but is a different directory.
        if not cfg.resolve().is_relative_to(env_root.resolve()):
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
        # Warn, not raise: several versions of a project in a find-links pool is legal, and
        # rejecting here would invalidate packages already uploaded. But it means the
        # package does not pin what gets installed, so say so where it can still be fixed
        # rather than leaving it to surface as a resolver failure mid-job.
        for name, versions in duplicate_wheel_distributions(wheels_dir).items():
            logger.warning(
                "wheels/ vendors %d versions of %s (%s). The installed version is then "
                "whatever the resolver picks. Regenerate the package so it vendors a "
                "single resolved closure.",
                len(versions),
                name,
                ", ".join(sorted(versions)),
            )

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
            raise EnvironmentPackageValidationError(f"vf_env_id {item.vf_env_id!r} != expected {expected_vf_env_id!r}")
        parsed.append(item)
    return parsed


def offline_wheel_install_required(manifest: EnvironmentManifest) -> bool:
    return manifest.format in (EnvironmentFormat.WHEELS_V1, EnvironmentFormat.ADAPTER_WHEELS_V1)
