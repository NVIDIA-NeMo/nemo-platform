# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate and stage complete custom Gym environment inputs.

The shared workflow calls this module after either a developer supplies a
complete ``wheels-v1`` directory and Gym JSONL dataset or the default example
adapter produces those same inputs. This module copies caller-owned inputs into
the run directory, validates the package and dataset without importing customer
code, discovers selectable resources servers, and extracts package metadata
used by generic runtime verification.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nemo_evaluator_sdk.agent_eval.runtimes.gym import discover_gym_tasks
from sandboxed_gym.environment_package import (
    WheelsV1Package,
    inspect_environment_components,
    load_environment_package,
)


@dataclass(frozen=True, slots=True)
class PreparedEnvironment:
    """Validated environment and dataset metadata consumed by later stages."""

    root: Path
    dataset: Path
    name: str
    resources_server: str
    resources_servers: tuple[str, ...]
    wheel_names: tuple[str, ...]
    task_count: int
    input_mode: str

    def evidence(self) -> dict[str, Any]:
        """Return JSON-serializable preparation evidence."""
        return asdict(self)


def _require_safe_copy(source: Path, destination: Path, *, label: str) -> None:
    """Reject copy layouts that could overwrite or recursively copy an input."""
    resolved_source = source.resolve()
    resolved_destination = destination.resolve()
    if resolved_source == resolved_destination:
        raise ValueError(f"{label} source and run destination must differ: {resolved_source}")
    if resolved_destination.is_relative_to(resolved_source):
        raise ValueError(f"{label} run destination cannot be inside its source: {resolved_destination}")
    if resolved_source.is_relative_to(resolved_destination):
        raise ValueError(f"{label} source cannot be inside its run destination: {resolved_source}")


def _copy_custom_inputs(
    environment_source: Path,
    dataset_source: Path,
    *,
    environment_output: Path,
    dataset_output: Path,
) -> None:
    """Copy caller-owned package and dataset into the isolated run directory."""
    if not environment_source.is_dir():
        raise ValueError(f"environment directory does not exist: {environment_source}")
    if not dataset_source.is_file():
        raise ValueError(f"dataset does not exist or is not a file: {dataset_source}")
    _require_safe_copy(environment_source, environment_output, label="environment")
    _require_safe_copy(dataset_source, dataset_output, label="dataset")

    if environment_output.exists():
        shutil.rmtree(environment_output)
    environment_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(environment_source, environment_output)
    dataset_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dataset_source, dataset_output)


def _select_resources_server(
    available_servers: frozenset[str],
    requested_server: str | None,
) -> str:
    """Select a declared resources server or explain why selection is ambiguous."""
    if not available_servers:
        raise ValueError("environment does not declare a resources server")
    if requested_server is not None:
        if requested_server not in available_servers:
            raise ValueError(
                f"resources server {requested_server!r} is not declared; "
                f"available servers: {', '.join(sorted(available_servers))}"
            )
        return requested_server
    if len(available_servers) != 1:
        raise ValueError(
            "environment declares multiple resources servers; select one with "
            f"--resources-server: {', '.join(sorted(available_servers))}"
        )
    return next(iter(available_servers))


def inspect_prepared_inputs(
    environment: Path,
    dataset: Path,
    *,
    requested_resources_server: str | None,
    input_mode: str,
) -> PreparedEnvironment:
    """Validate staged inputs and derive all component metadata dynamically."""
    environment_package = load_environment_package(environment)
    if not isinstance(environment_package, WheelsV1Package):
        actual_format = type(environment_package).__name__
        raise ValueError(f"expected a wheels-v1 package, got {actual_format}")

    components = inspect_environment_components(environment_package)
    resources_server = _select_resources_server(
        components.resources_servers,
        requested_resources_server,
    )
    tasks = discover_gym_tasks(dataset)
    if not tasks:
        raise ValueError(f"Gym discovered no tasks in {dataset}")

    return PreparedEnvironment(
        root=environment_package.root,
        dataset=dataset.resolve(),
        name=environment_package.manifest.metadata.name,
        resources_server=resources_server,
        resources_servers=tuple(sorted(components.resources_servers)),
        wheel_names=tuple(wheel.name for wheel in environment_package.wheel_files),
        task_count=len(tasks),
        input_mode=input_mode,
    )


def prepare_custom_inputs(
    environment_source: Path,
    dataset_source: Path,
    *,
    environment_output: Path,
    dataset_output: Path,
    requested_resources_server: str | None,
) -> PreparedEnvironment:
    """Copy and validate a developer-provided environment package and dataset."""
    # Validate the caller-owned tree before copying so symlinks cannot be
    # dereferenced into apparently valid files inside the run directory.
    source_package = load_environment_package(environment_source)
    if not isinstance(source_package, WheelsV1Package):
        actual_format = type(source_package).__name__
        raise ValueError(f"expected a wheels-v1 package, got {actual_format}")

    _copy_custom_inputs(
        environment_source,
        dataset_source,
        environment_output=environment_output,
        dataset_output=dataset_output,
    )
    return inspect_prepared_inputs(
        environment_output,
        dataset_output,
        requested_resources_server=requested_resources_server,
        input_mode="custom",
    )
