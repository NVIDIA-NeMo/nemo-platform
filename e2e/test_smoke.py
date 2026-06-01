"""Smoke tests that verify the platform is reachable and core APIs respond.

These are intentionally minimal — they validate the e2e harness works and
that services are up. Add more substantive tests in separate files.
"""

from nemo_platform import NeMoPlatform


def test_health_ready(sdk: NeMoPlatform):
    """GET /health/ready returns 200 when all services are up."""
    resp = sdk._client.get("/health/ready")
    assert resp.status_code == 200


def test_health_live(sdk: NeMoPlatform):
    """GET /health/live returns 200 (liveness probe)."""
    resp = sdk._client.get("/health/live")
    assert resp.status_code == 200


def test_create_and_delete_workspace(workspace: str, sdk: NeMoPlatform):
    """Workspace CRUD round-trips through the platform.

    Uses the ``workspace`` fixture which creates a unique workspace
    and deletes it on teardown.
    """
    page = sdk.workspaces.list()
    names = [w.name for w in page.data]
    assert workspace in names


def test_list_workspaces(sdk: NeMoPlatform, workspace: str):
    """Listing workspaces returns at least the test workspace."""
    page = sdk.workspaces.list()
    names = [w.name for w in page.data]
    assert workspace in names
