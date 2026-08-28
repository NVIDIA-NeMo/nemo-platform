#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare sandboxed rho-agent Harbor runs for the Eval Author walkthrough."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

RHO_REVISION = os.environ["RHO_REVISION"]
RHO_AGENT_REPO = os.environ["RHO_AGENT_REPO"]
RHO_AGENT_ROOT = os.environ["RHO_AGENT_ROOT"]
RHO_AGENT_VENV_PYTHON = f"{RHO_AGENT_ROOT}/.venv/bin/python"
IMAGE_REPOSITORY = os.environ["IMAGE_REPOSITORY"]
IMAGE_TAG = RHO_REVISION[:12]
IMAGE_REF = f"{IMAGE_REPOSITORY}:{IMAGE_TAG}"
DEFAULT_INFERENCE_BASE_URL = os.environ["DEFAULT_INFERENCE_BASE_URL"]

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "rho-agent"
SANDBOX_TASKS = Path(__file__).resolve().parent / "sandbox-tasks"


def workspace_rho_agent_path(workspace: Path) -> Path:
    return workspace / os.environ["RHO_AGENT_CHECKOUT"]


def inference_allowlist_hosts(base_url: str | None = None) -> list[str]:
    url = (base_url or DEFAULT_INFERENCE_BASE_URL).strip()
    if not url:
        return [host.strip() for host in os.environ["DEFAULT_INFERENCE_HOSTS"].split(",") if host.strip()]

    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.hostname
    if host is None:
        return [host.strip() for host in os.environ["DEFAULT_INFERENCE_HOSTS"].split(",") if host.strip()]
    return [host]


class PrepareError(RuntimeError):
    """User-correctable prepare failure."""


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise PrepareError(f"{' '.join(command)}: {detail}")
    return result


