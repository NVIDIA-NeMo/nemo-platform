# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build-if-missing provisioning for the Fabric sandbox image.

``FabricContainerRuntime`` needs a container image with Fabric + its harness runtimes. Rather than
make callers hand-write a Dockerfile, the SDK owns the recipe (:mod:`sandbox.Dockerfile`, a
multi-stage build) and provisions the image opaquely: :func:`ensure_fabric_image` returns a usable
image tag, building it only when it isn't already present locally. This mirrors the
``ensure_task_image`` build-if-missing pattern (``docker image inspect`` → ``docker build``).

The tag is content-addressed on the recipe + selected extras, so a recipe change produces a new tag
(cache-bust) and an unchanged recipe reuses the cached image. The Fabric source is private/native
(no public wheel), so the build needs a local NeMo-Fabric checkout — resolved from ``fabric_repo`` /
``$NEMO_FABRIC_REPO`` / ``~/workspace/NeMo-Fabric``. Only the maturin build inputs are staged into the
context (not the whole repo), and the multi-stage build keeps the source and Rust toolchain out of the
final image.

This is the local-Docker provisioning path. The intended evolution is a remote image registry as a
cache: :func:`ensure_fabric_image` keeps the same "return a usable tag" contract, its body swapping
local build for a registry pull (build-and-push on miss).

