# Authz E2E verification harness (real OIDC, signed JWTs)

Black-box verification that the plugin-HTTP-authz rework (branch
`aircore-743-plugin-http-authz/md`, plan: Linear doc "Plugin HTTP Authz
(AIRCORE-743) — Implementation Plan & Decisions") restricts access as
intended — exercised against a **real running platform** with identity
supplied exclusively as **RS256-signed JWTs from a real-HTTP test OIDC
issuer**. This is the one authn path nothing else covers: `opa test` and the
in-process integration tests validate policy decisions and header principals,
but `JWTValidator`'s discovery/JWKS/signature/expiry/audience network path was
previously exercised only with `validate_token` mocked.

## One command

```sh
make build-policy   # once per rego change — policy.wasm is gitignored
uv run pytest e2e/authz_oidc -v --run-e2e
```

Produces `AUTHZ_E2E_REPORT.md` (+ `.json`) — one row per case:
request → token claims → expected status → observed status.

Not part of CI: everything is marked `e2e` and skipped without `--run-e2e`.

## What it does

1. **Starts a mini OIDC issuer** (`idp.py`) on a free localhost port: real
   `/.well-known/openid-configuration` + JWKS over HTTP, real RS256 signing.
   A second, unpublished key signs the "unknown key" case. Defective tokens
   (expired / wrong issuer / wrong audience / `alg=none`) are minted directly —
   the reason a production IdP container isn't used is that it *refuses* to
   mint these.
2. **Installs three fixture plugins** (editable, into the active venv):
   - `harness-fixture` — clean; declares the only `SERVICE_PRINCIPAL`-only
     route (no shipped plugin has one), plus an open control route.
   - `harness-unruled` — one ruled + one unruled route (deny-route
     containment / quarantine subject).
   - `harness-broken` — fails at import (unenumerable ⇒ namespace fence).
3. **Spawns `nemo services run`** on a free port with a fresh tmp data dir:
   `auth.enabled=true`, `oidc.enabled=true` → issuer, **`allow_unsigned_jwt=false`**
   (both local configs default it to *true*; with it on, the signed-JWT proof
   would be hollow), audience pinned, `NMP_SEED_ON_STARTUP=true`,
   `bundle_cache_seconds=0` for instant role-binding propagation.
4. **Provisions via signed service JWT** (`sub=service:e2e-harness` — the IAM
   role-binding API is service-principal-only at the handler, and a Bearer
   token whose `sub` starts with `service:` is a service principal end-to-end):
   creates workspaces `authz-e2e-wsa`/`-wsb`, binds alice→Editor@wsA,
   victor→Viewer@wsA, sam→Viewer@system, and **revokes the seeded wildcard
   `*`→Viewer@system binding** (otherwise every authenticated user holds all
   `.read`/`.list` permissions in `system` and the F1-5 deny rows are
   untestable). The seeded `*`→Editor@default binding is left alone — no
   matrix row touches the `default` workspace.
5. **Runs the matrix** (`matrix.py`, ~40 cases), then repeats a small group on
   a second platform instance with `on_invalid_plugin=quarantine` +
   `platform_admin_exempt_from_service_only=true`.

## Matrix coverage → branch findings

| Group | Verifies | Finding / decision |
|-------|----------|--------------------|
| authn | valid sig 200; no/expired/wrong-iss/wrong-aud/unknown-key/unsigned/garbage token → 401 | success criteria "Denied" |
| bindings | no binding → 403; Viewer read-not-write; cross-workspace isolation | success criteria |
| no-workspace-get | permission-stamped no-`{workspace}` GET requires the permission in `system`; permissionless sibling stays open | F1-5 |
| scopes | `auditor:read` token: GET 200 / POST 403; `:write` POST 201; OIDC-only scopes = full power (documented); agents-gateway read/write method split | F1-13 |
| caller-kind | service principal denied on `callers=[principal]` route (symmetric half); human & PlatformAdmin denied on service-only route; service no-match bypass pinned as documented behavior | F1-8/F1-9, D1/D6 |
| fence | unenumerable plugin namespace denied for human/service/PlatformAdmin incl. bare prefix; unruled route denied for everyone while ruled sibling works | F1-11/F1-12, F2-4, D4 |
| knobs | quarantine fences the whole offending plugin; exemption knob admits PlatformAdmin (and only PlatformAdmin) to service-only routes | D4, D6 |

Status-code conventions asserted throughout: **401** only when no identity was
established (missing/invalid token); **403** for every policy denial of an
authenticated principal. Two rows use a `not 403` oracle (agent-gateway proxy
404s on a nonexistent agent *after* authz passes; getting past the PDP is the
point).

## Findings (2026-06-12 harness shakedown)

Building and running this harness surfaced four issues; all are verified live:

1. **Namespace fence didn't cover subpaths in production (branch bug, FIXED
   here).** `path_under_denied_prefix`'s subpath arm was written with
   `sprintf`, an SDK-provided builtin the embedded engine stubs to return 0
   (`engine.py` `opa_builtin*` imports). The deny silently never fired for
   `/apis/<broken-plugin>/<anything>` — only the bare prefix was fenced — so a
   service principal fell through the no-match bypass to any mounted route of
   a quarantined plugin. `opa test` passes either way (the Go evaluator has
   every builtin), which is why only a real-WASM path could catch it. Fixed in
   `authz.rego` with wasm-native builtins; pinned by
   `TestWasmNativeBuiltins` in `services/core/auth/tests/test_embedded_pdp.py`
   (asserts the compiled policy requires zero host builtins).
2. **Embedded-PDP fuel regression (branch, OPEN).** Branch rego costs 25–57%
   more fuel per eval than main (same opa 1.8.0, same data); the
   PlatformAdmin-bypass eval went 71.4M → 111.8M, past the 100M default
   `auth.embedded_pdp_cpu_limit`, so a default-config platform 502s every
   request once seeded principals load. The harness sets
   `NMP_AUTH_EMBEDDED_PDP_CPU_LIMIT=2000` to proceed; the default (and the
   stale "typical 20-25M" docstring in `services/core/auth/config.py`) needs
   revisiting. Reproduce with `tools/measure_fuel.py`.
3. **IAM revoke ignores the binding's workspace (pre-existing).**
   `DELETE /apis/auth/v2/iam/role-bindings/{name}` looks the entity up without
   a workspace (defaults to `default`) and 404s for any binding stored
   elsewhere — e.g. every system-workspace binding (`iam/endpoints.py:230`).
4. **Workspace-members removal filter never matches (pre-existing).**
   `remove_workspace_member` filters on `data.workspace`, but role-binding
   entities don't carry a `workspace` key inside `data` (it's the envelope
   column) — "Member not found" for seeded/IAM-created bindings. The harness
   revokes the seeded wildcard via the generic entities API instead.

## Known limits

- WebSocket routes are not enforced by the PDP middleware at all (tracked
  branch follow-up) — deliberately absent from the matrix.
- `X-NMP-Principal-*` headers remain a trusted identity channel in this
  deployment shape; the harness never sends them, but does not prove they are
  stripped (that's an ingress concern, out of authz scope).
- `hard_fail` mode aborts bundle build (auth service degraded) — its
  observable is process health, not a per-request status; not asserted here.
