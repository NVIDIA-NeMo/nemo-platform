# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Domain pytest checks for the workspace-basic-cli-easy ACES eval."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from nemo_platform import NeMoPlatform

WORKSPACE_NAME = "harbor-test-workspace"


def _entry() -> dict[str, Any]:
    entry_path = Path(os.environ.get("HARBOR_ENTRY_JSON", "/tests/entry.json"))
    return json.loads(entry_path.read_text(encoding="utf-8"))


def _workspace_names() -> list[str]:
    nmp_base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
    client = NeMoPlatform(base_url=nmp_base_url)
    response = client.workspaces.list()
    return [workspace.name for workspace in response.data]


def test_expected_workspace_state() -> None:
    """Positive cases create the workspace; negative cases leave it absent."""
    entry = _entry()
    workspace_names = _workspace_names()

    if entry.get("expected_skill") == "workspace-basic-cli-easy":
        assert WORKSPACE_NAME in workspace_names, (
            f"Workspace {WORKSPACE_NAME!r} was not created. Found workspaces: {workspace_names}"
        )
    else:
        assert WORKSPACE_NAME not in workspace_names, (
            f"Negative case should not create {WORKSPACE_NAME!r}. Found workspaces: {workspace_names}"
        )
