# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for OPA bundle generation."""

import gzip
import io
import json
import tarfile

import pytest


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


@pytest.mark.asyncio
async def test_build_authorization_data_includes_core_domain_metadata(monkeypatch):
    """Core API namespaces are exposed as auth domains."""
    from nmp.core.auth.app.bundle import build_authorization_data

    monkeypatch.setattr("nmp.core.auth.app.bundle._discover_domain_manifests", lambda: {})

    data = await build_authorization_data(None)

    assert data["authz"]["domains"]["models"] == {
        "name": "models",
        "version": "core",
        "kind": "core",
    }


@pytest.mark.asyncio
async def test_build_authorization_data_merges_extension_manifest_domain_metadata(monkeypatch):
    """Discovered extension manifests are merged into auth domains."""
    from nemo_platform_plugin.interface import PluginManifest
    from nmp.core.auth.app.bundle import build_authorization_data

    monkeypatch.setattr(
        "nmp.core.auth.app.bundle._discover_domain_manifests",
        lambda: {
            "agents": PluginManifest(
                name="agents",
                version="1.2.3",
                description="Agents API",
            )
        },
    )

    data = await build_authorization_data(None)

    assert data["authz"]["domains"]["agents"] == {
        "name": "agents",
        "version": "1.2.3",
        "kind": "extension",
    }


@pytest.mark.asyncio
async def test_build_authorization_data_rejects_domain_manifest_collisions(monkeypatch):
    """Extension manifests must not override core-inferred API domains."""
    from nemo_platform_plugin.interface import PluginManifest
    from nmp.core.auth.app.bundle import build_authorization_data

    monkeypatch.setattr(
        "nmp.core.auth.app.bundle._discover_domain_manifests",
        lambda: {
            "models": PluginManifest(
                name="models",
                version="9.9.9",
                description="Conflicting Models API",
            )
        },
    )

    with pytest.raises(ValueError, match="Domain name conflict"):
        await build_authorization_data(None)


@pytest.mark.asyncio
async def test_build_authorization_data_ignores_non_service_plugin_name_overlap(monkeypatch):
    """Non-service plugin surfaces must not participate in auth domain discovery."""
    from nmp.core.auth.app.bundle import build_authorization_data

    monkeypatch.setattr("nmp.core.auth.app.bundle._discover_domain_manifests", lambda: {})

    data = await build_authorization_data(None)

    assert data["authz"]["domains"]["guardrails"] == {
        "name": "guardrails",
        "version": "core",
        "kind": "core",
    }
