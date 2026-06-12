# Authz E2E verification report (real OIDC, signed JWTs)

Generated 2026-06-12 19:09 UTC by `e2e/authz_oidc` — 50/50 cases passed.

Identity for every request is an RS256-signed JWT minted by the in-harness
OIDC issuer and validated by the platform via JWKS discovery
(`auth.allow_unsigned_jwt=false`; no `X-NMP-Principal-*` headers anywhere).

## authn (default phase)

| case | finding | request | identity (claims) | expected | observed | result |
|------|---------|---------|-------------------|----------|----------|--------|
| A1 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test | 200 | 200 | PASS |
| A2 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | anonymous: (no Authorization header) | 401 | 401 | PASS |
| A3 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, EXPIRED | 401 | 401 | PASS |
| A4 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, iss=http://127.0.0.1:1/evil-issuer | 401 | 401 | PASS |
| A5 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, aud=some-other-audience | 401 | 401 | PASS |
| A6 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, key=unpublished | 401 | 401 | PASS |
| A7 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, alg=none | 401 | 401 | PASS |
| A8 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: (garbage bearer string) | 401 | 401 | PASS |


## bindings (default phase)

| case | finding | request | identity (claims) | expected | observed | result |
|------|---------|---------|-------------------|----------|----------|--------|
| B1 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | nobody: sub=usr-nobody, email=nobody@harness.test | 403 | 403 | PASS |
| B2 | - | `POST /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test | 201 | 201 | PASS |
| B3 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | victor: sub=usr-victor, email=victor@harness.test | 200 | 200 | PASS |
| B4 | - | `POST /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | victor: sub=usr-victor, email=victor@harness.test | 403 | 403 | PASS |
| B5 | - | `GET /apis/auditor/v2/workspaces/authz-e2e-wsb/targets` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |


## no-workspace-get (default phase)

| case | finding | request | identity (claims) | expected | observed | result |
|------|---------|---------|-------------------|----------|----------|--------|
| C1 | F1-5 | `GET /apis/entities/v2/workspaces` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |
| C2 | F1-5 | `GET /apis/entities/v2/workspaces` | sam: sub=usr-sam, email=sam@harness.test | 200 | 200 | PASS |
| C3 | F1-5 | `GET /apis/evaluator/v1/hello/world` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |
| C4 | F1-5 | `GET /apis/evaluator/v1/hello/world` | sam: sub=usr-sam, email=sam@harness.test | 200 | 200 | PASS |
| C5 | F1-5 | `GET /apis/evaluator/v1/healthz` | alice: sub=usr-alice, email=alice@harness.test | 200 | 200 | PASS |
| C6 | F1-5 | `GET /apis/evaluator/v1/healthz` | anonymous: (no Authorization header) | 401 | 401 | PASS |


## scopes (default phase)

