# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import io
import tarfile

import pytest
from httpx import Request, Response
from scaled_evals.api.build.task_image_identity import (
    normalize_upstream_image_ref,
    resolve_upstream_image,
)
from scaled_evals.dispatch.harbor_dataset_images import dataset_configs, effective_image_mode
from scaled_evals.harbor_dataset_import import (
    HarborDatasetImageImport,
    build_image_import_context,
)


def test_import_context_is_pinned_and_deterministic() -> None:
    imported = HarborDatasetImageImport.parse("docker.io/example/task@sha256:" + "a" * 64)

    first = build_image_import_context(imported)
    assert first == build_image_import_context(imported)
    with tarfile.open(fileobj=io.BytesIO(first), mode="r:gz") as archive:
        dockerfile = archive.extractfile("Dockerfile")
        assert dockerfile is not None
        assert dockerfile.read() == f"FROM {imported.source_image}\n".encode()


@pytest.mark.parametrize("image", ["docker.io/example/task:latest", "docker.io/example/task@sha256:bad"])
def test_import_rejects_unpinned_images(image: str) -> None:
    with pytest.raises(ValueError, match="pinned"):
        HarborDatasetImageImport.parse(image)


def test_import_context_carries_runnable_harbor_task(tmp_path) -> None:  # noqa: ANN001
    task = tmp_path / "task"
    task.mkdir()
    (task / "task.toml").write_text('[environment]\ndocker_image = "example/task:1"\n')
    (task / "instruction.md").write_text("do the thing\n")
    imported = HarborDatasetImageImport.parse("docker.io/example/task@sha256:" + "a" * 64)

    context = build_image_import_context(imported, task_dir=task, task_name="example-task")

    with tarfile.open(fileobj=io.BytesIO(context), mode="r:gz") as archive:
        assert archive.extractfile("tasks/example-task/task.toml") is not None
        instruction = archive.extractfile("tasks/example-task/instruction.md")
        assert instruction is not None
        assert instruction.read() == b"do the thing\n"


def test_upstream_image_resolution_expands_docker_shorthand() -> None:
    assert normalize_upstream_image_ref("alexgshaw/task:20251031") == ("docker.io/alexgshaw/task:20251031")
    response = Response(
        200,
        headers={"Docker-Content-Digest": "sha256:" + "a" * 64},
        request=Request("GET", "https://docker.io/v2/alexgshaw/task/manifests/20251031"),
    )
    requested: list[str] = []

    def get(_self, url, **_kwargs):  # type: ignore[no-untyped-def]
        requested.append(url)
        return response

    client = type("Client", (), {"get": get})()

    resolved = resolve_upstream_image("alexgshaw/task:20251031", client=client)

    assert resolved.immutable_ref == "docker.io/alexgshaw/task@sha256:" + "a" * 64
    assert requested == ["https://registry-1.docker.io/v2/alexgshaw/task/manifests/20251031"]


def test_dataset_image_mode_is_always_managed() -> None:
    assert effective_image_mode({"dataset_only": True}) == "managed"
    assert effective_image_mode({"dataset_only": True, "dataset_image_mode": "managed"}) == ("managed")
    with pytest.raises(ValueError, match="deployment-managed"):
        effective_image_mode({"dataset_only": True, "dataset_image_mode": "direct"})


def test_dataset_configs_reads_wrapped_harbor_yaml() -> None:
    profile = {
        "dataset_only": True,
        "harbor_config": "datasets:\n  - name: org/dataset\n    n_tasks: 10\n",
    }

    assert dataset_configs(profile) == [{"name": "org/dataset", "n_tasks": 10}]
