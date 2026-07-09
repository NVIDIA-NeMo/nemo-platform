# Machine identity for NeMo Platform via authentik (optional reference)

This is an optional reference, not part of the core platform. It stands up
[authentik](https://goauthentik.io/) as an OIDC identity provider and shows how a
**machine** (CI, an agent, a service) authenticates to NeMo Platform with its own
credential, with access controlled by NeMo's existing RBAC.

## Why this needs zero NeMo core changes

NeMo already validates any OIDC token and authorizes it:

- The middleware validates a `Authorization: Bearer <token>` JWT against the
  configured issuer and builds `Principal(id=sub, email, groups)`
  (`packages/nmp_common/src/nmp/common/auth/middleware.py`; `jwt.py` requires `sub`).
- `authorize_request` forwards the principal's groups to the policy engine
  (`packages/nmp_common/src/nmp/common/auth/client.py`), and the policy resolves
  roles over the union of id, email, and groups
  (`services/core/auth/src/nmp/core/auth/app/policies/common.rego`).

A machine's client-credentials token goes through the same path. So: put the machine
(a service account) in a group in your IdP, issue it tokens that carry the `groups`
claim, and bind a NeMo role to that group. NeMo is not a token authority; authentik
is.

> Security: do NOT use the internal `X-NMP-Principal-Id: service:` header for customer
> machines. That header is an unconditional trust path for internal services only, and
> the edge/gateway must strip inbound `X-NMP-Principal-*` headers. Customer machines
> authenticate via OIDC, as below.

## 1. Bring up authentik

```bash
cp contrib/authentik/env.example contrib/authentik/.env   # set AUTHENTIK_SECRET_KEY
docker compose -p nemo-authentik -f contrib/authentik/docker-compose.yml up -d
```

First start runs migrations (about a minute). The blueprint in `blueprints/nemo.yaml`
is applied automatically: an RS256 OAuth2 provider, the `nemo` application
(issuer `http://localhost:9000/application/o/nemo/`), groups `nemo-admins` and
`nemo-editors`, and a service account `svc-nemo-ci` in `nemo-editors` with a
non-expiring app-password token.

Confirm discovery:

```bash
curl -s http://localhost:9000/application/o/nemo/.well-known/openid-configuration | jq .issuer
```

## 2. Get a machine token (client credentials)

```bash
curl -s -X POST http://localhost:9000/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id=nemo-platform \
  -d client_secret=nemo-platform-secret-dev \
  -d username=svc-nemo-ci \
  -d password=svc-nemo-ci-token-secret-dev \
  -d scope="openid email groups" | jq -r .access_token
```

Verify the token first (this is the load-bearing check). Decode the payload and
confirm `sub` == `svc-nemo-ci`, `iss` == the configured issuer, and `groups` includes
`nemo-editors`:

```bash
TOKEN=...   # from above
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq '{sub, iss, aud, groups}'
```

## 3. Run NeMo against authentik

```bash
set -a && source packages/nmp_platform/config/local.env && set +a
export NMP_BASE_URL=http://127.0.0.1:8080
NMP_CONFIG_FILE_PATH=contrib/authentik/config/authentik.yaml \
  nemo services run --services auth,entities,models --host 127.0.0.1 --port 8080
```

## 4. Demonstrate: respected, scoped, revocable

Before any role binding, the machine is denied:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8080/apis/models/v2/workspaces/default/models -H "Authorization: Bearer $TOKEN"
# 403
```

Bind the `nemo-editors` group to a role (run as a service principal locally):

```bash
curl -s -X POST http://127.0.0.1:8080/apis/auth/v2/iam/role-bindings \
  -H "X-NMP-Principal-Id: service:bootstrap" \
  -H "Content-Type: application/json" \
  -d '{"principal": "nemo-editors", "role": "Editor", "workspace": "default"}'
```

Now the machine is authorized:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8080/apis/models/v2/workspaces/default/models -H "Authorization: Bearer $TOKEN"
# 200
```

Revoke by removing the binding (or the SA's group in authentik), and the machine is
denied again. Access is controlled entirely in NeMo via the group->role binding;
identity and credential lifecycle live in authentik.

## Tear down

```bash
docker compose -p nemo-authentik -f contrib/authentik/docker-compose.yml down -v
```

## What this does and does not do

Does: federated machine auth with scoped, revocable access, validated by existing
NeMo code, no core changes.

Does not: add NeMo-native service accounts. The service account, its credential, and
its lifecycle (create/rotate/revoke) live in authentik. NeMo only holds the role
binding. This is intentional: NeMo federates identity rather than becoming a token
authority.

## Verified locally (2026-06-16)

Run against this bundle (authentik 2024.x + NeMo from main, embedded PDP):

- Machine token claims: `sub=svc-nemo-ci`, `iss=http://localhost:9000/application/o/nemo/`, `groups=["nemo-editors"]`, `alg=RS256`.
- `GET /apis/models/v2/workspaces/default/models` with the token, before any binding: `403`.
- After binding `nemo-editors -> Editor` in `default`: `200`.
- After revoking the binding: `403`.

NeMo respected, scoped, and revoked the machine identity with no core code changes.
