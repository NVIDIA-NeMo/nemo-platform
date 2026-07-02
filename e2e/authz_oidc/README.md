# Authz E2E verification harness (real OIDC, signed JWTs)

Black-box verification that plugin HTTP authorization restricts access as
intended — exercised against a **real running platform** with identity supplied
exclusively as **RS256-signed JWTs from a real-HTTP test OIDC issuer**. This
covers the signed-JWT path end to end: `JWTValidator`'s discovery / JWKS /
signature / expiry / audience checks run over the network, which `opa test` and
the in-process integration tests (header principals, mocked `validate_token`)
do not exercise.

## One command

```sh
make build-policy   # once per rego change — policy.wasm is gitignored
uv run pytest e2e/authz_oidc -v --run-e2e
```

Produces `AUTHZ_E2E_REPORT.md` (+ `.json`, both gitignored) — one row per case:
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
   `.read`/`.list` permissions in `system` and the no-workspace permission-deny
   rows are untestable). The seeded `*`→Editor@default binding is left alone —
   no matrix row touches the `default` workspace.
5. **Runs the matrix** (`matrix.py`, ~40 cases), then repeats a small group on
   a second platform instance with `on_invalid_plugin=quarantine`.

## Matrix coverage

| Group | Verifies |
|-------|----------|
| authn | valid sig 200; no/expired/wrong-iss/wrong-aud/unknown-key/unsigned/garbage token → 401 |
| bindings | no binding → 403; Viewer read-not-write; cross-workspace isolation |
| no-workspace-get | permission-stamped no-`{workspace}` GET requires the permission in `system`; permissionless sibling stays open |
| scopes | `auditor:read` token: GET 200 / POST 403; `:write` POST 201; OIDC-only scopes = full power (documented); agents-gateway read/write method split |
| caller-kind | service principal denied on `callers=[principal]` route (symmetric half); human denied on service-only route (PlatformAdmin keeps its global bypass); service no-match bypass pinned as documented behavior |
| fence | unenumerable plugin namespace denied for human/service/PlatformAdmin incl. bare prefix; unruled route denied for everyone while ruled sibling works |
| knobs | quarantine fences the whole offending plugin |

Status-code conventions asserted throughout: **401** only when no identity was
established (missing/invalid token); **403** for every policy denial of an
authenticated principal. Two rows use a `not 403` oracle (agent-gateway proxy
404s on a nonexistent agent *after* authz passes; getting past the PDP is the
point).

## Known limits

- WebSocket routes are not enforced by the PDP middleware at all — deliberately
  absent from the matrix.
- `X-NMP-Principal-*` headers remain a trusted identity channel in this
  deployment shape; the harness never sends them, but does not prove they are
  stripped (that's an ingress concern, out of authz scope).
- `hard_fail` (the default `on_invalid_plugin` mode) aborts bundle build (auth
  service degraded) — its observable is process health, not a per-request status;
  not asserted here. Both harness phases pin a softer mode (`deny_route` /
  `quarantine`) so the platform stays up with the deliberately-broken fixtures.
