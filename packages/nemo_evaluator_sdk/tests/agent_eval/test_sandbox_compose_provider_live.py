# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live Docker Compose provider tests for image-first and source-build modes."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.base import SandboxSpec
from nemo_evaluator_sdk.agent_eval.runtimes.sandbox.providers.compose import (
    ComposeServiceTopology,
    DockerComposeSandboxProvider,
)


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        compose = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=15,
        )
        daemon = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
        return compose.returncode == 0 and daemon.returncode == 0
    except subprocess.TimeoutExpired:
        return False


pytestmark = pytest.mark.skipif(not _docker_ready(), reason="docker compose daemon not available")


def _run(*argv: str, cwd: Path | None = None) -> None:
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr


def _build_fixture(context: Path, image: str, value: str) -> None:
    context.mkdir(parents=True, exist_ok=True)
    (context / "Dockerfile").write_text(
        "FROM busybox:latest\nCOPY value.txt /value.txt\nRUN adduser -D -u 1001 app\nWORKDIR /home/app\nUSER app\n",
        encoding="utf-8",
    )
    (context / "value.txt").write_text(value, encoding="utf-8")
    _run("docker", "build", "--tag", image, str(context))


def _topology(*services: str) -> ComposeServiceTopology:
    return ComposeServiceTopology(
        target_service="agent",
        long_running_services=frozenset(services),
    )


