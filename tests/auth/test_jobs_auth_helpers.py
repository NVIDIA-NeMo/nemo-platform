# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.auth.integration.jobs_auth_helpers import job_exists_in_pages, managed_admin_workspace


class _StubWorkspaces:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.deleted: list[str] = []

    def create(self, *, name: str) -> None:
        self.created.append(name)

    def delete(self, name: str) -> None:
        self.deleted.append(name)


class _StubSDK:
    def __init__(self) -> None:
        self.workspaces = _StubWorkspaces()


class _StubJob:
    def __init__(self, name: str) -> None:
        self.name = name


class _StubPage:
    def __init__(self, pages: list["_StubPage"], job_names: list[str]) -> None:
        self._pages = pages
        self.data = [_StubJob(name) for name in job_names]
        self.pagination = object()

    def iter_pages(self):
        yield from self._pages


def test_managed_admin_workspace_deletes_workspace_after_success() -> None:
    sdk = _StubSDK()

    with managed_admin_workspace(sdk, "workspace-a") as workspace_name:
        assert workspace_name == "workspace-a"

    assert sdk.workspaces.created == ["workspace-a"]
    assert sdk.workspaces.deleted == ["workspace-a"]


def test_managed_admin_workspace_deletes_workspace_after_failure() -> None:
    sdk = _StubSDK()

    with pytest.raises(RuntimeError, match="boom"):
        with managed_admin_workspace(sdk, "workspace-b"):
            raise RuntimeError("boom")

    assert sdk.workspaces.created == ["workspace-b"]
    assert sdk.workspaces.deleted == ["workspace-b"]


def test_job_exists_in_pages_checks_later_pages() -> None:
    page_two = _StubPage([], ["target-job"])
    page_one = _StubPage([], ["other-job"])
    page_one._pages = [page_one, page_two]

    assert job_exists_in_pages(page_one, "target-job") is True
