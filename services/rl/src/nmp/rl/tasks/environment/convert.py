# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prime Intellect hub → adapter-wheels-v1 conversion (CLI-first, internet on host)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from nmp.customization_common.service.constants import SANDBOX_DATASET_PATH
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

# Training image is linux/amd64; resolve and download for that, not this host.
# pip matches --platform tags literally, so several glibc floors are listed.
TARGET_WHEEL_PLATFORMS = (
    "manylinux_2_39_x86_64",
    "manylinux_2_28_x86_64",
    "manylinux_2_17_x86_64",
    "manylinux2014_x86_64",
)
TARGET_UV_PLATFORM = "x86_64-unknown-linux-gnu"
TARGET_PYTHON_VERSION = "3.13"  # Gym venv Python in the training image
_TARGET_PLATFORM_TAG_RE = re.compile(r"^(any|linux_x86_64|manylinux[0-9_.]*_x86_64)$")

# Snapshot of the hub env's HF dataset, mounted at SANDBOX_DATASET_PATH.
HUB_ENV_DATASET_FILENAME = "hub_environment.parquet"
DATASET_PATH_ARG = "dataset_path"
# Isolated Hugging Face cache from convert, for loaders that ignore dataset_path.
HUB_ENV_HF_CACHE_DIRNAME = ".huggingface"


@dataclass(frozen=True)
class ConvertEnvironmentSpec:
    hub_id: str
    out_dir: Path
    hub_version: str | None = None  # pin the hub release; unset follows the index
    dataset_dir: Path | None = None
    vf_env_id: str | None = None
    vf_env_args: dict[str, Any] | None = None  # host-side load args; dataset_path is overwritten
    adapter_agent: str = DEFAULT_ADAPTER_AGENT
    dataset_size: int = -1
    dataset_seed: int | None = None
    validation_fraction: float = 0.0
    verifiers_spec: str = DEFAULT_VERIFIERS_SPEC
    extra_wheels: tuple[str, ...] = ()
    wheels_dir: Path | None = None  # pre-vendored *.whl; required non-empty if set


def _compile_pinned_requirements(
    work_dir: Path,
    packages: list[str],
    *,
    extra_index_url: str | None = None,
) -> Path:
    """Pin ``packages`` before download so ``pip download --no-deps`` cannot vendor duplicates."""
    work_dir.mkdir(parents=True, exist_ok=True)
    requirements_in = work_dir / "requirements.in"
    requirements_in.write_text("\n".join(packages) + "\n", encoding="utf-8")
    pinned = work_dir / "requirements.txt"
    cmd = [
        "uv",
        "pip",
        "compile",
        str(requirements_in),
        "--output-file",
        str(pinned),
        "--no-header",
        "--no-config",  # ignore this repo's uv overrides; they are not applied on the cluster
        "--python-platform",
        TARGET_UV_PLATFORM,
        "--python-version",
        TARGET_PYTHON_VERSION,
    ]
    if extra_index_url:
        cmd.extend(["--extra-index-url", extra_index_url, "--index-strategy", "unsafe-best-match"])
    logger.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    logger.info("Resolved closure:\n%s", pinned.read_text(encoding="utf-8").strip())
    return pinned


def _run_pip_download(
    dest: Path,
    *,
    requirements_file: Path,
    extra_index_url: str | None = None,
) -> None:
    """Download the already-pinned closure with ``pip download --no-deps``."""
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(dest),
        "--no-cache-dir",
        "--no-deps",
        "--python-version",
        TARGET_PYTHON_VERSION,
    ]
    for platform_tag in TARGET_WHEEL_PLATFORMS:
        cmd.extend(["--platform", platform_tag])
    cmd.extend(["-r", str(requirements_file)])
    if extra_index_url:
        cmd.extend(["--extra-index-url", extra_index_url])
    logger.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _wheel_platform_tags(wheel: Path) -> list[str]:
    """Platform tags a wheel declares, e.g. ``manylinux2014_x86_64.manylinux_2_17_x86_64``."""
    return wheel.stem.rsplit("-", 1)[-1].split(".")


def assert_wheels_target_platform(wheels_dir: Path) -> None:
    """Reject wheels that are not pure-Python or linux x86_64."""
    foreign: dict[str, list[str]] = {}
    for wheel in sorted(wheels_dir.glob("*.whl")):
        tags = _wheel_platform_tags(wheel)
        if not any(_TARGET_PLATFORM_TAG_RE.match(tag) for tag in tags):
            foreign[wheel.name] = tags
    if foreign:
        listed = "\n  ".join(f"{name} -> {', '.join(tags)}" for name, tags in foreign.items())
        raise RuntimeError(
            f"{len(foreign)} vendored wheel(s) are not installable on the training image "
            f"(expected pure-Python or linux x86_64):\n  {listed}"
        )


