# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare the bundled ASCII Tree example consumed by the generic workflow.

This module contains every Prime Intellect and ASCII Tree implementation detail:
it converts the pinned source fixture, adapts its rows to Gym's image-provided
``simple_agent``, builds and caches the custom scorer wheel, and materializes a
complete ``wheels-v1`` package. The shared preparation, submission, and
verification modules treat its outputs like any caller-provided environment.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from artifacts import read_jsonl
from commands import CommandRunner

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
ENVIRONMENT_TEMPLATE = SCRIPT_DIRECTORY / "environment"
WHEEL_SOURCE = SCRIPT_DIRECTORY / "scorer"
WHEEL_CACHE = Path(tempfile.gettempdir()) / "nmp-gym-custom-environment-wheel-cache"
FIXTURE_CACHE = Path(tempfile.gettempdir()) / "nmp-gym-custom-environment-fixture-cache"
SCORER_DISTRIBUTION = "nmp_ascii_tree_evaluator"
PRIME_FIXTURE_HUB_ID = "primeintellect/ascii-tree"
PRIME_FIXTURE_HUB_VERSION = "0.1.5"
PRIME_FIXTURE_SIZE = 2
PRIME_FIXTURE_SEED = 0
FIXTURE_CACHE_FORMAT_VERSION = 1


def _fixture_cache_path() -> Path:
    """Return the content-addressed cache path for the pinned source fixture."""
    cache_inputs = {
        "format_version": FIXTURE_CACHE_FORMAT_VERSION,
        "hub_id": PRIME_FIXTURE_HUB_ID,
        "hub_version": PRIME_FIXTURE_HUB_VERSION,
        "size": PRIME_FIXTURE_SIZE,
        "seed": PRIME_FIXTURE_SEED,
    }
    cache_key = hashlib.sha256(json.dumps(cache_inputs, sort_keys=True).encode()).hexdigest()
    return FIXTURE_CACHE / cache_key / "training.jsonl"


def _valid_fixture_cache(cache_path: Path) -> bool:
    """Return whether a cached conversion contains the expected usable rows."""
    if not cache_path.is_file():
        return False
    try:
        rows = read_jsonl(cache_path)
        return len(rows) == PRIME_FIXTURE_SIZE and all(
            isinstance(row.get("responses_create_params"), dict)
            and isinstance(row.get("answer"), str)
            and bool(row["answer"].strip())
            for row in rows
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _copy_cached_fixture(cache_path: Path, converter_dataset: Path) -> None:
    """Copy the reusable JSONL fixture into this run's working directory."""
    if converter_dataset.exists():
        shutil.rmtree(converter_dataset)
    converter_dataset.mkdir(parents=True)
    shutil.copy2(cache_path, converter_dataset / "training.jsonl")


def _convert_fixture(
    runner: CommandRunner,
    *,
    converter_environment: Path,
    converter_dataset: Path,
) -> bool:
    """Create or reuse the pinned two-row Prime Intellect fixture.

    The converter runs in an isolated uv environment. Only its JSONL output is
    cached; generated adapters, snapshots, and package caches are discarded.

    Returns ``True`` when an existing valid conversion was reused.
    """
    cache_path = _fixture_cache_path()
    if _valid_fixture_cache(cache_path):
        _copy_cached_fixture(cache_path, converter_dataset)
        return True

    if cache_path.exists():
        cache_path.unlink()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        runner.run(
            [
                "uv",
                "run",
                "--isolated",
                "--frozen",
                "--package",
                "nmp-rl",
                "--extra",
                "conversion",
                "pi-to-gym-conversion",
                "--hub-id",
                PRIME_FIXTURE_HUB_ID,
                "--hub-version",
                PRIME_FIXTURE_HUB_VERSION,
                "--out-dir",
                str(converter_environment),
                "--dataset-dir",
                str(converter_dataset),
                "--dataset-size",
                str(PRIME_FIXTURE_SIZE),
                "--dataset-seed",
                str(PRIME_FIXTURE_SEED),
            ]
        )
        converted_dataset = converter_dataset / "training.jsonl"
        if not _valid_fixture_cache(converted_dataset):
            raise RuntimeError(f"converter did not produce {PRIME_FIXTURE_SIZE} valid rows at {converted_dataset}")

        # Replace atomically so an interrupted conversion cannot expose a partial cache.
        with tempfile.NamedTemporaryFile(dir=cache_path.parent, delete=False) as temporary_file:
            temporary_cache_path = Path(temporary_file.name)
        try:
            shutil.copy2(converted_dataset, temporary_cache_path)
            temporary_cache_path.replace(cache_path)
        finally:
            temporary_cache_path.unlink(missing_ok=True)
    finally:
        if converter_environment.exists():
            shutil.rmtree(converter_environment)
        if converter_dataset.exists():
            shutil.rmtree(converter_dataset)

    _copy_cached_fixture(cache_path, converter_dataset)
    return False


def _adapt_row(row: dict[str, Any], *, position: int) -> dict[str, Any]:
    """Retarget one source row from Prime Intellect's agent to ``simple_agent``."""
    response_parameters = row.get("responses_create_params")
    if not isinstance(response_parameters, dict):
        raise ValueError(f"row {position} has no responses_create_params mapping")
    prompt = response_parameters.get("input")
    if not isinstance(prompt, list) or not prompt:
        raise ValueError(f"row {position} has no prompt in responses_create_params.input")
    answer = row.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"row {position} has no non-empty answer")

    adapted_row = dict(row)
    adapted_row["agent_ref"] = {
        "type": "responses_api_agents",
        "name": "simple_agent",
    }
    return adapted_row


