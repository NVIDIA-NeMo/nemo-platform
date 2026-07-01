---
name: plugin-authz
description: Declares HTTP authorization on NeMo Platform plugin routes with @path_rule, AuthzScope, PermissionSet, and CallerKind. Use when adding or securing a plugin route, minting permission ids, choosing PRINCIPAL vs SERVICE_PRINCIPAL callers, fixing a hard_fail bundle build from an unruled route, or migrating off get_authz_contribution. Trigger keywords: authz, authorization, permission, path_rule, AuthzScope, PermissionSet, perm, CallerKind, SERVICE_PRINCIPAL, scope, hard_fail, on_invalid_plugin, unruled route, bundle build, get_authz_contribution.
---

# Plugin HTTP Authorization (path_rule / AuthzScope)

Authz is derived *entirely from the routes*. Each handler carries two orthogonal decorators — a `@path_rule` (who may call + what they must hold) and an `@AuthzScope.read`/`.write` (the OAuth scope gate). The platform reads them off the mounted routes to build the permission catalog, the per-endpoint bindings, and the OPA bundle. There is no separate permission list to keep in sync.

## THE RULE

Every plugin HTTP route MUST carry a `@path_rule` — directly, or via a route factory you passed `authz=` to. A route with no rule is a validation error: the offending routes are emitted as explicit **deny** markers (they override every allow, including the service `*` wildcard and the PlatformAdmin bypass), and under the default `on_invalid_plugin="hard_fail"` the auth service **refuses to build the OPA bundle** — the platform 502s rather than silently fencing the route.

If you add a route, you add a rule. If the platform starts 502-ing after you touch a plugin, suspect an unruled route first.

## Recipe — hand-written route

```python
from nemo_platform_plugin.authz import AuthzScope, CallerKind, PermissionSet, path_rule, perm

scope = AuthzScope("myplugin")                 # owns scopes myplugin:read / myplugin:write

class ItemPerms(PermissionSet, namespace="myplugin.items"):
    READ = perm("Read an item")                # id -> "myplugin.items.read"

@router.get("/v2/workspaces/{workspace}/items/{name}")
@scope.read                                    # OAuth scope gate
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[ItemPerms.READ])
async def get_item(workspace: str, name: str) -> Item: ...
```

**Decorator order:** `@router.<method>` is the OUTERMOST (top) decorator; `@scope.read` and `@path_rule` sit under it. Their order *relative to each other* does not matter — both only stamp attributes on the handler and return it unchanged (identity survives FastAPI's `include_router(prefix=...)` rebasing).

## `@path_rule` — callers + permissions

```python
@path_rule(callers=[CallerKind.PRINCIPAL], permissions=[ItemPerms.READ, ItemPerms.WRITE])
```

- `callers` are **OR**'d, `permissions` are **AND**'d.
- Stacking `@path_rule` on one handler adds **OR alternatives** (any satisfied rule allows access).
- `callers` is **required and non-empty**; `permissions` may be `[]` for an authenticated-but-permissionless route (e.g. `/healthz`, a blob `PUT`).
- Reference `PermissionSet` members, **never bare strings** — a string raises `TypeError` at import, so a permission typo can't reach the policy layer.

## Permission ids — `PermissionSet` + `perm()`

Id grammar is `<service>.<resource>.<action>`, joined from parts. The `<service>` (first segment) MUST equal `NemoService.name` — that namespace fence is enforced, or the whole plugin fails closed.

```python
class ItemPerms(PermissionSet, namespace="myplugin.items"):
    CREATE = perm("Create an item")                      # id -> "myplugin.items.create"
    STATUS_UPDATE = perm("Set observed status",
                         suffix="status.update")          # id -> "myplugin.items.status.update"
```

- Inside `PermissionSet(namespace="a.b")`, `perm("desc")` gives id `a.b.<member-name-lowercased>`.
- `perm("desc", suffix="configs.create")` mints a compound id `a.b.configs.create`.
- `PermissionSet.all()` returns every member (handy for `extra_permissions`).

## `@AuthzScope.read` / `.write` — the scope gate

A route carries **exactly one** OAuth scope, declared separately from `@path_rule`. `AuthzScope("agents")` owns `agents:read` / `agents:write` (each expands to `["<area>:<verb>", "platform:<verb>"]`). Re-stamping the same scope is idempotent; a *different* scope on the same handler is a `ValueError` at import.

Mint permissions off the same scope when the permission namespace nests deeper than the scope:

```python
AuthzScope("agents").child("deployments").permission("create", description="...")
# -> Permission id "agents.deployments.create"; the OAuth scope stays "agents"
```

Share one `AuthzScope` across a plugin's route modules (define it in a small `authz.py` and import it) so the scope and namespace live in one place.

## Caller kinds — PRINCIPAL vs SERVICE_PRINCIPAL

- `CallerKind.PRINCIPAL` — a normal authenticated user. The default.
- `CallerKind.SERVICE_PRINCIPAL` — a caller whose id is prefixed `service:` (e.g. a controller writing observed status).
- Caller-kind is a PDP subject attribute enforced in Rego. There is no `ANON` kind — genuinely public routes are core infrastructure, hardcoded as a PEP bypass.

The deployments controller-status `PUT` is the canonical service-principal route — only the controller (`service:...`) may write observed status:

```python
@router.put("/deployments/{name}/status", response_model=Deployment)
@scope.write
@path_rule(callers=[CallerKind.SERVICE_PRINCIPAL], permissions=[DeploymentPerms.STATUS_UPDATE])
async def update_deployment_status(
    workspace: str,
    name: str,
    body: UpdateDeploymentStatusRequest,
    _: None = Depends(require_service_principal),   # 403s a non-service caller in-handler
    entity_client: NemoEntitiesClient = Depends(get_entity_client),
) -> Deployment: ...
```

`DeploymentPerms.STATUS_UPDATE = perm("Update deployment observed status (controller)", suffix="status.update")` under `namespace="deployments.deployments"` → id `deployments.deployments.status.update`.

## Route factories — pass `authz=` or the routes are UNRULED

`add_job_routes` / `add_function_routes` stamp the rule for you, but the `authz=` kwarg **defaults to `None`** — omit it and every generated route is unruled (denied fail-closed at bundle time).

```python
from nemo_platform_plugin.jobs.routes import add_job_routes
from nemo_platform_plugin.functions.routes import add_function_routes

add_job_routes(MyJob, authz=AuthzScope("myplugin"))
add_function_routes(MyFn, authz=AuthzScope("myplugin"), permission_description="Invoke MyFn")
```

Invoking a function is a **write** action: the factory mints a PRINCIPAL permission `<namespace>.<function-name>` and stamps `@scope.write`. `permission_description` defaults to the function's own description and **requires `authz`** (supplying it alone is a `ValueError`).

## Escape hatches — permissions with no 1:1 route

Override on your `NemoService` for permissions that aren't attached to a route (checked in middleware, or granted to a role the heuristic misses):

```python
from nemo_platform_plugin.authz import Permission

def extra_permissions(self) -> list[Permission]: ...
def extra_role_permissions(self) -> dict[str, list[Permission]]: ...
```

**Default role-grant heuristic:** ids ending `.list` or `.read` → Viewer + Editor; everything else → Editor only. Use `extra_role_permissions` to reach a role the heuristic wouldn't — e.g. granting a Viewer an `.invoke` permission (its suffix isn't `read`). Grants are **unioned** with the defaults (never subtractive), each granted permission is also auto-registered in the catalog (no need to also list it in `extra_permissions`), and every permission must live in this service's own namespace or the whole plugin fails closed.