def download_hub_wheels(
    spec: ConvertEnvironmentSpec,
    *,
    work_dir: Path,
) -> Path:
    """Copy ``spec.wheels_dir`` or download the hub env + verifiers closure."""
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
        assert_wheels_target_platform(wheels_dir)
        return wheels_dir

    package_name = hub_id_to_package_name(spec.hub_id)
    hub_requirement = f"{package_name}=={spec.hub_version}" if spec.hub_version else package_name
    packages = [spec.verifiers_spec, hub_requirement, *spec.extra_wheels]
    pinned = _compile_pinned_requirements(work_dir, packages, extra_index_url=PRIME_HUB_SIMPLE_INDEX)
    _run_pip_download(wheels_dir, requirements_file=pinned, extra_index_url=PRIME_HUB_SIMPLE_INDEX)
    downloaded = sorted(wheels_dir.glob("*.whl"))
    if not downloaded:
        raise RuntimeError(
            f"pip download produced no wheels for {packages!r}; adapter-wheels-v1 requires a wheel closure"
        )
    sdists = sorted(p.name for p in wheels_dir.iterdir() if p.is_file() and p.suffix != ".whl")
    if sdists:
        logger.warning(
            "Not vendoring %d source-only artifact(s): %s. They are excluded from the "
            "package and must be satisfied when the Gym server venv is built.",
            len(sdists),
            ", ".join(sdists),
        )
    assert_wheels_target_platform(wheels_dir)
    return wheels_dir


def _wheel_version(path: Path) -> Version:
    """Parse the version segment of a wheel filename (``name-version-...whl``)."""
    parts = path.name.split("-")
    try:
        return Version(parts[1]) if len(parts) > 1 else Version("0")
    except InvalidVersion:
        return Version("0")


def _hub_package_wheel(wheels_dir: Path, package_name: str) -> Path:
    """Pick the hub env wheel the cluster will install (highest parsed version)."""
    candidates = sorted(wheels_dir.glob(f"{package_name}-*.whl"))
    if not candidates:
        dashed = package_name.replace("_", "-")
        candidates = sorted(wheels_dir.glob(f"{dashed}-*.whl"))
    if not candidates:
        raise RuntimeError(f"No wheel for hub package {package_name!r} under {wheels_dir}; cannot load dataset")
    return max(candidates, key=_wheel_version)


def _sandbox_hub_dataset_path(filename: str = HUB_ENV_DATASET_FILENAME) -> str:
    return f"{SANDBOX_DATASET_PATH.rstrip('/')}/{filename}"


@contextmanager
def _isolated_hf_home(hf_home: Path) -> Iterator[Path]:
    """Point ``HF_HOME`` at ``hf_home`` for the duration of the block.

    Conversion must not copy the developer's ``~/.cache/huggingface``; loaders
    populate this temp home, which is then snapshotted into the dataset FileSet.
    """
    hf_home.mkdir(parents=True, exist_ok=True)
    previous = os.environ.get("HF_HOME")
    os.environ["HF_HOME"] = str(hf_home)
    try:
        yield hf_home
    finally:
        if previous is None:
            os.environ.pop("HF_HOME", None)
        else:
            os.environ["HF_HOME"] = previous


def snapshot_huggingface_home(hf_home: Path, dataset_dir: Path) -> Path | None:
    """Copy the isolated Hugging Face home into ``dataset_dir/.huggingface``."""
    if not hf_home.is_dir() or not any(hf_home.iterdir()):
        logger.warning(
            "isolated HF_HOME at %s is empty after load_environment; "
            "not writing %s (parquet dataset_path remains the primary contract)",
            hf_home,
            HUB_ENV_HF_CACHE_DIRNAME,
        )
        return None
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dest = dataset_dir / HUB_ENV_HF_CACHE_DIRNAME
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(hf_home, dest)
    logger.info("Snapshotted isolated Hugging Face cache to %s", dest)
    return dest


