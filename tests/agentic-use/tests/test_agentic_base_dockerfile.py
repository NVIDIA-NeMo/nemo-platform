# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO_ROOT / "Dockerfile.agentic-base"


def _nat_install_command() -> str:
    dockerfile = DOCKERFILE.read_text()
    start = dockerfile.index("RUN uv pip install --python /app/.venv/bin/python")
    end = dockerfile.index("uv pip install --python /app/.venv/bin/python -e /app/plugins/nemo-agents", start)
    return dockerfile[start:end]


def test_agentic_base_nat_install_allows_prereleases() -> None:
    command = _nat_install_command()

    assert "--prerelease=allow" in command
    assert command.index("--prerelease=allow") < command.index('"nvidia-nat[most]==1.7.0"')


def test_agentic_base_nat_install_pins_package_family() -> None:
    command = _nat_install_command()

    for requirement in (
        '"nvidia-nat[most]==1.7.0"',
        "nvidia-nat-atif==1.7.0",
        "nvidia-nat-eval==1.7.0",
        "nvidia-nat-mcp==1.7.0",
    ):
        assert requirement in command
