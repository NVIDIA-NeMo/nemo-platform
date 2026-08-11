# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from harbor_nemo.client import NemoClient
from harbor_nemo.config import NemoConfig

BASE_URL = "http://nemo.test"
WORKSPACE = "default"
FILESET = "harbor-packages"

TASKS_URL = f"{BASE_URL}/apis/evaluator/v2/workspaces/{WORKSPACE}/tasks"
TASKSETS_URL = f"{BASE_URL}/apis/evaluator/v2/workspaces/{WORKSPACE}/tasksets"
FILES_URL = f"{BASE_URL}/apis/files/v2/workspaces/{WORKSPACE}/filesets"


@pytest.fixture
def config() -> NemoConfig:
    return NemoConfig(
        base_url=BASE_URL,
        workspace=WORKSPACE,
        fileset=FILESET,
        token=None,
        timeout_sec=5.0,
    )


@pytest.fixture
async def client(config: NemoConfig):
    nemo_client = NemoClient(config)
    yield nemo_client
    await nemo_client.aclose()


def harbor_task(
    *,
    archive_digest: str = "a" * 64,
    revision: int = 1,
    tags: dict[str, int] | None = None,
    kind: str = "harbor",
) -> dict:
    return {
        "id": "task-1",
        "name": "nvidia.my-task",
        "workspace": WORKSPACE,
        "revision": revision,
        "tags": tags if tags is not None else {"latest": revision},
        "spec": {
            "kind": kind,
            "archive_ref": f"{WORKSPACE}/{FILESET}#packages/nvidia/my-task/{archive_digest}/dist.tar.gz",
            "archive_digest": archive_digest,
            "instruction": "",
            "config": {},
        },
    }