def vendor_hub_environment_dataset(env: Any, dataset_dir: Path) -> Path:
    """Write the hub env's Hugging Face dataset into the dataset FileSet as parquet."""
    dataset = getattr(env, "dataset", None)
    if dataset is None:
        raise RuntimeError(
            "hub environment has no .dataset to vendor into the dataset FileSet; "
            "the Gym sandbox would otherwise call Hugging Face at load_environment()"
        )
    if not hasattr(dataset, "to_parquet"):
        raise RuntimeError(f"hub environment dataset type {type(dataset)!r} cannot be written as parquet")
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dest = dataset_dir / HUB_ENV_DATASET_FILENAME
    dataset.to_parquet(str(dest))
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError(f"failed to vendor hub environment dataset to {dest}")
    logger.info("Vendored hub environment dataset to %s (%d bytes)", dest, dest.stat().st_size)
    return dest


def _install_hub_package_from_wheels(wheels_dir: Path, package_name: str) -> None:
    """Install only the hub env wheel so ``load_environment`` can import it.

    ``--no-deps`` because ``verifiers`` comes from the conversion extra, and the
    download dir can still contain sdists (e.g. ``verifiers-*.zip``) that pip would
    otherwise try to build, needing hatchling and failing ``--no-index``.
    """
    whl = _hub_package_wheel(wheels_dir, package_name)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-index",
        "--no-deps",
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
    logger.warning(
        "Installing untrusted hub package %s into the active interpreter at %s. This "
        "mutates that environment (it will no longer match uv.lock) and the package stays "
        "importable afterwards. Run pi-to-gym-conversion in a throwaway venv if that matters.",
        whl.name,
        sys.executable,
    )
    logger.info("Installing hub package for dataset load: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _load_verifiers_environment(vf_env_id: str, vf_env_args: dict[str, Any]) -> Any:
    try:
        import verifiers as vf  # conversion extra
    except ImportError as exc:
        raise RuntimeError(
            "verifiers is required for pi-to-gym-conversion dataset generation; it lives in "
            "the optional `conversion` extra — run "
            "`uv sync --package nmp-rl --extra conversion`"
        ) from exc

    return vf.load_environment(vf_env_id, **vf_env_args)


def _dataset_rows_from_env(
    env: Any,
    vf_env_id: str,
    *,
    size: int,
    seed: int | None,
) -> list[dict[str, Any]]:
    try:
        dataset = env.get_dataset(n=size, seed=seed)
    except ValueError:
        dataset = env.get_eval_dataset(n=size, seed=seed)

    rows: list[dict[str, Any]] = []
    for i in range(len(dataset)):
        prompt = dataset["prompt"][i]
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


def _load_verifiers_dataset_rows(
    vf_env_id: str,
    vf_env_args: dict[str, Any],
    *,
    size: int,
    seed: int | None,
) -> list[dict[str, Any]]:
    env = _load_verifiers_environment(vf_env_id, vf_env_args)
    return _dataset_rows_from_env(env, vf_env_id, size=size, seed=seed)


def split_train_validation(
    rows: list[dict[str, Any]],
    validation_fraction: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Split rows into (train, validation). Raises if the split would empty training."""
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
    host_vf_env_args = dict(spec.vf_env_args or {})
    package_vf_env_args = dict(host_vf_env_args)
    env_out = spec.out_dir
    dataset_out = spec.dataset_dir or (spec.out_dir.parent / f"{env_out.name}-dataset")
    package_name = hub_id_to_package_name(spec.hub_id)

    with tempfile.TemporaryDirectory(prefix="nmp-rl-convert-") as tmp:
        wheels_dir = download_hub_wheels(spec, work_dir=Path(tmp))

        if spec.dataset_size == 0:  # package layout only
            all_rows: list[dict[str, Any]] = []
        else:
            hf_home = Path(tmp) / "hf-home"
            with _isolated_hf_home(hf_home):
                _install_hub_package_from_wheels(wheels_dir, package_name)
                env = _load_verifiers_environment(vf_env_id, host_vf_env_args)
                all_rows = _dataset_rows_from_env(
                    env,
                    vf_env_id,
                    size=spec.dataset_size,
                    seed=spec.dataset_seed,
                )
                if not all_rows:
                    raise RuntimeError(
                        f"Dataset generation for {spec.hub_id!r} (vf_env_id={vf_env_id!r}) "
                        f"returned 0 rows (dataset_size={spec.dataset_size})"
                    )
                vendor_hub_environment_dataset(env, dataset_out)
                snapshot_huggingface_home(hf_home, dataset_out)
                package_vf_env_args[DATASET_PATH_ARG] = _sandbox_hub_dataset_path()

        manifest = write_adapter_wheels_package(
            out_dir=env_out,
            hub_id=spec.hub_id,
            vf_env_id=vf_env_id,
            vf_env_args=package_vf_env_args,
            adapter_agent=spec.adapter_agent,
            wheels_src=wheels_dir,
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