| case | finding | request | identity (claims) | expected | observed | result |
|------|---------|---------|-------------------|----------|----------|--------|
| D1 | F1-13 | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, scope=auditor:read | 200 | 200 | PASS |
| D2 | F1-13 | `POST /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, scope=auditor:read | 403 | 403 | PASS |
| D3 | F1-13 | `POST /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, scope=auditor:write | 201 | 201 | PASS |
| D4 | F1-13 | `POST /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | alice: sub=usr-alice, email=alice@harness.test, scope=openid profile email | 201 | 201 | PASS |
| D5 | F1-13 | `GET /apis/agents/v2/workspaces/authz-e2e-wsa/agents/ghost-agent/-/health` | alice: sub=usr-alice, email=alice@harness.test, scope=agents:read | not 403 | 404 | PASS |
| D6 | F1-13 | `POST /apis/agents/v2/workspaces/authz-e2e-wsa/agents/ghost-agent/-/health` | alice: sub=usr-alice, email=alice@harness.test, scope=agents:read | 403 | 403 | PASS |
| D7 | F1-13 | `POST /apis/agents/v2/workspaces/authz-e2e-wsa/agents/ghost-agent/-/health` | alice: sub=usr-alice, email=alice@harness.test, scope=agents:write | not 403 | 404 | PASS |

- **D4** — OIDC-only scopes (no area:verb) = full power, documented. scopes.rego: tokens with no colon-scopes skip the scope gate by design
- **D5** — Gateway read method passes with agents:read (authz oracle: not 403). proxy 404s on the nonexistent agent AFTER authorization passes

## caller-kind (default phase)

| case | finding | request | identity (claims) | expected | observed | result |
|------|---------|---------|-------------------|----------|----------|--------|
| E1 | F1-8 | `GET /apis/auditor/v2/workspaces/authz-e2e-wsa/targets` | service: sub=service:probe | 403 | 403 | PASS |
| E10 | - | `POST /apis/auth/v2/authz/allow` | provisioner: sub=service:e2e-harness | 401 | 401 | PASS |
| E2 | F1-8 | `GET /apis/harness-fixture/probe/service-only` | service: sub=service:probe | 200 | 200 | PASS |
| E3 | F1-8 | `GET /apis/harness-fixture/probe/service-only` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |
| E4 | F1-8/D6 | `GET /apis/harness-fixture/probe/service-only` | admin: sub=usr-admin, email=admin@harness.test | 403 | 403 | PASS |
| E5 | - | `GET /apis/harness-fixture/probe/open` | alice: sub=usr-alice, email=alice@harness.test | 200 | 200 | PASS |
| E6 | - | `GET /apis/auditor/v2/path-that-matches-no-rule` | service: sub=service:probe | not 403 | 404 | PASS |
| E7 | - | `GET /apis/auditor/v2/path-that-matches-no-rule` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |
| E8 | F1-9 | `POST /apis/auth/v2/iam/role-bindings` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |
| E9 | F1-9 | `GET /apis/auth/v2/iam/role-bindings` | provisioner: sub=service:e2e-harness | 200 | 200 | PASS |

- **E1** — Service principal denied on callers=[principal] route. pre-branch this passed via the ServiceSystem '*' wildcard
- **E10** — PDP entrypoint rejects Bearer identity (header-principal only). middleware consults only X-NMP-Principal-Id on /apis/auth/v2/authz/*
- **E6** — Service no-match bypass pinned: unknown path under healthy plugin -> authz passes (404). documents the deliberate service:* bypass for unmatched paths (authz.rego:61-71)

## fence (default phase)

| case | finding | request | identity (claims) | expected | observed | result |
|------|---------|---------|-------------------|----------|----------|--------|
| F1 | F1-11/12 | `GET /apis/harness-broken/anything` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |
| F2 | F2-4 | `GET /apis/harness-broken/anything` | service: sub=service:probe | 403 | 403 | PASS |
| F3 | F1-11/12 | `GET /apis/harness-broken/anything` | admin: sub=usr-admin, email=admin@harness.test | 403 | 403 | PASS |
| F4 | F2-4 | `GET /apis/harness-broken` | service: sub=service:probe | 403 | 403 | PASS |
| F5 | D4 | `GET /apis/harness-unruled/ruled` | alice: sub=usr-alice, email=alice@harness.test | 200 | 200 | PASS |
| F6 | D4 | `GET /apis/harness-unruled/unruled` | alice: sub=usr-alice, email=alice@harness.test | 403 | 403 | PASS |
| F7 | D4 | `GET /apis/harness-unruled/unruled` | service: sub=service:probe | 403 | 403 | PASS |
| F8 | D4 | `GET /apis/harness-unruled/unruled` | admin: sub=usr-admin, email=admin@harness.test | 403 | 403 | PASS |


## knobs (knobs phase)

| case | finding | request | identity (claims) | expected | observed | result |
|------|---------|---------|-------------------|----------|----------|--------|
| G1 | D4 | `GET /apis/harness-unruled/ruled` | service: sub=service:probe | 403 | 403 | PASS |
| G2 | D4 | `GET /apis/harness-unruled/ruled` | admin: sub=usr-admin, email=admin@harness.test | 403 | 403 | PASS |
| G3 | D6 | `GET /apis/harness-fixture/probe/service-only` | admin: sub=usr-admin, email=admin@harness.test | 200 | 200 | PASS |
| G4 | D6 | `GET /apis/harness-fixture/probe/service-only` | nobody: sub=usr-nobody, email=nobody@harness.test | 403 | 403 | PASS |
| G5 | D6 | `GET /apis/harness-fixture/probe/service-only` | service: sub=service:probe | 200 | 200 | PASS |
| G6 | - | `GET /apis/entities/v2/workspaces` | admin: sub=usr-admin, email=admin@harness.test | 200 | 200 | PASS |