def _adapt_dataset(converter_dataset: Path, dataset_output: Path) -> int:
    """Write source rows in the standard Gym JSONL shape and return their count."""
    source_rows = read_jsonl(converter_dataset)
    if not source_rows:
        raise ValueError(f"{converter_dataset} contains no dataset rows")
    adapted_rows = [_adapt_row(row, position=position) for position, row in enumerate(source_rows, start=1)]
    dataset_output.parent.mkdir(parents=True, exist_ok=True)
    dataset_output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in adapted_rows),
        encoding="utf-8",
    )
    return len(adapted_rows)


def _wheel_source_digest() -> str:
    """Hash scorer source paths and contents for deterministic cache invalidation."""
    digest = hashlib.sha256()
    source_files = sorted(
        path for path in WHEEL_SOURCE.rglob("*") if path.is_file() and "__pycache__" not in path.parts
    )
    for source_file in source_files:
        relative_path = source_file.relative_to(WHEEL_SOURCE)
        digest.update(relative_path.as_posix().encode())
        digest.update(b"\0")
        digest.update(source_file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _cached_scorer_wheel(runner: CommandRunner) -> tuple[Path, bool]:
    """Return a source-matched scorer wheel, building it only when absent."""
    cache_directory = WHEEL_CACHE / _wheel_source_digest()
    cached_wheels = sorted(cache_directory.glob(f"{SCORER_DISTRIBUTION}-*.whl"))
    if len(cached_wheels) == 1:
        return cached_wheels[0], True
    if cached_wheels:
        shutil.rmtree(cache_directory)

    cache_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nmp-ascii-tree-wheel-") as temporary_directory:
        distribution_directory = Path(temporary_directory)
        runner.run(
            [
                "uv",
                "build",
                "--wheel",
                "--clear",
                "--out-dir",
                str(distribution_directory),
                str(WHEEL_SOURCE),
            ]
        )
        built_wheels = sorted(distribution_directory.glob(f"{SCORER_DISTRIBUTION}-*.whl"))
        if len(built_wheels) != 1:
            raise RuntimeError(f"expected one {SCORER_DISTRIBUTION} wheel, found: {built_wheels}")
        cached_wheel = cache_directory / built_wheels[0].name
        shutil.copy2(built_wheels[0], cached_wheel)
        return cached_wheel, False


def _materialize_environment(runner: CommandRunner, environment_output: Path) -> tuple[Path, bool]:
    """Copy the example package and place its cached scorer wheel in the wheelhouse."""
    if environment_output.exists():
        shutil.rmtree(environment_output)
    shutil.copytree(ENVIRONMENT_TEMPLATE, environment_output)

    scorer_wheel, cache_hit = _cached_scorer_wheel(runner)
    wheels_directory = environment_output / "wheels"
    wheels_directory.mkdir(parents=True, exist_ok=True)
    for existing_path in wheels_directory.iterdir():
        if existing_path.is_dir():
            shutil.rmtree(existing_path)
        else:
            existing_path.unlink()
    wheel_destination = wheels_directory / scorer_wheel.name
    shutil.copy2(scorer_wheel, wheel_destination)
    return wheel_destination, cache_hit


def prepare_example(
    runner: CommandRunner,
    *,
    converter_environment: Path,
    converter_dataset: Path,
    environment_output: Path,
    dataset_output: Path,
) -> dict[str, Any]:
    """Build the default complete environment and dataset for generic validation."""
    fixture_cache_hit = _convert_fixture(
        runner,
        converter_environment=converter_environment,
        converter_dataset=converter_dataset,
    )
    scorer_wheel, wheel_cache_hit = _materialize_environment(runner, environment_output)
    row_count = _adapt_dataset(converter_dataset / "training.jsonl", dataset_output)
    return {
        "input_mode": "default-ascii-tree",
        "input_label": "bundled ASCII Tree example",
        "rows": row_count,
        "wheels": [scorer_wheel.name],
        "fixture_cache_hit": fixture_cache_hit,
        "wheel_cache_hit": wheel_cache_hit,
    }
