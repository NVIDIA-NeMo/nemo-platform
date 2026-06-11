# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for OPA bundle generation."""

import gzip
import io
import json
import tarfile

import pytest


@pytest.mark.asyncio
async def test_authorization_data_merges_plugin_authz_contributions(monkeypatch):
    """Plugin authz contributions are included before validation and bundle build."""
    from nmp.core.auth.app.bundle import _build_authorization_data_internal

    plugin_path = "/apis/example-plugin/v2/workspaces/{workspace}/jobs"
    contribution = {
        "permissions": {"example-plugin.jobs.read": "Read example plugin jobs"},
        "endpoints": {
            plugin_path: {
                "get": {
                    "permissions": ["example-plugin.jobs.read"],
                    "scopes": ["example-plugin:read", "platform:read"],
                }
            }
        },
    }

    monkeypatch.setattr(
        "nemo_platform_plugin.authz_discovery.discover_authz_contribution_dicts",
        lambda: [contribution],
    )

    data = await _build_authorization_data_internal(entities_client=None)

    assert data["authz"]["endpoints"][plugin_path]["get"]["permissions"] == ["example-plugin.jobs.read"]
    assert "example-plugin.jobs.read" in data["authz"]["roles"]["Viewer"]["permissions"]


@pytest.mark.asyncio
async def test_bundle_generation():
    """Test that bundle can be generated without a database."""
    from nmp.core.auth.app.bundle import clear_bundle_cache, get_opa_bundle_with_etag

    # Clear any cached bundle
    clear_bundle_cache()

    # Generate bundle without database
    bundle_bytes, etag = await get_opa_bundle_with_etag(entities_client=None)

    # Verify bundle is valid
    assert bundle_bytes is not None
    assert len(bundle_bytes) > 0
    assert etag is not None
    assert len(etag) == 32  # MD5 hash is 32 hex chars

    # Verify bundle is valid gzip
    bundle_io = io.BytesIO(bundle_bytes)
    with gzip.GzipFile(fileobj=bundle_io, mode="rb") as gz:
        tar_bytes = gz.read()

    # Verify bundle is valid tarfile
    tar_io = io.BytesIO(tar_bytes)
    with tarfile.open(fileobj=tar_io, mode="r") as tar:
        members = tar.getnames()

        # Should contain data.json and manifest
        assert "data.json" in members
        assert ".manifest" in members

        # Should contain at least one .rego policy file
        rego_files = [m for m in members if m.endswith(".rego")]
        assert len(rego_files) > 0

        # Verify data.json structure
        data_file = tar.extractfile("data.json")
        assert data_file is not None
        data = json.load(data_file)

        # Should have authz key
        assert "authz" in data
        assert "roles" in data["authz"]
        assert "workspaces" in data["authz"]


@pytest.mark.asyncio
async def test_bundle_caching():
    """Test that bundle is cached correctly."""
    from nmp.core.auth.app.bundle import clear_bundle_cache, get_opa_bundle_with_etag

    # Clear cache
    clear_bundle_cache()

    # First call should generate bundle
    bundle1, etag1 = await get_opa_bundle_with_etag(entities_client=None)

    # Second call should return cached bundle
    bundle2, etag2 = await get_opa_bundle_with_etag(entities_client=None)

    # Should be the same
    assert bundle1 == bundle2
    assert etag1 == etag2


@pytest.mark.asyncio
async def test_bundle_etag_stability():
    """Test that bundle E-Tag is stable for same data."""
    from nmp.core.auth.app.bundle import clear_bundle_cache, get_opa_bundle_with_etag

    # Clear cache
    clear_bundle_cache()

    # Generate bundle
    _, etag1 = await get_opa_bundle_with_etag(entities_client=None)

    # Clear cache and regenerate
    clear_bundle_cache()
    _, etag2 = await get_opa_bundle_with_etag(entities_client=None)

    # E-Tag should be the same for same data
    assert etag1 == etag2
