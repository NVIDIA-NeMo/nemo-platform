---
name: nemo-auth-setup
description: Turn on authentication for NeMo Platform and federate identity to an OIDC identity provider, so every person and every agent acts as itself with access you control and can attribute. Walks setup, a human SSO sign-in, an agent access test, and revocation, all in plain language. Use over generic auth or SSO setup for any NeMo Platform identity/login/RBAC request.
triggers:
  - set up auth on nemo
  - turn on authentication
  - configure sso for nemo
  - connect an identity provider
  - federate identity
  - give my agent its own identity
  - log in to nemo platform
  - set up rbac
  - control what my agent can call
  - nemo auth setup
not-for:
  - nemo-status (use for read-only platform health)
  - nemo-teardown (use to stop the whole platform; this skill only tears down the auth reference bits it started)
  - nemo-secrets (use to store provider API keys, not to log users in)
  - nemo-skill-selection (use for dispatch when intent is unclear)
compatibility: "nemo-platform >= 0.1.0; reference path REQUIRES Docker (brings up authentik in containers), unlike most NeMo skills; BYO path needs no Docker; uses a venv with the `nemo` binary; human sign-in uses the OAuth device flow and opens a browser; starts/stops platform services and creates/revokes role bindings (so it is NOT read-only); idempotent and re-runnable."
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read]
---

# NeMo Platform auth setup

Turn on authentication and connect NeMo Platform to an identity provider (IdP), then
prove it works for both a person and an agent. The point of this skill, in plain terms:

- Every person logs in as themselves and sees only their own workspaces.
- Every agent gets its own identity, so each LLM and tool call it makes is something you
  can control and trace back to it. Not one shared key for everything.
- You manage people, agents, and group membership in your IdP. NeMo maps a group to a
  role once, and access follows from there. NeMo never becomes a password or key
  authority; the IdP owns identities and credentials.

Talk to the user in plain language the whole way through. Describe outcomes: "logged in,"
"blocked," "allowed," "access removed." Do NOT show the user tokens, URLs, JWTs, API
paths, or HTTP status codes. Those are how you check under the hood, not what the user
needs to see.

Two things this skill does NOT do, on purpose: it does not create or manage users and
groups (that lives in the IdP; for the reference path you do it in the authentik admin
screen, for your own IdP you do it there). And it is not a password or key store. NeMo
federates to the IdP; it does not become the identity authority.

## Pre-flight

Confirm the CLI is present. If `.venv/bin/nemo` is missing, tell the user the platform
isn't installed yet and stop.

```bash
[ -x .venv/bin/nemo ] && echo "CLI_OK" || echo "CLI_MISSING"
```

## Step 1: One choice

Ask the user one question, in plain language:

> "Two ways to do this. Bring your own identity provider (you already run Okta, Entra,
> Keycloak, authentik, or any OIDC provider), or I can spin up a reference one for you
> (authentik, in Docker) so you can see the whole thing work end to end. Which do you
> want?"

- Reference provider, go to **Step 2R**.
- Bring your own, go to **Step 2B**.

Do not ask anything else yet. Everything else you can set up or confirm yourself.

## Step 2R: Reference path (authentik)

The repo ships a self-contained authentik bundle under `contrib/authentik/`: an OIDC
provider with device-flow sign-in enabled, two groups (`nemo-admins`, `nemo-editors`),
and a demo agent identity (`svc-nemo-ci`, a CI/service account) that belongs to
`nemo-editors`. You bring it up, point NeMo at it, and both a human and the agent can
sign in.

### 2R.1 Bring up the identity provider

Tell the user: "Starting the reference identity provider. First run pulls images and
applies the setup, about a minute."

