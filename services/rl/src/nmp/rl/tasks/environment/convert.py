# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prime Intellect hub → adapter-wheels-v1 conversion (CLI-first, internet on host)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nmp.rl.tasks.environment.allowlist import DEFAULT_ADAPTER_AGENT
from nmp.rl.tasks.environment.package import (
    ConvertedPackage,
    dataset_row_from_verifiers,
    hub_id_to_package_name,
    hub_id_to_vf_env_id,
    write_adapter_wheels_package,
    write_dataset_jsonl,
)
from nmp.rl.tasks.environment.validate import validate_dataset_rows
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

PRIME_HUB_SIMPLE_INDEX = "https://hub.primeintellect.ai/primeintellect/simple/"
DEFAULT_VERIFIERS_SPEC = "verifiers @ git+https://github.com/PrimeIntellect-ai/verifiers.git@v0.1.14"


@dataclass(frozen=True)
class ConvertEnvironmentSpec:
    hub_id: str
    out_dir: Path
    dataset_dir: Path | None = None
    vf_env_id: str | None = None
    vf_env_args: dict[str, Any] | None = None
    adapter_agent: str = DEFAULT_ADAPTER_AGENT
    dataset_size: int = -1
    dataset_seed: int | None = None
    validation_fraction: float = 0.0
    verifiers_spec: str = DEFAULT_VERIFIERS_SPEC
    extra_wheels: tuple[str, ...] = ()
    # Pre-vendored wheels for air-gapped hosts; must contain at least one *.whl.
    wheels_dir: Path | None = None


def _run_pip_download(
    dest: Path,
    packages: list[str],
    *,
    extra_index_url: str | None = None,
) -> None:
    """Vendor wheels via ``pip download`` using this process's interpreter.

    ``pip`` is a declared ``nmp-rl`` dependency so the synced env can run
    ``python -m pip`` without nested ``uv run`` bootstraps.
    """
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(dest),
        "--no-cache-dir",
    ]
    if extra_index_url:
        cmd.extend(["--extra-index-url", extra_index_url])
    cmd.extend(packages)
    logger.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def download_hub_wheels(
    spec: ConvertEnvironmentSpec,
    *,
    work_dir: Path,
) -> Path:
    """Vendor transitive wheel closure for hub env + verifiers.

    ``adapter-wheels-v1`` always requires a non-empty ``wheels/`` tree. Either
    copy from ``spec.wheels_dir`` or download from the hub index — never emit
    an empty/stub package.
    """
    wheels_dir = work_dir / "wheels"
    if spec.wheels_dir is not None:
        src_wheels = sorted(spec.wheels_dir.glob("*.whl"))
        if not src_wheels:
            raise ValueError(
                f"--wheels-dir {spec.wheels_dir} has no *.whl files; adapter-wheels-v1 requires a wheel closure"
            )
        wheels_dir.mkdir(parents=True, exist_ok=True)
        for whl in src_wheels:
            shutil.copy2(whl, wheels_dir / whl.name)
        return wheels_dir

    package_name = hub_id_to_package_name(spec.hub_id)
    packages = [spec.verifiers_spec, package_name, *spec.extra_wheels]
    _run_pip_download(wheels_dir, packages, extra_index_url=PRIME_HUB_SIMPLE_INDEX)
    downloaded = sorted(wheels_dir.glob("*.whl"))
    if not downloaded:
        raise RuntimeError(
            f"pip download produced no wheels for {packages!r}; adapter-wheels-v1 requires a wheel closure"
        )
    return wheels_dir


def _wheel_version(path: Path) -> Version:
    """Parse the version segment of a wheel filename (``name-version-...whl``)."""
    parts = path.name.split("-")
    try:
        return Version(parts[1]) if len(parts) > 1 else Version("0")
    except InvalidVersion:
        return Version("0")


