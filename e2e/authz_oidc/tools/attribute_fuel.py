"""Attribute the AIRCORE-797 fuel regression to individual branch rego additions.

Builds policy.wasm variants (each with one branch addition removed), evaluates
the same inputs against the same data, and reports per-rule fuel attribution.
Then probes scaling vs principal count and endpoint-pattern count.
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from nmp.core.auth.app.embedded_pdp.engine import OPAPolicy

REPO = Path.cwd()
POLICIES = REPO / "services/core/auth/src/nmp/core/auth/app/policies"
EXP = Path(os.environ.get("FUEL_EXP_DIR", "/tmp/fuel-exp"))  # holds live-bundle.tar.gz
LIMIT = 50_000_000_000

DENY_MARKER = """deny_request if {
\tendpoint_denied(extract_path, extract_method)
}
"""

FENCE = """deny_request if {
\tsome prefix in object.get(data.authz.config, "denied_plugin_prefixes", [])
\tpath_under_denied_prefix(split(extract_path, "?")[0], prefix)
}
"""

SERVICE_ONLY = """service_only_route if {
\tcallers := endpoint_callers(extract_path, extract_method)
\t"service_principal" in callers
\tnot "principal" in callers
}
"""

SERVICE_ONLY_DENY = """deny_request if {
\tservice_only_route
\tprincipal_id := extract_principal_id
\tnot startswith(principal_id, "service:")
\tnot platform_admin_exempt
}
"""

PRINCIPAL_ONLY = """principal_only_route if {
\tcallers := endpoint_callers(extract_path, extract_method)
\t"principal" in callers
\tnot "service_principal" in callers
}
"""

PRINCIPAL_ONLY_DENY = """deny_request if {
\tprincipal_only_route
\tprincipal_id := extract_principal_id
\tstartswith(principal_id, "service:")
}
"""

F15_ALLOW = """allow_request if {
\tapplicable_principals := get_applicable_principals
\tcount(applicable_principals) > 0

\tscope_check_passed

\tmethod := extract_method
\tmethod in ["GET", "HEAD"]
\tpath := extract_path
\tnormalize_endpoint(path)
\tnot extract_workspace_from_path(path)

\trequired_permissions := get_required_permissions(path, method)
\tcount(required_permissions) > 0

\tsome principal in applicable_principals
\thas_permissions(principal, "system", required_permissions)
}
"""

F15_GUARD = "\tnot endpoint_requires_permissions(path, method)\n"

VARIANTS = [
    ("branch (baseline)", []),
    ("- deny-marker rule", [DENY_MARKER]),
    ("- namespace fence rule", [FENCE]),
    ("- service-only route+deny", [SERVICE_ONLY, SERVICE_ONLY_DENY]),
    ("- principal-only route+deny", [PRINCIPAL_ONLY, PRINCIPAL_ONLY_DENY]),
    ("- F1-5 permissioned allow rule", [F15_ALLOW]),
    ("- F1-5 guard in permissionless rule", [F15_GUARD]),
    (
        "- ALL new deny rules",
        [DENY_MARKER, FENCE, SERVICE_ONLY, SERVICE_ONLY_DENY, PRINCIPAL_ONLY, PRINCIPAL_ONLY_DENY],
    ),
    (
        "- everything new (≈ main)",
        [
            DENY_MARKER,
            FENCE,
            SERVICE_ONLY,
            SERVICE_ONLY_DENY,
            PRINCIPAL_ONLY,
            PRINCIPAL_ONLY_DENY,
            F15_ALLOW,
            F15_GUARD,
        ],
    ),
]

CASES = [
    (
        "admin GET workspaces",
        {
            "principal_id": "usr-admin",
            "principal_email": "admin@harness.test",
            "method": "GET",
            "path": "/apis/entities/v2/workspaces",
        },
    ),
    (
        "editor GET ws list",
        {
            "principal_id": "usr-alice",
            "principal_email": "alice@harness.test",
            "method": "GET",
            "path": "/apis/auditor/v2/workspaces/authz-e2e-wsa/targets",
        },
    ),
    (
        "unbound deny",
        {
            "principal_id": "usr-nobody",
            "principal_email": "nobody@harness.test",
            "method": "GET",
            "path": "/apis/auditor/v2/workspaces/authz-e2e-wsa/targets",
        },
    ),
    (
        "service unknown path",
        {"principal_id": "service:probe", "method": "GET", "path": "/apis/auditor/v2/path-that-matches-no-rule"},
    ),
]


def load_data() -> dict:
    with tarfile.open(EXP / "live-bundle.tar.gz") as tf:
        member = next(m for m in tf.getmembers() if m.name.lstrip("/").endswith("data.json"))
        fobj = tf.extractfile(member)
        assert fobj is not None
        data = json.load(fobj)
    data["authz"]["principals"] = {
        "admin@harness.test": {"workspaces": {"system": ["PlatformAdmin"]}},
        "*": {"workspaces": {"default": ["Editor"], "system": ["Viewer"]}},
        "alice@harness.test": {"workspaces": {"authz-e2e-wsa": ["Editor"]}},
    }
    return data


def build_variant(removals: list[str]) -> str:
    src = (POLICIES / "authz.rego").read_text()
    for block in removals:
        assert src.count(block) == 1, f"block not unique/found:\n{block[:80]}..."
        src = src.replace(block, "")
    workdir = Path(tempfile.mkdtemp(prefix="fuelvar-"))
    pol = workdir / "policies"
    shutil.copytree(POLICIES, pol)
    (pol / "authz.rego").write_text(src)
    bundle = workdir / "bundle.tar.gz"
    subprocess.run(
        [
            "opa",
            "build",
            "-t",
            "wasm",
            "-e",
            "authz/allow",
            "-e",
            "authz/has_permissions",
            "-e",
            "authz/has_role",
            "-o",
            str(bundle),
            ".",
        ],
        cwd=pol,
        check=True,
        capture_output=True,
    )
    with tarfile.open(bundle) as tf:
        tf.extract("/policy.wasm", workdir, filter="data")
    return str(workdir / "policy.wasm")


def measure(wasm: str, data: dict) -> list[float]:
    pol = OPAPolicy(wasm, fuel_limit=LIMIT, memory_limit_mb=256)
    pol.set_data(data)
    out = []
    for _, inp in CASES:
        pol.evaluate(inp, entrypoint=0)
        out.append((LIMIT - pol.store.get_fuel()) / 1e6)
    return out


def main() -> None:
    data = load_data()
    print(f"{'variant':38} | " + " | ".join(f"{n:>20}" for n, _ in CASES))
    baseline: list[float] | None = None
    for name, removals in VARIANTS:
        fuels = measure(build_variant(removals), data)
        if baseline is None:
            baseline = fuels
            row = " | ".join(f"{f:17.1f}M   " for f in fuels)
        else:
            row = " | ".join(f"{f:9.1f}M ({f - b:+6.1f})" for f, b in zip(fuels, baseline))
        print(f"{name:38} | {row}")

    # Scaling probes on the unmodified branch policy.
    wasm = build_variant([])
    print("\nScaling: principal count (admin GET workspaces row)")
    for n in (3, 100, 1000):
        d = load_data()
        for i in range(n):
            d["authz"]["principals"][f"user{i}@x.test"] = {"workspaces": {f"ws{i % 20}": ["Editor"]}}
        f = measure(wasm, d)
        print(f"  {3 + n:5} principals: " + " | ".join(f"{x:8.1f}M" for x in f))

    print("\nScaling: endpoint-pattern count")
    for mult in (1, 2, 4):
        d = load_data()
        eps = dict(d["authz"]["endpoints"])
        for m in range(1, mult):
            for k, v in list(d["authz"]["endpoints"].items()):
                eps[f"/apis/zzfake{m}{k[5:]}"] = v
        d["authz"]["endpoints"] = eps
        f = measure(wasm, d)
        print(f"  {len(eps):5} patterns: " + " | ".join(f"{x:8.1f}M" for x in f))


if __name__ == "__main__":
    sys.exit(main())