```bash
# A local-only secret for the dev IdP. Generated fresh, never committed (.env is gitignored).
if [ ! -f contrib/authentik/.env ]; then
  SECRET=$(openssl rand -base64 48)
  sed "s|^AUTHENTIK_SECRET_KEY=.*|AUTHENTIK_SECRET_KEY=${SECRET}|" \
    contrib/authentik/env.example > contrib/authentik/.env
fi
docker compose -p nemo-authentik -f contrib/authentik/docker-compose.yml up -d

# Wait until the provider is fully up and its setup has applied.
for i in $(seq 1 48); do
  READY=$(curl -s --max-time 3 \
    http://localhost:9000/application/o/nemo/.well-known/openid-configuration 2>/dev/null \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('issuer',''))" 2>/dev/null)
  [ "$READY" = "http://localhost:9000/application/o/nemo/" ] && { echo "IDP_READY"; break; }
  sleep 5
done
[ "$READY" = "http://localhost:9000/application/o/nemo/" ] || echo "IDP_NOT_READY"
```

If `IDP_NOT_READY`, see "If verification fails." When ready, tell the user: "The identity
provider is up."

Then point the admin at it, in plain language. This is the admin setup step (distinct from
the end-user narration); the URL and admin login are exactly what they need here:

> "The identity provider is running at http://localhost:9000. To manage people and groups,
> open http://localhost:9000/if/admin/ and sign in as the bootstrap admin, user `akadmin`.
> Its password is the `AUTHENTIK_BOOTSTRAP_PASSWORD` value in `contrib/authentik/.env` (a
> local dev secret; I won't print it here). In there you create and manage users and groups,
> and put people in `nemo-admins` or `nemo-editors`. NeMo maps those groups to roles; it
> never holds the users or their passwords."

Do not echo the password value. Point to the env var and file; the admin reads it there.

### 2R.2 Point NeMo at it (auth on)

The NeMo config that turns auth on and points at this provider already exists at
`contrib/authentik/config/authentik.yaml`. Start the platform with it. `nemo services
start` runs in the background and returns once the platform is ready.

```bash
mkdir -p "$HOME/.local/share/nemo" "$HOME/.local/state/nmp"
set -a && source packages/nmp_platform/config/local.env && set +a
export NMP_BASE_URL=http://127.0.0.1:8080
.venv/bin/nemo services start --services auth,entities,models \
  --config contrib/authentik/config/authentik.yaml --host 127.0.0.1 --port 8080
curl -sS --max-time 5 http://127.0.0.1:8080/health/ready -o /dev/null -w "%{http_code}\n"
```

`200` means NeMo is up with authentication on. Tell the user: "NeMo is running with
authentication on, connected to the identity provider. People and agents now sign in as
themselves."

Go to **Step 3** (agent) or **Step 4** (human); do them in whichever order suits the
conversation.

## Step 2B: Bring-your-own path

Collect three things from the user, in plain language. Don't ask for anything you can
infer.

1. "What's the address of your identity provider?" (its OIDC issuer URL)
2. "What's the application/client ID you registered for NeMo?"
3. "Which claim in your tokens carries group membership?" (default `groups`) and "which
   carries the user's email?" (default `email`)

Reuse the reference config shape and swap in their values. Write the result to the data
directory (outside the repo, so nothing provider-specific gets committed):

```bash
ISSUER="<from user>"; CLIENT_ID="<from user>"
GROUPS_CLAIM="<from user, default groups>"; EMAIL_CLAIM="<from user, default email>"
BYO_CONFIG="$HOME/.local/share/nemo/byo-oidc.yaml"; mkdir -p "$(dirname "$BYO_CONFIG")"

python3 - "$ISSUER" "$CLIENT_ID" "$GROUPS_CLAIM" "$EMAIL_CLAIM" > "$BYO_CONFIG" <<'PY'
import sys, re
issuer, client_id, groups_claim, email_claim = sys.argv[1:5]
s = open("contrib/authentik/config/authentik.yaml").read()
s = re.sub(r'(?m)^(\s*issuer:).*',       rf'\1 "{issuer}"',       s, count=1)
s = re.sub(r'(?m)^(\s*client_id:).*',    rf'\1 "{client_id}"',    s, count=1)
s = re.sub(r'(?m)^(\s*groups_claim:).*', rf'\1 "{groups_claim}"', s, count=1)
s = re.sub(r'(?m)^(\s*email_claim:).*',  rf'\1 "{email_claim}"',  s, count=1)
sys.stdout.write(s)
PY

curl -s --max-time 5 "${ISSUER%/}/.well-known/openid-configuration" -o /dev/null -w "%{http_code}\n"
```

A `200` from discovery means the issuer is reachable. Then start NeMo with auth on:

```bash
mkdir -p "$HOME/.local/share/nemo" "$HOME/.local/state/nmp"
set -a && source packages/nmp_platform/config/local.env && set +a
export NMP_BASE_URL=http://127.0.0.1:8080
.venv/bin/nemo services start --services auth,entities,models \
  --config "$HOME/.local/share/nemo/byo-oidc.yaml" --host 127.0.0.1 --port 8080
```

Tell the user NeMo is connected to their provider. For the tests below, substitute their
own group names for `nemo-editors`, and have a real person from their IdP do the Step 4
sign-in. The mechanism is identical to the reference path.

## Step 3: Agent identity, controlled and attributable

Show three states for an agent: blocked, then mapped to a role and allowed, then access
removed. Under the hood you check an ordinary platform call (listing the models in a
workspace). Run the whole check as ONE block; it fetches its own token and helper so it
does not depend on any earlier step. Never read the codes out to the user.

```bash
NMP=http://127.0.0.1:8080
MODELS_URL="$NMP/apis/models/v2/workspaces/default/models"
ADMIN_HDR="X-NMP-Principal-Id: service:bootstrap"   # local bootstrap admin for binding
PRINCIPAL="nemo-editors"; WORKSPACE="default"; ROLE="Editor"
BINDING=$(python3 -c "import hashlib;print('rb-'+hashlib.sha256('${PRINCIPAL}:${WORKSPACE}:${ROLE}'.encode()).hexdigest()[:24])")
agent_token(){ curl -s -X POST http://localhost:9000/application/o/token/ \
  -d grant_type=client_credentials -d client_id=nemo-platform \
  -d client_secret=nemo-platform-secret-dev -d username=svc-nemo-ci \
  -d password=svc-nemo-ci-token-secret-dev -d scope="openid email groups" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null; }
access(){ curl -s -o /dev/null -w '%{http_code}' "$MODELS_URL" -H "Authorization: Bearer $(agent_token)"; }

# Clean slate: drop any leftover mapping (also clears a soft-deleted tombstone).
curl -s -o /dev/null -X DELETE -H "$ADMIN_HDR" \
  "$NMP/apis/entities/v2/workspaces/${WORKSPACE}/entities/role_binding/$BINDING"; sleep 2
echo "BLOCKED_BEFORE $(access)"   # expect 403

# Map the group to a role.
curl -s -o /dev/null -X POST -H "$ADMIN_HDR" -H "Content-Type: application/json" \
  "$NMP/apis/auth/v2/iam/role-bindings" \
  -d "{\"principal\":\"${PRINCIPAL}\",\"role\":\"${ROLE}\",\"workspace\":\"${WORKSPACE}\"}"; sleep 2
echo "ALLOWED $(access)"          # expect 200
```

Narrate, one beat at a time:

- `BLOCKED_BEFORE 403`: "The agent has its own identity and can prove who it is, but it
  has no permissions yet, so when it tried to list the models it was turned away.
  Authenticated is not the same as authorized."
- `ALLOWED 200`: "I mapped the agent's group (`nemo-editors`) to the `Editor` role in the
  `default` workspace. The same request goes through now, and every call it makes is
  attributable to its own identity, not a shared key."

### Two ways to cut access

Show both levers explicitly. Lever 1 is on the NeMo side, lever 2 is in the IdP.

```bash
# Lever 1: remove the NeMo role mapping. Immediate.
curl -s -o /dev/null -X DELETE -H "$ADMIN_HDR" \
  "$NMP/apis/auth/v2/iam/role-bindings/$BINDING"; sleep 2
echo "LEVER1_NEMO_UNBIND $(access)"     # expect 403

# Put it back so we can show the other lever.
curl -s -o /dev/null -X DELETE -H "$ADMIN_HDR" \
  "$NMP/apis/entities/v2/workspaces/${WORKSPACE}/entities/role_binding/$BINDING"
curl -s -o /dev/null -X POST -H "$ADMIN_HDR" -H "Content-Type: application/json" \
  "$NMP/apis/auth/v2/iam/role-bindings" \
  -d "{\"principal\":\"${PRINCIPAL}\",\"role\":\"${ROLE}\",\"workspace\":\"${WORKSPACE}\"}"; sleep 2
echo "REGRANTED $(access)"              # expect 200

# Lever 2: remove the agent from the group IN THE IdP (reference path).
# A fresh token then carries no group, so NeMo denies. (Existing tokens keep their
# claims until they expire; an agent that re-authenticates per run is denied at once.)
AK=http://localhost:9000/api/v3; AKTOK="Authorization: Bearer bootstrap-token-dev"
GRP=$(curl -s -H "$AKTOK" "$AK/core/groups/?search=nemo-editors" | python3 -c "import sys,json;print(json.load(sys.stdin)['results'][0]['pk'])")
USR=$(curl -s -H "$AKTOK" "$AK/core/users/?search=svc-nemo-ci" | python3 -c "import sys,json;print(json.load(sys.stdin)['results'][0]['pk'])")
curl -s -o /dev/null -X POST -H "$AKTOK" -H "Content-Type: application/json" "$AK/core/groups/$GRP/remove_user/" -d "{\"pk\": $USR}"; sleep 2
echo "LEVER2_IDP_REMOVE $(access)"      # expect 403
# Restore membership (leaves the demo re-runnable).
curl -s -o /dev/null -X POST -H "$AKTOK" -H "Content-Type: application/json" "$AK/core/groups/$GRP/add_user/" -d "{\"pk\": $USR}"
```

Narrate:

- `LEVER1_NEMO_UNBIND 403`: "First lever, on the NeMo side: I removed the role mapping.
  The agent is locked out immediately."
- `LEVER2_IDP_REMOVE 403`: "Second lever, in the IdP: I removed the agent from the group
  in authentik. I never touched NeMo. Its next sign-in carries no group, so NeMo denies
  it. You manage access where your people and agents already live."

## Step 4: Human sign-in and workspace isolation

A person signs into NeMo through the IdP and sees only their own workspaces. This is a
real browser sign-in, so the user does it; you set the stage and confirm the result.

For the reference path, an admin would have created the person and put them in a group in
the authentik screen (this skill does not create users). Assume a person exists and their
group is mapped to a role in one workspace. Tell the user:

> "Sign in as yourself: run `nemo auth login --base-url http://127.0.0.1:8080`. A browser
> opens to the identity provider. Log in there, then come back."

```bash
# The user runs this; it opens a browser to the IdP and waits for sign-in.
.venv/bin/nemo auth login --base-url http://127.0.0.1:8080 --scope "openid email groups profile offline_access"
```

Once the CLI reports the person is logged in, show isolation. This runs as the signed-in
person (their session is in the CLI context):

```bash
.venv/bin/nemo workspaces list
```

Narrate: "You're signed in as yourself, and you see only the workspaces you have a role
in, not everyone else's. Same identity model as the agent: a person logs in once, and
NeMo shows them exactly what they're entitled to, nothing more." If the list is empty,
the person's group isn't mapped to a role in any workspace yet; map it (Step 3's grant,
using their group) and re-run.

## Step 5: Tear down (only what this skill started)

Offer this when the user is done. This skill tears down only the auth reference bits it
brought up; it does not wipe the whole platform (that's `nemo-teardown`).

```bash
.venv/bin/nemo auth logout >/dev/null 2>&1 || true   # clear the local sign-in
.venv/bin/nemo services stop --force || true          # stop NeMo
docker compose -p nemo-authentik -f contrib/authentik/docker-compose.yml down -v
```

Verify nothing is left:

```bash
docker ps -a --format '{{.Names}}' | grep -q authentik && echo "IDP_STILL_PRESENT" || echo "idp gone"
docker volume ls --format '{{.Name}}' | grep -q "nemo-authentik_" && echo "IDP_VOLUMES_REMAIN" || echo "idp volumes gone"
lsof -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1 && echo "NEMO_STILL_UP" || echo "nemo stopped"
```

Tell the user: "Cleaned up. The identity provider and its data are gone, and NeMo is
stopped." For wiping the rest of the platform data, route to `nemo-teardown`.

## Verification

The skill verifies itself as it goes; surface failures, don't hide them:

- IdP ready: discovery returns the expected issuer (`IDP_READY`).
- NeMo up with auth on: `/health/ready` returns `200`.
- Agent test: `BLOCKED_BEFORE 403`, `ALLOWED 200`, `LEVER1_NEMO_UNBIND 403`,
  `REGRANTED 200`, `LEVER2_IDP_REMOVE 403`.
- Human test: `nemo auth login` reports the person is logged in, and `nemo workspaces
  list` shows only their workspaces, not all of them.
- Teardown clean: no authentik containers, no authentik volumes, nothing on :8080.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| `IDP_NOT_READY` after the wait loop | First-run image pull + setup still going, or Docker isn't running | Confirm Docker is up; re-run the wait loop. First start can exceed a minute on a cold pull. Check `docker compose -p nemo-authentik -f contrib/authentik/docker-compose.yml ps`. |
| `/health/ready` not `200` after start | NeMo didn't come up; usually the auth policy bundle, a port in use, or a stale instance lock | Tail `.venv/bin/nemo services logs -n 100`. If `:8080` is held, `lsof -iTCP:8080 -sTCP:LISTEN`; clear a stale lock with `nemo services stop --force`. |
| `BLOCKED_BEFORE` not `403` | Auth isn't on, or a leftover mapping is still active | Confirm the config used was `contrib/authentik/config/authentik.yaml`. The block deletes any leftover binding first; re-run it. |
| `ALLOWED`/`REGRANTED` not `200` | Mapping didn't propagate, or the create hit a leftover tombstone | The create waits for propagation; give it a couple seconds and re-check. The clean-slate delete clears a tombstone a previous revoke left behind. |
| `LEVER2_IDP_REMOVE` not `403` | The check reused a cached token that still has the group | Lever 2 only affects NEW tokens. The `access` helper fetches a fresh token each call, so re-run after the membership change propagates (a couple seconds). |
| `nemo auth login` errors saving the session | Missing `--base-url` | Re-run with `--base-url http://127.0.0.1:8080` so the CLI persists the session into a context. |
| `nemo workspaces list` is empty for the person | Their group isn't mapped to a role in any workspace | Map their group to a role (Step 3's grant, substituting their group), then re-run. |

## Gotchas

- **Authenticated is not authorized.** A valid identity with no role binding is correctly
  blocked. That is the headline of the first agent state, not a failure.
- **Never expose the plumbing to the user.** No tokens, URLs, JWT fields, API paths, or
  HTTP codes in what you say. Translate every check into an outcome.
- **NeMo is not the identity authority, and this skill does not manage users.** People,
  agents, credentials, and group membership live in the IdP. For the reference path, an
  admin creates and manages them in the authentik screen; NeMo only holds the group->role
  mapping.
- **Two revoke levers, two scopes.** Removing the NeMo role mapping is immediate and
  affects that workspace. Removing someone from a group in the IdP affects everywhere that
  group grants access, and it applies to their next sign-in (existing tokens keep their
  claims until they expire). Say which one you used.
- **Human sign-in is a real browser flow.** `nemo auth login` uses the device flow and
  needs `--base-url` to persist the session. The person logs in themselves; you cannot do
  it for them. The reference IdP has device sign-in enabled out of the box.
- **The mapping is by group and deterministic.** A binding's internal name comes from
  `principal:workspace:role`, so re-binding the same group/role/workspace reuses the same
  name. Revoke is a soft delete that leaves that name reserved; the agent block hard-
  deletes by name first so the test is repeatable.
- **The `service:bootstrap` admin header is local-only.** It is the local bootstrap admin
  used to create the role binding during setup. Never use a `service:` principal header
  for a real customer machine, and the edge must strip inbound `X-NMP-Principal-*`
  headers. Customer agents and people authenticate via OIDC.
- **Reference path needs Docker; BYO doesn't.** Most NeMo skills don't need Docker. This
  one does for the reference IdP. Offer the BYO path if Docker isn't available.
- **Teardown is scoped.** This skill stops NeMo and removes the authentik reference only.
  Route to `nemo-teardown` to wipe platform data, the venv, or local agent files.
