# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from nemo_platform import NeMoPlatform


@contextmanager
def managed_admin_workspace(admin_sdk: NeMoPlatform, workspace_name: str) -> Iterator[str]:
    admin_sdk.workspaces.create(name=workspace_name)
    try:
        yield workspace_name
    finally:
        admin_sdk.workspaces.delete(workspace_name)


def job_exists_in_pages(items: Iterator[Any], job_name: str) -> bool:
    return any(item.name == job_name for item in items)
