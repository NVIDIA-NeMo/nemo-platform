# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for the authz OIDC E2E harness.

Spawns dedicated ``nemo services run`` instances (fresh tmp data dir, free
port, this checkout's code) configured for **native OIDC only**:
``auth.enabled=true``, ``oidc.enabled=true`` pointing at the in-harness
issuer, and — critically — ``allow_unsigned_jwt=false``, so every identity in
the matrix is established by a real RS256-signed JWT. ``X-NMP-Principal-*``
headers are never sent; provisioning itself authenticates with a signed JWT
whose ``sub`` is ``service:e2e-harness``.

Two platform phases (both lazy, session-scoped):

- ``platform`` — default authz knobs (``on_invalid_plugin=deny_route``,
  PlatformAdmin not exempt from service-only routes).
- ``platform_knobs`` — ``on_invalid_plugin=quarantine`` +
  ``platform_admin_exempt_from_service_only=true``.

Run: ``pytest e2e/authz_oidc -v --run-e2e`` (see README.md).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import ADMIN_EMAIL, WS_A, WS_B, Platform  # noqa: E402
from idp import DEFAULT_AUDIENCE, MiniOIDCIssuer  # noqa: E402
from report import ReportCollector  # noqa: E402

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_PLATFORM_CONFIG = _REPO_ROOT / "packages/nmp_platform/config/local.yaml"
_FIXTURE_PLUGINS = ["harness-fixture", "harness-unruled", "harness-broken"]

_HEALTH_TIMEOUT = 180
_PROVISION_TIMEOUT = 120
_POLL = 1.0


# --------------------------------------------------------------------------- #
# Issuer                                                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def issuer() -> Iterator[MiniOIDCIssuer]:
    idp = MiniOIDCIssuer()
    url = idp.start()
    logger.info("Mini OIDC issuer serving at %s", url)
    yield idp
    idp.stop()


# --------------------------------------------------------------------------- #
# Platform process                                                             #
# --------------------------------------------------------------------------- #


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ensure_fixture_plugins_installed() -> None:
    """Editable-install the three fixture plugins into the active venv (idempotent)."""
    from importlib.metadata import entry_points

    installed = {ep.name for ep in entry_points(group="nemo.services")}
    missing = [p for p in _FIXTURE_PLUGINS if p not in installed]
    if not missing:
        return
    pip_specs = [str(_HERE / "fixtures" / p) for p in missing]
    subprocess.run(
        ["uv", "pip", "install", "--python", sys.executable, *[f"-e{spec}" for spec in pip_specs]],
        check=True,
        capture_output=True,
        cwd=_REPO_ROOT,
    )
    logger.info("Installed fixture plugins: %s", ", ".join(missing))


def _platform_env(issuer_url: str, data_dir: Path, extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NMP_", "DATABASE_"))}
    env.update(
        {
            "NMP_CONFIG_FILE_PATH": str(_PLATFORM_CONFIG),
            "NMP_CONFIG_WARNINGS_DISABLED": "1",
            "NMP_DATA_DIR": str(data_dir),
            "NMP_SEED_ON_STARTUP": "true",
            "NMP_AUTH_ENABLED": "true",
            "NMP_AUTH_ALLOW_UNSIGNED_JWT": "false",  # defaults are true; signed JWTs only
            "NMP_AUTH_OIDC_ENABLED": "true",
            "NMP_AUTH_OIDC_ISSUER": issuer_url,
            "NMP_AUTH_OIDC_AUDIENCE": DEFAULT_AUDIENCE,
            "NMP_AUTH_ADMIN_EMAIL": ADMIN_EMAIL,
            # bundle_cache_seconds must stay NONZERO: at 0 every PDP eval
            # rebuilds policy data, and degraded fixture plugins are never
            # cached (F1-10) — each eval then re-runs full plugin derivation
            # and entity paging, blowing the 5s PDP timeout platform-wide.
            # Fast background refresh + settle-probes handle propagation.
            "NMP_AUTH_BUNDLE_CACHE_SECONDS": "5",
            "NMP_AUTH_POLICY_DATA_REFRESH_INTERVAL": "2",
            # FINDING (harness-discovered): branch rego exceeds the default
            # embedded-PDP fuel budget (100M; config docstring says typical
            # evals are 20-25M) once seeded principal data is loaded — every
            # request 502s. Raised here to unblock; flagged for the branch.
            "NMP_AUTH_EMBEDDED_PDP_CPU_LIMIT": "2000",
        }
    )
    env.update(extra)
    return env


def _spawn_platform(
    issuer: MiniOIDCIssuer,
    tmp_path_factory: pytest.TempPathFactory,
    label: str,
    extra_env: dict[str, str],
) -> Iterator[Platform]:
    _ensure_fixture_plugins_installed()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    work = tmp_path_factory.mktemp(f"authz-e2e-{label}")
    data_dir = work / "data"
    data_dir.mkdir()
    log_path = work / "services.log"

    nemo_bin = Path(sys.executable).parent / "nemo"
    args = [
        str(nemo_bin),
        "services",
        "run",
        "--service-group",
        "all",
        "--controller-group",
        "all",
        "--port",
        str(port),
    ]
    env = _platform_env(issuer.issuer_url, data_dir, extra_env)

    logger.info("Spawning platform [%s] on %s (log: %s)", label, base_url, log_path)
    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(args, stdout=log_file, stderr=subprocess.STDOUT, env=env)
        try:
            platform = Platform(base_url=base_url, issuer=issuer, log_path=log_path)
            _wait_healthy(platform)
            yield platform
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _wait_healthy(platform: Platform) -> None:
    deadline = time.monotonic() + _HEALTH_TIMEOUT
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{platform.base_url}/health/ready", timeout=2.0).status_code == 200:
                break
        except httpx.RequestError:
            pass
        time.sleep(_POLL)
    else:
        pytest.fail(f"Platform on {platform.base_url} not healthy within {_HEALTH_TIMEOUT}s; log: {platform.log_path}")

    # Seeding runs as a startup task and may lag /health/ready: wait until the
    # admin's PlatformAdmin binding is live via the OIDC path itself.
    admin_token = platform.token("admin")
    deadline = time.monotonic() + _PROVISION_TIMEOUT
    while time.monotonic() < deadline:
        resp = platform.request("GET", "/apis/entities/v2/workspaces", token=admin_token)
        if resp.status_code == 200:
            return
        time.sleep(_POLL)
    pytest.fail(f"Admin OIDC token not authorized within {_PROVISION_TIMEOUT}s; log: {platform.log_path}")


# --------------------------------------------------------------------------- #
# Provisioning (signed service JWT only — no principal headers anywhere)       #
# --------------------------------------------------------------------------- #


def _provision(platform: Platform) -> None:
    """Create workspaces + explicit role bindings; revoke the seeded wildcard.

    Everything authenticates as ``service:e2e-harness`` via a signed JWT: the
    IAM role-binding endpoints are service-principal-only at the handler, and
    a Bearer token whose ``sub`` starts with ``service:`` satisfies that
    end-to-end (middleware builds Principal.id straight from the sub claim).
    """
    token = platform.token("provisioner")

    def call(method: str, path: str, body: dict | None = None) -> httpx.Response:
        resp = platform.request(method, path, token=token, body=body)
        if resp.status_code >= 500:
            raise AssertionError(f"provisioning {method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp

    # 1. Revoke the seeded wildcard '*' -> Viewer@system binding. With it in
    #    place every authenticated user holds all .read/.list permissions in
    #    the system workspace, which would make the F1-5 deny rows untestable.
    #    Revocation must go through the generic entities API: both dedicated
    #    revocation endpoints are broken for this binding (IAM DELETE looks it
    #    up in the 'default' workspace; members DELETE filters on a
    #    data.workspace key that binding entities don't carry) — see report.
    entity_path = "/apis/entities/v2/workspaces/system/entities/role_binding/wildcard-system-viewer"
    entity = call("GET", entity_path)
    assert entity.status_code == 200, f"seeded wildcard binding not found -> {entity.status_code}: {entity.text[:300]}"
    payload = entity.json()
    payload["data"]["revoked_at"] = "2026-01-01T00:00:00Z"
    resp = call("PUT", entity_path, {"name": payload["name"], "data": payload["data"]})
    assert resp.status_code == 200, f"wildcard revoke -> {resp.status_code}: {resp.text[:300]}"
    logger.info("Revoked seeded wildcard-system-viewer binding via entities API")

    # 2. Workspaces (creator auto-Admin binding is keyed to the service sub; harmless).
    for ws in (WS_A, WS_B):
        resp = call("POST", "/apis/entities/v2/workspaces", {"name": ws})
        assert resp.status_code == 201, f"workspace {ws} -> {resp.status_code}: {resp.text[:300]}"

    # 3. Explicit bindings (wait_role_propagation defaults to true -> synchronous).
    for principal, workspace, role in (
        ("alice@harness.test", WS_A, "Editor"),
        ("victor@harness.test", WS_A, "Viewer"),
        ("sam@harness.test", "system", "Viewer"),
    ):
        resp = call(
            "POST", "/apis/auth/v2/iam/role-bindings", {"principal": principal, "workspace": workspace, "role": role}
        )
        assert resp.status_code in (200, 201), (
            f"binding {principal}/{role}@{workspace} -> {resp.status_code}: {resp.text[:300]}"
        )

    # 4. Settle probe: alice's Editor binding effective AND the wildcard
    #    revocation propagated (alice must now be denied on the F1-5 route).
    alice = platform.token("alice")
    deadline = time.monotonic() + _PROVISION_TIMEOUT
    while time.monotonic() < deadline:
        ok = platform.request("GET", f"/apis/auditor/v2/workspaces/{WS_A}/targets", token=alice).status_code == 200
        revoked = platform.request("GET", "/apis/entities/v2/workspaces", token=alice).status_code == 403
        if ok and revoked:
            return
        time.sleep(_POLL)
    raise AssertionError("Provisioned bindings did not settle (alice 200 on wsA targets + 403 on workspaces list)")


# --------------------------------------------------------------------------- #
# Session fixtures                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def platform(issuer: MiniOIDCIssuer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Platform]:
    """Default-knob platform, fully provisioned."""
    gen = _spawn_platform(issuer, tmp_path_factory, "default", {})
    p = next(gen)
    _provision(p)
    yield p
    next(gen, None)


@pytest.fixture(scope="session")
def platform_knobs(issuer: MiniOIDCIssuer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Platform]:
    """Quarantine + PlatformAdmin-exemption knob platform (no extra provisioning)."""
    gen = _spawn_platform(
        issuer,
        tmp_path_factory,
        "knobs",
        {
            "NMP_AUTH_ON_INVALID_PLUGIN": "quarantine",
            "NMP_AUTH_PLATFORM_ADMIN_EXEMPT_FROM_SERVICE_ONLY": "true",
        },
    )
    p = next(gen)
    yield p
    next(gen, None)


# --------------------------------------------------------------------------- #
# Audit report                                                                 #
# --------------------------------------------------------------------------- #


_REPORT_KEY = pytest.StashKey[ReportCollector]()


@pytest.fixture(scope="session")
def report(request: pytest.FixtureRequest) -> ReportCollector:
    collector = ReportCollector()
    request.session.stash[_REPORT_KEY] = collector
    return collector


def pytest_sessionfinish(session: pytest.Session) -> None:
    collector = session.stash.get(_REPORT_KEY, None)
    if collector and collector.rows:
        out = _HERE / "AUTHZ_E2E_REPORT.md"
        out.write_text(collector.render())
        json_out = _HERE / "AUTHZ_E2E_REPORT.json"
        json_out.write_text(json.dumps(collector.as_json(), indent=2))
        print(f"\nAuthz E2E audit report: {out} ({len(collector.rows)} cases)")