async def test_no_build_runs_prebuilt_image_without_source_context(tmp_path: Path) -> None:
    image = f"nemo-eval-compose-live:{uuid.uuid4().hex}"
    context = tmp_path / "build-context"
    _build_fixture(context, image, "prebuilt")
    shutil.rmtree(context)
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "\n".join(
            [
                "services:",
                "  agent:",
                f"    image: {image}",
                "    build: ./missing-context",
                '    command: ["sh", "-c", "sleep 300"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    provider = DockerComposeSandboxProvider(
        compose_files=(compose_file,),
        service_topology=_topology("agent"),
        pull_policy="never",
        startup_timeout_seconds=60,
    )
    try:
        handle = await provider.create(SandboxSpec())
        result = await provider.exec(handle, "cat /value.txt")
        assert result.ok
        assert result.stdout is not None
        assert result.stdout.strip() == "prebuilt"
        seed = tmp_path / "seed.txt"
        seed.write_text("seed", encoding="utf-8")
        await provider.upload_file(handle, seed, "/home/app/missing/parent/seed.txt")
        modified = await provider.exec(
            handle,
            "echo -n '-modified' >> /home/app/missing/parent/seed.txt && cat /home/app/missing/parent/seed.txt",
        )
        assert modified.ok and modified.stdout == "seed-modified"
        sibling = await provider.exec(
            handle,
            "echo -n sibling > /home/app/missing/parent/sibling.txt && cat /home/app/missing/parent/sibling.txt",
        )
        assert sibling.ok and sibling.stdout == "sibling"

        assert (await provider.exec(handle, "ln -s /tmp /home/app/replaced-parent")).ok
        with pytest.raises(RuntimeError, match="Compose upload target preparation failed"):
            await provider.upload_file(handle, seed, "/home/app/replaced-parent/blocked.txt")
        assert (await provider.exec(handle, "test ! -e /tmp/blocked.txt")).ok

        await provider.upload_file(handle, seed, "relative/missing/seed.txt")
        relative_modified = await provider.exec(
            handle,
            "echo -n '-relative' >> /relative/missing/seed.txt && cat /relative/missing/seed.txt",
        )
        assert relative_modified.ok and relative_modified.stdout == "seed-relative"

        source_dir = tmp_path / "source-dir"
        source_dir.mkdir()
        (source_dir / "note.txt").write_text("uploaded", encoding="utf-8")
        await provider.upload_dir(handle, source_dir, "/home/app/absent/workspace")
        absent_upload = await provider.exec(
            handle,
            "echo -n '-modified' >> /home/app/absent/workspace/note.txt && cat /home/app/absent/workspace/note.txt",
        )
        assert absent_upload.ok and absent_upload.stdout == "uploaded-modified"
        assert (await provider.exec(handle, "test ! -e /home/app/absent/workspace/source-dir")).ok

        assert (await provider.exec(handle, "mkdir -p /home/app/existing/workspace")).ok
        await provider.upload_dir(handle, source_dir, "/home/app/existing/workspace")
        existing_upload = await provider.exec(handle, "cat /home/app/existing/workspace/note.txt")
        assert existing_upload.ok and existing_upload.stdout == "uploaded"
        assert (await provider.exec(handle, "test ! -e /home/app/existing/workspace/source-dir")).ok

        assert (
            await provider.exec(
                handle,
                "mkdir -p /home/app/download-source && echo -n downloaded > /home/app/download-source/result.txt",
            )
        ).ok
        absent_download = tmp_path / "absent-download"
        await provider.download_dir(handle, "/home/app/download-source", absent_download)
        assert (absent_download / "result.txt").read_text(encoding="utf-8") == "downloaded"
        assert not (absent_download / "download-source").exists()

        existing_download = tmp_path / "existing-download"
        existing_download.mkdir()
        (existing_download / "sentinel.txt").write_text("keep", encoding="utf-8")
        await provider.download_dir(handle, "/home/app/download-source", existing_download)
        assert (existing_download / "result.txt").read_text(encoding="utf-8") == "downloaded"
        assert (existing_download / "sentinel.txt").read_text(encoding="utf-8") == "keep"
        assert not (existing_download / "download-source").exists()
        await provider.close(handle)
    finally:
        await provider.aclose()
        subprocess.run(["docker", "image", "rm", "--force", image], capture_output=True, timeout=30)


async def test_build_mode_rebuilds_changed_provisioned_workspace(tmp_path: Path) -> None:
    image = f"nemo-eval-compose-live:{uuid.uuid4().hex}"
    context = tmp_path / "source"
    context.mkdir()
    (context / "Dockerfile").write_text(
        "FROM busybox:latest\nCOPY value.txt /value.txt\n",
        encoding="utf-8",
    )
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "\n".join(
            [
                "services:",
                "  agent:",
                f"    image: {image}",
                "    build: ./source",
                '    command: ["sh", "-c", "sleep 300"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    async def evaluate(value: str) -> str:
        (context / "value.txt").write_text(value, encoding="utf-8")
        provider = DockerComposeSandboxProvider(
            compose_files=(compose_file,),
            service_topology=_topology("agent"),
            build=True,
            pull_policy="never",
            startup_timeout_seconds=60,
        )
        try:
            handle = await provider.create(SandboxSpec())
            result = await provider.exec(handle, "cat /value.txt")
            await provider.close(handle)
            assert result.ok
            assert result.stdout is not None
            return result.stdout.strip()
        finally:
            await provider.aclose()

    try:
        assert await evaluate("candidate-one") == "candidate-one"
        assert await evaluate("candidate-two") == "candidate-two"
    finally:
        subprocess.run(["docker", "image", "rm", "--force", image], capture_output=True, timeout=30)


async def test_ordered_override_and_profile_activate_expected_topology(tmp_path: Path) -> None:
    base = tmp_path / "compose.yaml"
    override = tmp_path / "compose.override.yaml"
    base.write_text(
        "\n".join(
            [
                "services:",
                "  agent:",
                "    image: busybox:latest",
                '    command: ["sh", "-c", "sleep 300"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    override.write_text(
        "\n".join(
            [
                "services:",
                "  worker:",
                "    image: busybox:latest",
                "    profiles: [extra]",
                '    command: ["sh", "-c", "sleep 300"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    provider = DockerComposeSandboxProvider(
        compose_files=(base, override),
        service_topology=_topology("agent", "worker"),
        profiles=("extra",),
        pull_policy="missing",
        startup_timeout_seconds=60,
    )
    try:
        handle = await provider.create(SandboxSpec())
        assert (await provider.status(handle)).value == "running"
        await provider.close(handle)
    finally:
        await provider.aclose()