def _install_hub_package_from_wheels(wheels_dir: Path, package_name: str) -> None:
    """Install the hub env package so ``verifiers.load_environment`` can resolve it."""
    candidates = sorted(wheels_dir.glob(f"{package_name}-*.whl"))
    if not candidates:
        dashed = package_name.replace("_", "-")
        candidates = sorted(wheels_dir.glob(f"{dashed}-*.whl"))
    if not candidates:
        raise RuntimeError(f"No wheel for hub package {package_name!r} under {wheels_dir}; cannot load dataset")
    # Filename order is lexicographic, which puts 0.9.0 after 0.10.0 — pick by parsed
    # version so host-side dataset generation uses the same build the cluster installs.
    whl = max(candidates, key=_wheel_version)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--force-reinstall",
        str(whl),
    ]
    logger.warning(
        "Installing untrusted hub package %s into the active interpreter at %s. This "
        "mutates that environment (it will no longer match uv.lock) and the package stays "
        "importable afterwards. Run pi-to-gym-conversion in a throwaway venv if that matters.",
        whl.name,
        sys.executable,
    )
    logger.info("Installing hub package for dataset load: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _load_verifiers_dataset_rows(
    vf_env_id: str,
    vf_env_args: dict[str, Any],
    *,
    size: int,
    seed: int | None,
) -> list[dict[str, Any]]:
    try:
        import verifiers as vf
    except ImportError as exc:
        raise RuntimeError(
            "verifiers is required for pi-to-gym-conversion dataset generation; "
            "it is a declared nmp-rl dependency — run `uv sync --package nmp-rl`"
        ) from exc

    env = vf.load_environment(vf_env_id, **vf_env_args)
    try:
        dataset = env.get_dataset(n=size, seed=seed)
    except ValueError:
        dataset = env.get_eval_dataset(n=size, seed=seed)

    rows: list[dict[str, Any]] = []
    for i in range(len(dataset)):
        prompt = dataset["prompt"][i]
        # example_id is optional upstream just like answer/task/info; hub envs that omit
        # it would otherwise raise KeyError partway through conversion.
        example_id = dataset["example_id"][i] if "example_id" in dataset.column_names else i
        answer = dataset["answer"][i] if "answer" in dataset.column_names else ""
        task = dataset["task"][i] if "task" in dataset.column_names else vf_env_id
        info = dataset["info"][i] if "info" in dataset.column_names else {}
        rows.append(
            dataset_row_from_verifiers(
                idx=i,
                prompt=prompt,
                vf_env_id=vf_env_id,
                example_id=example_id,
                answer=answer,
                task=task,
                info=info if isinstance(info, dict) else {},
            )
        )
    return rows


def split_train_validation(
    rows: list[dict[str, Any]],
    validation_fraction: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Split rows into (train, validation), refusing splits that leave no training rows.

    Silently falling back to the full set for training would make the two files
    identical, and GRPO ranks checkpoints on ``val:total_reward/mean`` — so the run
    would select a best checkpoint against its own training data with nothing to
    indicate it.
    """
    if not rows or validation_fraction <= 0:
        return rows, None
    split = max(1, int(len(rows) * validation_fraction))
    if split >= len(rows):
        raise ValueError(
            f"validation_fraction={validation_fraction} leaves no training rows "
            f"({len(rows)} row(s) available, {split} would go to validation). "
            "Use a smaller fraction or generate more rows."
        )
    return rows[split:], rows[:split]


def convert_prime_environment(spec: ConvertEnvironmentSpec) -> ConvertedPackage:
    """Convert a Prime Intellect hub environment to adapter-wheels-v1 + Gym JSONL."""
    vf_env_id = spec.vf_env_id or hub_id_to_vf_env_id(spec.hub_id)
    vf_env_args = spec.vf_env_args or {}
    env_out = spec.out_dir
    dataset_out = spec.dataset_dir or (spec.out_dir.parent / f"{env_out.name}-dataset")
    package_name = hub_id_to_package_name(spec.hub_id)

    with tempfile.TemporaryDirectory(prefix="nmp-rl-convert-") as tmp:
        wheels_dir = download_hub_wheels(spec, work_dir=Path(tmp))
        manifest = write_adapter_wheels_package(
            out_dir=env_out,
            hub_id=spec.hub_id,
            vf_env_id=vf_env_id,
            vf_env_args=vf_env_args,
            adapter_agent=spec.adapter_agent,
            wheels_src=wheels_dir,
        )

    # dataset_size == 0 skips JSONL generation (package layout only).
    if spec.dataset_size == 0:
        all_rows: list[dict[str, Any]] = []
    else:
        _install_hub_package_from_wheels(env_out / "wheels", package_name)
        all_rows = _load_verifiers_dataset_rows(
            vf_env_id,
            vf_env_args,
            size=spec.dataset_size,
            seed=spec.dataset_seed,
        )
        if not all_rows:
            raise RuntimeError(
                f"Dataset generation for {spec.hub_id!r} (vf_env_id={vf_env_id!r}) "
                f"returned 0 rows (dataset_size={spec.dataset_size})"
            )

    train_rows, val_rows = split_train_validation(all_rows, spec.validation_fraction)

    if train_rows:
        validate_dataset_rows(
            train_rows,
            expected_vf_env_id=vf_env_id,
            expected_agent=spec.adapter_agent,
        )

    train_path, val_path = write_dataset_jsonl(
        dataset_dir=dataset_out,
        rows=train_rows,
        validation_rows=val_rows,
    )

    return ConvertedPackage(
        environment_root=env_out,
        dataset_dir=dataset_out,
        manifest=manifest,
        training_jsonl=train_path,
        validation_jsonl=val_path,
    )