## Fail modes — `NMP_AUTH_ON_INVALID_PLUGIN`

The offending routes are *always* emitted as explicit denies; the auth-service config field `on_invalid_plugin` (env `NMP_AUTH_ON_INVALID_PLUGIN`, prefix `NMP_AUTH_`) only controls the blast radius:

| Value | Behaviour |
|---|---|
| `hard_fail` (default) | Refuse to build the OPA bundle — fail closed at the platform level (platform 502s). |
| `quarantine` | Deny the whole offending plugin, but keep the platform up. |
| `deny_route` | Deny only the bad routes. |

A deployment loading dynamically-discovered or third-party plugins CI never vetted can downgrade to `quarantine` / `deny_route` so one bad plugin can't wedge the platform.

## Verify

```bash
# From repo root, workspace installed. Reports 0 degraded plugins when every route is ruled:
uv run python services/core/auth/scripts/auth-tools.py sync-plugins --dry-run

make build-policy && make test-policy
```

> **Local dev:** `services/core/auth/.../assets/policy.wasm` is a gitignored build artifact. Run `make build-policy` after pulling authz/Rego changes, otherwise `test_embedded_pdp.py` fails against a stale copy (misleading `sprintf` / fence-fails-open errors).

## Migrating off `get_authz_contribution`

The old surface is gone: the `get_authz_contribution()` classmethod and the `nemo.authz` entry point were removed. To migrate a plugin:

1. Delete `get_authz_contribution()` and drop the `nemo.authz` entry point.
2. Move each permission id into a `PermissionSet` — **ids are preserved**, so existing role grants do not change.
3. Attach `@path_rule` plus `@scope.read` / `@scope.write` to every handler (or `authz=` on the route factory).

## See Also

- [`examples.md`](examples.md) — full copy-paste recipes (hand-written CRUD, service-principal status route, job/function factory wiring, escape hatches)
- [`../plugin-service/SKILL.md`](../plugin-service/SKILL.md) — building the `NemoService` and its routers
- [`../plugin-job/SKILL.md`](../plugin-job/SKILL.md) — `add_job_routes` and job wiring
- [`../plugin-function/SKILL.md`](../plugin-function/SKILL.md) — `add_function_routes` and function wiring
- [`../plugin-controller/SKILL.md`](../plugin-controller/SKILL.md) — the service-principal side that writes observed status
