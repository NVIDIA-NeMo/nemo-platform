# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The agent-bundle sidecar layout must come from configuration, not be hardcoded.

The installer path and identity env prefix are a contract with whichever builder
produced the bundle image. Getting either wrong makes the sidecar run a missing
binary or publish env names the bundle does not read, and that only shows up
inside a live sandbox — so pin the substitution here.
"""

from __future__ import annotations

import pytest
import yaml

# The imports this exercises happen inside the test body, so guard the module instead: a
# default sync leaves this plugin uninstalled and the repo-wide run still sweeps here.
pytest.importorskip("scaled_evals", reason="scaled-evals plugin not installed")

DIGEST = "sha256:" + "a" * 64
BUNDLE = {
    "agent_name": "demo-agent",
    "agent_version": "1.2.3",
    "image_ref": "registry.example.com/bundles/demo:1.2.3",
    "image_digest": f"registry.example.com/bundles/demo@{DIGEST}",
    "entrypoint": "bin/demo",
    "source_lock_digest": DIGEST,
    "fingerprint": DIGEST,
    "platform": "linux/amd64",
    "runtime_abi": "glibc2.36",
    "bundle_layout_version": "1",
    "builder_profile": "default",
}
CONFIG = yaml.safe_dump({"environment": {"kwargs": {}}, "agents": [{"name": "demo"}]})


def test_sidecar_uses_configured_installer_and_env_prefix(monkeypatch) -> None:
    from scaled_evals.api import settings as settings_module
    from scaled_evals.dispatch import sandbox_k8s

    # Defaults carry no internal deployment name.
    rendered = yaml.safe_load(sandbox_k8s._bind_agent_bundle(CONFIG, BUNDLE))
    sidecar = next(item for item in rendered["environment"]["kwargs"]["sidecars"] if item["name"] == "agent-bundle")
    assert "/opt/agent-bundle/copy-agent /installed-agent" in sidecar["args"][0]
    assert sidecar["env"]["AGENT_BUNDLE_NAME"] == "demo-agent"
    assert sidecar["env"]["AGENT_BUNDLE_SOURCE_LOCK_DIGEST"] == DIGEST
    assert not [key for key in sidecar["env"] if "ASTRA" in key]

    # A deployment whose bundles use a different layout can point at it.
    monkeypatch.setattr(settings_module.settings, "agent_bundle_installer_path", "/opt/other/install", False)
    monkeypatch.setattr(settings_module.settings, "agent_bundle_env_prefix", "OTHER_", False)
    rendered = yaml.safe_load(sandbox_k8s._bind_agent_bundle(CONFIG, BUNDLE))
    sidecar = next(item for item in rendered["environment"]["kwargs"]["sidecars"] if item["name"] == "agent-bundle")
    assert "/opt/other/install /installed-agent" in sidecar["args"][0]
    assert sidecar["env"]["OTHER_NAME"] == "demo-agent"
    assert "AGENT_BUNDLE_NAME" not in sidecar["env"]