def docker_image_exists(image_ref: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def clone_rho_agent(workspace: Path, *, force: bool = False) -> Path:
    """Clone pinned rho-agent source into the walkthrough workspace."""
    checkout = workspace_rho_agent_path(workspace.resolve())
    if checkout.is_dir() and not force:
        head = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode == 0 and head.stdout.strip() == RHO_REVISION:
            return checkout
        shutil.rmtree(checkout)
    elif checkout.exists():
        shutil.rmtree(checkout)

    checkout.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", RHO_AGENT_REPO, str(checkout)])
    _run(["git", "-C", str(checkout), "checkout", RHO_REVISION])
    return checkout


def build_agent_image(*, image_ref: str = IMAGE_REF, force: bool = False) -> str:
    """Build the pre-baked rho-agent Harbor image on the Docker host."""
    if not force and docker_image_exists(image_ref):
        return image_ref

    if shutil.which("docker") is None:
        raise PrepareError("docker not found on PATH")

    script = Path(__file__).resolve().parent / "build_agent_image.sh"
    if not script.is_file():
        raise PrepareError(f"missing build script: {script}")

    env = os.environ.copy()
    env["RHO_AGENT_IMAGE"] = image_ref
    result = subprocess.run(
        ["bash", str(script)],
        cwd=script.parent,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise PrepareError(f"failed to build rho-agent image {image_ref}")
    return image_ref


# Keep in sync with Harbor's DockerEnvironment egress kernel probe (harbor 0.22+).
_HARBOR_EGRESS_PROBE_IMAGE = "alpine:3.23.4@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11"
_HARBOR_EGRESS_PROBE_SCRIPT = (
    "if [ ! -f /proc/config.gz ]; then exit 0; fi; "
    "zcat /proc/config.gz 2>/dev/null | "
    "grep -qE '^CONFIG_NFT_FIB_INET=[ym]'"
)


def _harbor_egress_kernel_support() -> bool | None:
    """Return Harbor's daemon egress probe when the harbor package is importable."""
    try:
        from harbor.environments.docker.docker import DockerEnvironment
    except ImportError:
        return None

    DockerEnvironment._egress_control_kernel_support.cache_clear()
    return DockerEnvironment._egress_control_kernel_support()


def _probe_egress_kernel_support() -> bool:
    """Run Harbor's docker egress kernel probe without importing harbor."""
    try:
        result = subprocess.run(
            [
                "docker",
                "container",
                "run",
                "--rm",
                _HARBOR_EGRESS_PROBE_IMAGE,
                "sh",
                "-c",
                _HARBOR_EGRESS_PROBE_SCRIPT,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _docker_desktop_version() -> str | None:
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        marker = "Docker Desktop"
        if marker not in line:
            continue
        tail = line.split(marker, 1)[1].strip()
        version = tail.split()[0] if tail else ""
        return version or None
    return None


def _docker_desktop_upgrade_hint(version: str | None) -> str | None:
    if version is None:
        return None
    parts = version.split(".")
    if len(parts) < 2:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except ValueError:
        return None
    if major < 4 or (major == 4 and minor < 86):
        return (
            f"Docker Desktop {version} detected; Harbor egress control requires "
            "Docker Desktop 4.86.0 or later on macOS."
        )
    return None


def check_egress_control_support() -> dict[str, Any]:
    """Probe whether Harbor's Docker egress sidecar can run on this daemon."""
    if shutil.which("docker") is None:
        return {"supported": False, "method": "none", "reason": "docker not found on PATH"}

    harbor_version: str | None = None
    try:
        import harbor

        harbor_version = harbor.__version__
    except ImportError:
        harbor_version = None

    harbor_api = _harbor_egress_kernel_support()
    if harbor_api is not None:
        supported = harbor_api
        method = "harbor"
    else:
        supported = _probe_egress_kernel_support()
        method = "docker-probe"

    desktop_version = _docker_desktop_version()
    payload: dict[str, Any] = {
        "supported": supported,
        "method": method,
        "harbor_version": harbor_version,
        "docker_desktop_version": desktop_version,
    }

    if supported:
        payload["reason"] = "Docker daemon passed Harbor egress kernel probe (CONFIG_NFT_FIB_INET)."
        return payload

    reason_parts = [
        "Harbor Docker egress control is unavailable in the Docker daemon kernel. "
        "Sandbox trials require CONFIG_NFT_FIB_INET=y|m. "
        "On macOS: upgrade Docker Desktop to 4.86.0 or later, or use OrbStack or Colima."
    ]
    upgrade_hint = _docker_desktop_upgrade_hint(desktop_version)
    if upgrade_hint:
        reason_parts.append(upgrade_hint)
    payload["reason"] = " ".join(reason_parts)
    return payload


def sandbox_task_toml(*, inference_hosts: list[str]) -> str:
    """Return task.toml network policy for sandboxed rho-agent trials."""
    lines = [
        'version = "1.0"',
        "",
        "[task]",
        'name = "rho-agent/sandbox-task"',
        "authors = []",
        'keywords = ["sandbox", "rho-agent"]',
        "",
        "[metadata]",
        'author_name = "eval-author-walkthrough"',
        'difficulty = "easy"',
        'category = "programming"',
        'tags = ["sandbox"]',
        "",
        "[verifier]",
        "timeout_sec = 120.0",
        "",
        "[agent]",
        "timeout_sec = 600.0",
        'network_mode = "allowlist"',
        f"allowed_hosts = {json.dumps(inference_hosts)}",
        "",
        "[environment]",
        "build_timeout_sec = 600.0",
        'network_mode = "no-network"',
        "cpus = 1",
        "memory_mb = 2048",
        "storage_mb = 10240",
        "gpus = 0",
    ]
    return "\n".join(lines) + "\n"


def cover_read_task_toml(*, inference_hosts: list[str]) -> str:
    """Return the cover-read draft task.toml with sandbox network policy."""
    return "\n".join(
        [
            'version = "1.0"',
            "",
            "[task]",
            'name = "rho-agent/cover-read"',
            'authors = [{ name = "eval-author-walkthrough" }]',
            'keywords = ["read", "write", "sandbox"]',
            "",
            "[metadata]",
            'author_name = "eval-author-walkthrough"',
            'difficulty = "easy"',
            'category = "programming"',
            'tags = ["read", "sandbox"]',
            "",
            "[verifier]",
            "timeout_sec = 120.0",
            "",
            "[agent]",
            "timeout_sec = 600.0",
            'network_mode = "allowlist"',
            f"allowed_hosts = {json.dumps(inference_hosts)}",
            "",
            "[environment]",
            "build_timeout_sec = 600.0",
            'network_mode = "no-network"',
            "cpus = 1",
            "memory_mb = 2048",
            "storage_mb = 10240",
            "gpus = 0",
            "",
        ]
    )


def task_dockerfile_with_seed(*, image_ref: str = IMAGE_REF) -> str:
    return "\n".join(
        [
            f"FROM {image_ref}",
            "",
            "WORKDIR /app",
            "COPY seed.txt /app/seed.txt",
            "",
        ]
    )


def task_0_task_toml(*, inference_hosts: list[str]) -> str:
    """Return task.toml for the bundled baseline task-0 overlay."""
    toml = sandbox_task_toml(inference_hosts=inference_hosts)
    return toml.replace('name = "rho-agent/sandbox-task"', 'name = "rho-agent/task-0"', 1).replace(
        'keywords = ["sandbox", "rho-agent"]',
        'keywords = ["write", "sandbox", "baseline"]',
        1,
    )


def legacy_task_0_task_toml() -> str:
    """Return a public-network task.toml for legacy runtime-install trials."""
    return (ASSETS / "task-0" / "task.toml").read_text(encoding="utf-8")


def write_baseline_overlay(
    workspace: Path,
    *,
    image_ref: str = IMAGE_REF,
    inference_hosts: list[str] | None = None,
    legacy: bool = False,
) -> Path:
    """Materialize bundled task-0 under .eval-author/sandbox/."""
    source_task = ASSETS / "task-0"
    if not source_task.is_dir():
        raise PrepareError(f"walkthrough missing bundled task-0 at {source_task}")

    overlay = workspace / ".eval-author" / "sandbox" / "task-0"
    if overlay.exists():
        shutil.rmtree(overlay)
    shutil.copytree(
        source_task,
        overlay,
        ignore=shutil.ignore_patterns("Dockerfile.legacy"),
    )

    if legacy:
        legacy_dockerfile = source_task / "environment" / "Dockerfile.legacy"
        shutil.copy2(legacy_dockerfile, overlay / "environment" / "Dockerfile")
        (overlay / "task.toml").write_text(legacy_task_0_task_toml(), encoding="utf-8")
    else:
        hosts = inference_hosts or inference_allowlist_hosts(os.environ.get("OPENAI_BASE_URL"))
        (overlay / "task.toml").write_text(
            task_0_task_toml(inference_hosts=hosts),
            encoding="utf-8",
        )
        (overlay / "environment" / "Dockerfile").write_text(
            "\n".join([f"FROM {image_ref}", "", "WORKDIR /app", ""]),
            encoding="utf-8",
        )

    (overlay / "tests" / "test.sh").chmod(0o755)
    (overlay / "solution" / "solve.sh").chmod(0o755)
    return overlay


def render_job_config(
    *,
    job_name: str,
    jobs_dir: Path,
    task_path: Path,
    fixture: Path,
    n_attempts: int,
    inference_hosts: list[str] | None = None,
) -> dict[str, Any]:
    """Build a Harbor job config dict for sandboxed rho-agent trials."""
    hosts = inference_hosts or inference_allowlist_hosts(os.environ.get("OPENAI_BASE_URL"))
    rel_jobs = jobs_dir.relative_to(fixture)
    rel_task = task_path.relative_to(fixture)
    return {
        "job_name": job_name,
        "jobs_dir": str(rel_jobs),
        "n_attempts": n_attempts,
        "timeout_multiplier": 1.0,
        "orchestrator": {"type": "local", "n_concurrent_trials": 1, "quiet": True},
        "environment": {"type": "docker", "force_build": False, "delete": True},
        "agents": [
            {
                "name": "rho-agent",
                "import_path": "rho_harbor_agent:RhoAgent",
                "extra_allowed_hosts": hosts,
            }
        ],
        "tasks": [{"path": str(rel_task)}],
    }


def write_job_config(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def prepare_workspace(
    workspace: Path,
    *,
    build_image: bool = True,
    force_build: bool = False,
    image_ref: str = IMAGE_REF,
    legacy: bool = False,
) -> dict[str, Any]:
    """Build image, baseline overlay, and baseline job config for one walkthrough workspace."""
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    checkout = clone_rho_agent(workspace)

    if build_image and not legacy:
        build_agent_image(image_ref=image_ref, force=force_build)

    inference_hosts = inference_allowlist_hosts(os.environ.get("OPENAI_BASE_URL"))
    egress = check_egress_control_support()
    if not legacy and not egress.get("supported"):
        reason = egress.get("reason", "Harbor egress control unavailable")
        raise PrepareError(
            f"Walkthrough demo requires Harbor network allowlists in Docker Desktop's Linux VM. {reason}"
        )

    overlay = write_baseline_overlay(
        workspace,
        image_ref=image_ref,
        inference_hosts=inference_hosts,
        legacy=legacy,
    )

    eval_author = workspace / ".eval-author"
    eval_author.mkdir(parents=True, exist_ok=True)
    baseline_job = render_job_config(
        job_name="rho-agent-baseline-task-0-sandbox",
        jobs_dir=eval_author / "baseline-jobs",
        task_path=overlay,
        fixture=workspace,
        n_attempts=1,
        inference_hosts=inference_hosts,
    )
    job_path = write_job_config(eval_author / "baseline-job.yaml", baseline_job)

    return {
        "image": image_ref,
        "inference_hosts": inference_hosts,
        "rho_agent_checkout": str(checkout.relative_to(workspace)),
        "baseline_overlay": str(overlay.relative_to(workspace)),
        "baseline_job": str(job_path.relative_to(workspace)),
        "egress_control": egress,
        "network_isolation": "legacy" if legacy else "allowlist",
    }


def prepare_fixture(
    fixture: Path,
    *,
    build_image: bool = True,
    force_build: bool = False,
    image_ref: str = IMAGE_REF,
) -> dict[str, Any]:
    """Backward-compatible alias for ``prepare_workspace``."""
    return prepare_workspace(
        fixture,
        build_image=build_image,
        force_build=force_build,
        image_ref=image_ref,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare sandboxed rho-agent Harbor walkthrough assets.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-image", help="Build the pre-baked rho-agent Harbor image.")
    build.add_argument("--force", action="store_true", help="Rebuild even when the tag already exists.")
    build.add_argument("--image", default=IMAGE_REF, help=f"Image ref to build (default: {IMAGE_REF}).")

    workspace_cmd = sub.add_parser(
        "prepare-workspace",
        help="Build image and write sandbox overlays for one walkthrough workspace.",
    )
    workspace_cmd.add_argument("workspace", type=Path, help="Walkthrough workspace directory.")
    workspace_cmd.add_argument("--skip-build", action="store_true", help="Assume the agent image already exists.")
    workspace_cmd.add_argument("--force-build", action="store_true", help="Force rebuild the agent image.")
    workspace_cmd.add_argument("--image", default=IMAGE_REF, help=f"Agent image ref (default: {IMAGE_REF}).")
    workspace_cmd.add_argument(
        "--legacy",
        action="store_true",
        help="Use ubuntu task-0 image and skip sandbox network policy.",
    )

    fixture = sub.add_parser(
        "prepare-fixture",
        help="Deprecated alias for prepare-workspace.",
    )
    fixture.add_argument("fixture", type=Path, help="Walkthrough workspace directory.")
    fixture.add_argument("--skip-build", action="store_true", help="Assume the agent image already exists.")
    fixture.add_argument("--force-build", action="store_true", help="Force rebuild the agent image.")
    fixture.add_argument("--image", default=IMAGE_REF, help=f"Agent image ref (default: {IMAGE_REF}).")

    _ = sub.add_parser("check-egress", help="Probe Docker egress-control support on this host.")

    hosts = sub.add_parser("inference-hosts", help="Print inference allowlist hostnames as JSON.")
    hosts.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", DEFAULT_INFERENCE_BASE_URL),
        help="OpenAI-compatible base URL to derive the allowlist from.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "build-image":
            image = build_agent_image(image_ref=args.image, force=args.force)
            print(json.dumps({"built": image}, indent=2))
            return 0

        if args.command in {"prepare-fixture", "prepare-workspace"}:
            target = args.fixture if args.command == "prepare-fixture" else args.workspace
            legacy = bool(getattr(args, "legacy", False))
            payload = prepare_workspace(
                target,
                build_image=not args.skip_build,
                force_build=args.force_build,
                image_ref=args.image,
                legacy=legacy,
            )
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "check-egress":
            print(json.dumps(check_egress_control_support(), indent=2))
            return 0

        if args.command == "inference-hosts":
            host = urlparse(args.base_url).hostname
            payload = {
                "base_url": args.base_url,
                "hosts": inference_allowlist_hosts(args.base_url),
                "python_path": RHO_AGENT_VENV_PYTHON,
                "image": f"{IMAGE_REPOSITORY}:{IMAGE_TAG}",
            }
            if host is None:
                payload["warning"] = "could not parse hostname; using defaults"
            print(json.dumps(payload, indent=2))
            return 0

        parser.error(f"unknown command: {args.command}")
    except PrepareError as exc:
        print(f"prepare failed: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
