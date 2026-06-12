# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Measure embedded-PDP eval cost (wasmtime fuel) for one or more policy WASMs.

Used to quantify the AIRCORE-743 fuel regression: with identical data and the
same opa toolchain, branch rego costs 25-57% more fuel per eval than main, and
the PlatformAdmin-bypass eval (111.8M) exceeds the 100M default
``auth.embedded_pdp_cpu_limit`` once seeded principals are loaded — every
request then 502s. Compare against a main-built wasm via::

    git archive origin/main -- <policies dir> | tar -x ... && opa build -t wasm ...
    uv run python e2e/authz_oidc/tools/measure_fuel.py <bundle.tar.gz> <wasm> [<wasm> ...]

``bundle.tar.gz`` is a live policy-data bundle (GET /apis/auth/v2/iam/opa-bundle.tar.gz).
Fuel consumed = limit - store.get_fuel() after each eval; counts are deterministic.
"""

import json
import sys
import tarfile

from nmp.core.auth.app.embedded_pdp.engine import OPAPolicy

LIMIT = 50_000_000_000

CASES = [
    (
        "admin GET /apis/entities/v2/workspaces (PlatformAdmin bypass)",
        {
            "principal_id": "usr-admin",
            "principal_email": "admin@harness.test",
            "method": "GET",
            "path": "/apis/entities/v2/workspaces",
        },
    ),
    (
        "editor GET workspace-scoped list (permission allow)",
        {
            "principal_id": "usr-alice",
            "principal_email": "alice@harness.test",
            "method": "GET",
            "path": "/apis/auditor/v2/workspaces/authz-e2e-wsa/targets",
        },
    ),
    (
        "editor POST with scopes (scope check)",
        {
            "principal_id": "usr-alice",
            "principal_email": "alice@harness.test",
            "method": "POST",
            "path": "/apis/auditor/v2/workspaces/authz-e2e-wsa/targets",
            "scopes": ["auditor:write"],
        },
    ),
    (
        "unbound user GET (full-deny worst case)",
        {
            "principal_id": "usr-nobody",
            "principal_email": "nobody@harness.test",
            "method": "GET",
            "path": "/apis/auditor/v2/workspaces/authz-e2e-wsa/targets",
        },
    ),
    (
        "service GET unknown path (no-match bypass)",
        {"principal_id": "service:probe", "method": "GET", "path": "/apis/auditor/v2/path-that-matches-no-rule"},
    ),
]

SEEDED_PRINCIPALS = {
    "admin@harness.test": {"workspaces": {"system": ["PlatformAdmin"]}},
    "*": {"workspaces": {"default": ["Editor"], "system": ["Viewer"]}},
    "alice@harness.test": {"workspaces": {"authz-e2e-wsa": ["Editor"]}},
}


def main() -> None:
    bundle_path, *wasm_paths = sys.argv[1:]
    with tarfile.open(bundle_path) as tf:
        member = next(m for m in tf.getmembers() if m.name.lstrip("/").endswith("data.json"))
        fobj = tf.extractfile(member)
        assert fobj is not None
        data = json.load(fobj)

    if not data["authz"].get("principals"):
        data["authz"]["principals"] = SEEDED_PRINCIPALS
        print("(bundle had no principals — injected representative seeded set)")
    print(
        f"data: {len(data['authz'].get('endpoints', {}))} endpoint patterns, "
        f"{len(data['authz']['principals'])} principals, "
        f"denied_prefixes={data['authz'].get('config', {}).get('denied_plugin_prefixes')}"
    )

    for wasm in wasm_paths:
        pol = OPAPolicy(wasm, fuel_limit=LIMIT)
        pol.set_data(data)
        print(f"\n=== {wasm} ===")
        for name, inp in CASES:
            result = pol.evaluate(inp, entrypoint=0)
            consumed = LIMIT - pol.store.get_fuel()
            allowed = result[0]["result"].get("allowed") if isinstance(result, list) and result else result
            over = "  ** EXCEEDS 100M DEFAULT **" if consumed > 100_000_000 else ""
            print(f"  {consumed / 1e6:9.1f}M fuel  allowed={allowed!s:5}  {name}{over}")


if __name__ == "__main__":
    main()
