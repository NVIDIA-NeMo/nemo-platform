# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guard against nvidia-nat package-family version drift.

The agentic-base image installs the NAT family unpinned (see
Dockerfile.agentic-base / tests/agentic-use/requirements-nat.txt). The CLI/meta
package historically lagged the plugin packages (e.g. ``nvidia-nat==1.4.3`` vs
``nvidia-nat-core``/``-eval``/``-langchain==1.7.0``), which silently produced
``ImportError: cannot import name 'register_dataset_loader'`` at plugin
discovery and crashed ``nat start fastapi`` with exit code 1 — only surfacing in
slow, GPU-bound end-to-end runs.

This is the cheapest layer that can catch the mismatch: enumerate the installed
``nvidia-nat*`` distributions and assert they all report the same version.
"""

from __future__ import annotations

from importlib import metadata

import pytest


def _nat_distributions() -> dict[str, str]:
    """Return {normalized_name: version} for every installed nvidia-nat* dist."""
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        normalized = name.lower().replace("_", "-")
        if normalized == "nvidia-nat" or normalized.startswith("nvidia-nat-"):
            found[normalized] = dist.version
    return found


def test_nvidia_nat_family_versions_are_aligned() -> None:
    """All installed nvidia-nat* packages must share the same version.

    Skips when NAT is not installed (NAT lives in an isolated venv and is only
    present in the agentic-base image / the .venv-nat dev environment).
    """
    dists = _nat_distributions()
    if not dists:
        pytest.skip("No nvidia-nat* packages installed; NAT runs in an isolated venv.")

    versions = set(dists.values())
    if len(versions) > 1:
        detail = "\n".join(f"  {name}=={version}" for name, version in sorted(dists.items()))
        pytest.fail(
            "nvidia-nat package family version mismatch — all nvidia-nat* packages "
            "must be pinned to the same version (a lagging meta/CLI package crashes "
            "`nat start fastapi` at plugin discovery):\n"
            f"{detail}\n"
            "Pin every nvidia-nat* package to one version in Dockerfile.agentic-base "
            "and tests/agentic-use/requirements-nat.txt."
        )