DEPENDENCY (as of July 2026): the multi-stage image installs the ``nemo-fabric`` wheel and discards
the source, so Fabric must be able to resolve built-in adapters *from the installed distribution*.
That only works on NeMo-Fabric's ``installed-adapter-discovery`` branch (which bundles the adapters
under ``python/src/nemo_fabric/adapters`` and adds ``AdapterDescriptorSource::Installed``). On today's
``main`` the wheel ships no adapter descriptors, so a wheel-only image cannot resolve e.g.
``nvidia.fabric.hermes.sdk``. Once that lands on ``main``, switch to installing the top-level
``adapters/*`` packages explicitly here instead of relying on the branch's packaging.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ``localhost/`` prefix so Docker treats it as an explicit local registry and does NOT qualify the tag
# to ``docker.io/…`` — this image is built locally and never pushed to Docker Hub.
DEFAULT_FABRIC_IMAGE_REPO = "localhost/nemo-evaluator/fabric-sandbox"
FABRIC_REPO_ENV = "NEMO_FABRIC_REPO"
_DEFAULT_FABRIC_REPO = Path.home() / "workspace" / "NeMo-Fabric"
_DOCKERFILE = Path(__file__).with_name("sandbox.Dockerfile")

# Bound the docker subprocess calls so an unresponsive daemon fails fast instead of hanging the runtime.
# ``inspect`` is near-instant; the build compiles nemo-fabric (minutes), so it gets a generous ceiling.
_INSPECT_TIMEOUT_S = 30
_BUILD_TIMEOUT_S = 3600

#: Harness runtime deps baked into the (single, harness-agnostic) Fabric image. The native
#: ``nemo-fabric`` build plus *all* built-in adapter descriptors are always present, so the CLI can
#: resolve any built-in harness; these extras add the per-harness *runtime* deps (``hermes`` →
#: ``hermes-agent``; ``relay`` → the ATIF exporter). Codex additionally needs node + the codex CLI +
#: the nemo-relay gateway binary and is not provisioned yet (see AALGO-321); append it here when ready.
_EXTRAS: tuple[str, ...] = ("hermes", "relay")

#: Paths under the NeMo-Fabric checkout that the maturin build actually needs. Staging only these
#: (rather than the whole repo) keeps the build context small; the multi-stage build keeps them out
#: of the final image entirely.
_BUILD_SOURCE_PATHS = ("Cargo.toml", "Cargo.lock", "pyproject.toml", "README.md", "crates", "python")


class FabricImageError(RuntimeError):
    """Raised when the Fabric sandbox image cannot be provisioned."""


def _extras_arg() -> str:
    return ",".join(_EXTRAS)


def fabric_image_tag(*, repo: str = DEFAULT_FABRIC_IMAGE_REPO) -> str:
    """Content-addressed tag for the harness-agnostic Fabric image: ``<repo>:<digest(recipe + extras)>``.

    Not keyed by harness: one Fabric install + the bundled adapters runs any built-in harness, so the
    image is the same regardless of which harness a task's config selects.
    """
    recipe = _DOCKERFILE.read_bytes() + _extras_arg().encode("utf-8")
    return f"{repo}:{hashlib.sha256(recipe).hexdigest()[:12]}"


def image_exists(tag: str, *, docker_bin: str = "docker") -> bool:
    """Whether an image tag is present in the local Docker image store.

    Raises :class:`FabricImageError` when the Docker daemon is unreachable, so a stopped/misconfigured
    daemon surfaces as a clear error instead of masquerading as "image absent" and triggering a build
    that then also fails confusingly.
    """
    try:
        result = subprocess.run(
            [docker_bin, "image", "inspect", tag], capture_output=True, check=False, timeout=_INSPECT_TIMEOUT_S
        )
    except subprocess.TimeoutExpired as exc:
        raise FabricImageError(
            f"`docker image inspect` timed out after {_INSPECT_TIMEOUT_S}s (daemon unresponsive?)"
        ) from exc
    if result.returncode == 0:
        return True
    stderr = result.stderr.decode("utf-8", errors="replace")
    if "cannot connect to the docker daemon" in stderr.lower():
        raise FabricImageError(f"cannot reach the Docker daemon (is it running?): {stderr.strip()}")
    logger.debug("Fabric image %s not present in local store", tag)
    return False


def _resolve_fabric_repo(fabric_repo: str | Path | None) -> Path:
    default = Path(os.environ.get(FABRIC_REPO_ENV, _DEFAULT_FABRIC_REPO))
    repo = (Path(fabric_repo) if fabric_repo is not None else default).expanduser()
    if not (repo / "pyproject.toml").is_file():
        raise FabricImageError(
            f"NeMo-Fabric source not found at {repo}. The Fabric image is built from source "
            f"(no public wheel); set {FABRIC_REPO_ENV} or pass fabric_repo to point at a checkout."
        )
    return repo


def _stage_source(repo: Path, dest: Path) -> None:
    """Copy only the maturin build inputs from ``repo`` into ``dest`` (not the whole checkout)."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in _BUILD_SOURCE_PATHS:
        src = repo / name
        if src.is_dir():
            shutil.copytree(src, dest / name, ignore=shutil.ignore_patterns("target", "__pycache__", "*.whl"))
        elif src.is_file():
            shutil.copy2(src, dest / name)
        else:
            raise FabricImageError(f"expected Fabric build input {name!r} not found under {repo}")


def ensure_fabric_image(
    *,
    fabric_repo: str | Path | None = None,
    docker_bin: str = "docker",
    force_build: bool = False,
) -> str:
    """Return a usable Fabric image tag, building it only if not already present.

    One harness-agnostic image serves every built-in harness. Idempotent and content-addressed: an
    unchanged recipe reuses the cached image; a changed recipe yields a new tag. Builds from a staged
    copy of the local NeMo-Fabric source (build inputs only).
    """
    tag = fabric_image_tag()
    if not force_build and image_exists(tag, docker_bin=docker_bin):
        logger.debug("Fabric image %s already present; skipping build.", tag)
        return tag

    repo = _resolve_fabric_repo(fabric_repo)
    logger.info(
        "Building Fabric image (first build compiles nemo-fabric; this can take minutes)...",
        extra=dict(tag=tag, repo=repo),
    )
    with tempfile.TemporaryDirectory(prefix="nemo-fabric-image-") as ctx_dir:
        ctx = Path(ctx_dir)
        _stage_source(repo, ctx / "nemo-fabric")
        shutil.copy2(_DOCKERFILE, ctx / "Dockerfile")
        try:
            subprocess.run(
                [docker_bin, "build", "--build-arg", f"EXTRAS={_extras_arg()}", "-t", tag, str(ctx)],
                check=True,
                env={**os.environ, "DOCKER_BUILDKIT": "1"},
                timeout=_BUILD_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise FabricImageError(f"docker build timed out after {_BUILD_TIMEOUT_S}s for {tag}") from exc
        except subprocess.CalledProcessError as exc:
            raise FabricImageError(f"docker build failed for {tag}: {exc}") from exc
    logger.info("Built Fabric image %s.", tag, extra=dict(tag=tag))
    return tag
