"""Smoke tests that verify the platform is reachable and core APIs respond.

These are intentionally minimal — they validate the e2e harness works and
that services are up. Add more substantive tests in separate files.
"""

import uuid

from nemo_platform import NeMoPlatform


def test_health_ready(sdk: NeMoPlatform):
    """GET /status returns 200 with healthy status when all services are up."""
    resp = sdk._client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_health_live(sdk: NeMoPlatform):
    """GET /status returns 200 (platform is reachable)."""
    resp = sdk._client.get("/status")
    assert resp.status_code == 200


def test_create_and_delete_workspace(sdk: NeMoPlatform):
    """Workspace create and delete round-trips through the platform."""
    name = f"e2e-smoke-{uuid.uuid4().hex[:8]}"
    ws = sdk.workspaces.create(name=name)
    try:
        assert ws.name == name
    finally:
        sdk.workspaces.delete(name)


def test_list_workspaces(sdk: NeMoPlatform, workspace: str):
    """Listing workspaces returns at least the test workspace."""
    page = sdk.workspaces.list()
    names = [w.name for w in page.data]
    assert workspace in names
