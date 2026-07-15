# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Analysis-owned view of an ``optimizer.yaml`` agent profile."""

import os
from collections.abc import MutableMapping
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROFILE_FILENAME = "optimizer.yaml"


class ProfileError(ValueError):
    """An optimizer profile is absent, unreadable, or invalid for analysis."""


class InsightsFileError(ValueError):
    """An existing shared Insights file is unreadable or structurally invalid."""


class AnalysisProfile(BaseModel):
    """Only fields consumed by ``nemo insights``; all other keys are tolerated."""

    model_config = ConfigDict(extra="ignore")

    agent: str = Field(min_length=1)
    agent_spec: str | None = None
    workspace: str = "default"
    profile_dir: Path


def load_profile(path: Path) -> AnalysisProfile:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProfileError(f"Could not parse profile {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProfileError(f"Could not parse profile {path}: expected a YAML mapping")
    if "profile_dir" in payload:
        raise ProfileError(f"Invalid profile {path}: 'profile_dir' is reserved")
    try:
        return AnalysisProfile(profile_dir=path.parent.resolve(), **payload)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}" for error in exc.errors())
        raise ProfileError(f"Invalid profile {path}: {details}") from exc


def discover_profile(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / PROFILE_FILENAME
        if candidate.is_file():
            return candidate
    return None


def resolve_profile_path(value: str, profile_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (profile_dir / path).resolve()


def pick_agent_spec(profile: AnalysisProfile) -> Path | None:
    if profile.agent_spec is not None:
        path = resolve_profile_path(profile.agent_spec, profile.profile_dir)
        if not path.is_file():
            raise ProfileError(f"Profile agent_spec {profile.agent_spec!r} does not exist (resolved to {path})")
        return path
    for name in ("AGENT-SPEC.md", "README.md"):
        candidate = profile.profile_dir / name
        if candidate.is_file():
            return candidate
    return None


def validate_insights_file(path: Path | None) -> None:
    """Require an existing shared Insights file to be UTF-8 YAML with a mapping root."""
    if path is None:
        return
    try:
        path.stat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise InsightsFileError(f"insights file {path} is not readable as UTF-8: {exc}") from exc
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        raise InsightsFileError(f"insights file {path} is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise InsightsFileError(f"insights file {path} is not readable as UTF-8: {exc}") from exc
    except yaml.YAMLError as exc:
        raise InsightsFileError(f"insights file {path} must contain valid YAML: {exc}") from exc
    if not isinstance(payload, dict):
        raise InsightsFileError(f"insights file {path} must contain a YAML mapping at its root")
    if "insights" not in payload:
        return
    records = payload["insights"]
    if not isinstance(records, list):
        raise InsightsFileError(f"insights file {path}: `insights` must be a list")
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise InsightsFileError(f"insights file {path}: `insights` item {index} must be a YAML mapping")


def load_env_file(
    path: Path,
    env: MutableMapping[str, str] = os.environ,
) -> list[str]:
    if not path.is_file():
        return []
    loaded: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in env:
            env[key] = value
            loaded.append(key)
    return loaded
