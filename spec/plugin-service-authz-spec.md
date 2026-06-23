# Plugin Service Authz Spec

## Summary

This spec replaces the current split between `nemo.services` and `nemo.authz` for HTTP-facing plugin authorization.

Plugins will define authorization entirely through the `NemoService` surface using two concepts:

- permissions
- path rules

The design is intentionally narrow. It does not introduce a general policy DSL. It only covers the data required to describe service-owned HTTP authorization.

## Goals

- Remove `nemo.authz` as a separate plugin discovery/configuration surface.
- Make `nemo.services` the sole source of plugin HTTP auth policy.
- Allow plugin authors to define authz close to the routes they own.
- Make plugin-owned authz definitions type-safe at the service authoring layer.
- Preserve compatibility with generated/programmatic routers such as job route factories.
- Make a clean design break before release rather than carrying forward transitional APIs.

## Non-Goals

- Defining a general-purpose authorization language.
- Replacing core platform roles with plugin-specific roles.
- Defining plugin-defined roles.
- Supporting non-HTTP policy surfaces in this iteration.
- Solving every possible cross-service permission composition case.
- Defining how plugin-defined roles are surfaced in IAM, CLI, UI, or docs.

## Current Problems

Today plugin HTTP authz is split across two mechanisms:

- `nemo.services` defines routers and paths.
- `nemo.authz` or `NemoService.get_authz_contribution()` defines permissions and endpoint policy separately.

This creates several problems:

- Route definitions and authz definitions drift because they are authored separately.
- `get_authz_contribution()` must be a classmethod because service discovery loads classes, which is awkward and non-idiomatic.
- Plugin authors need to learn two registration/configuration paths for one HTTP service.
- Factory-generated routes need separate handwritten authz helpers instead of carrying their own auth metadata.

## Design Overview

HTTP plugin authz is defined entirely through `NemoService`.

Each plugin service will define:

- permission definitions
- path rules

Path rules may be declared directly with `@path_rule(...)` on route handlers or attached programmatically by route factories.

The platform will derive the service authz contribution by:

1. discovering `nemo.services`
2. instantiating each service
3. reading its routers
4. reading authz metadata attached to routes
5. reading optional service-level authz definitions
6. building a normalized authz model used by runtime bundle generation and static sync tooling

The normalized authz model described in this spec governs endpoint permissions and route rules. It does not replace the upstream identity extraction layer.

## Core Concepts

### Permissions

Permissions are the canonical, service-owned identifiers used in path rules.

Rules:

- Permission ids must be namespaced to the declared `permission_namespace`.
- Format remains dot-separated.
- A plugin service may only define permissions under its declared permission namespace.
- Permission ids must use `.` as the segment separator.

Examples:

- `agents.deployments.read`
- `agents.deployments.create`
- `customization.jobs.read`

Each permission definition includes:

- id
- description

Descriptions are required.

Minimal model:

```python
@dataclass(frozen=True)
class PermissionDef:
    id: str
    description: str
```

Permissions must be declared explicitly in `get_authz_definition()`.

Path rules may reference permissions, but they do not define them.

This means:

- raw string permission definitions in endpoint decorators are not supported
- every permission referenced by a path rule must already exist in the service authz definition
- every permission definition must include a description
- every permission referenced by the service must begin with the declared `permission_namespace`

### Path Rules

Path rules define which callers and required permissions apply to a concrete HTTP method and mounted path.

Rules:

- Path rules are owned by the service that mounts the route.
- Path rules may only reference permissions in the declared `permission_namespace`.
- Path rules are normally authored at the route level using `@path_rule(...)`.
- Generated routers may attach the same metadata programmatically.
- Every plugin-owned route must have one or more normalized path rules.
- A missing path rule is a validation error.
- No implicit caller or access behavior is inferred for routes with missing path rules.
- Anonymous access must always be explicit.
- Multiple path rules on the same endpoint are alternative allow rules.

Minimal model:

```python
@dataclass(frozen=True)
class PathRule:
    method: str
    path: str
    callers: list[CallerKind]
    permissions_required: list[str] = field(default_factory=list)
    scopes: list[str] | None = None
```

## Public Plugin API

### Route Decorator

Plugins define path rules primarily through a single decorator with explicit callers.

Initial decorator:

- `@path_rule(...)`

Examples:

```python
@router.get("/deployments/{name}")
@path_rule(
    callers=[CallerKind.PRINCIPAL],
    permissions_required=[AgentsPermission.DEPLOYMENTS_READ],
    scopes=["agents:read", "platform:read"],
)
async def get_deployment(...): ...
```

```python
@router.get("/deployments/{name}")
@path_rule(
    callers=[CallerKind.SERVICE_PRINCIPAL],
    permissions_required=[AgentsPermission.INTERNAL_DEPLOYMENTS_READ],
)
async def get_deployment(...): ...
```

```python
@router.get("/docs")
@path_rule(
    callers=[CallerKind.ANON],
)
async def docs(...): ...
```

Decorator behavior:

- attach normalized authz metadata to the route handler
- do not perform authorization directly
- support both hand-authored and factory-authored routes
- allow one or more rules per endpoint
- interpret multiple rules on a single endpoint as OR, not AND

Initial caller kinds:

- `ANON`
- `PRINCIPAL`
- `SERVICE_PRINCIPAL`

Proposed enum:

```python
class CallerKind(StrEnum):
    ANON = "anon"
    PRINCIPAL = "principal"
    SERVICE_PRINCIPAL = "service_principal"
```

Caller kind semantics:

- `ANON`
  - route is callable without authentication

- `PRINCIPAL`
  - route is intended for normal authenticated principal access
  - this corresponds to the current model's non-anonymous, non-`service:` callers

- `SERVICE_PRINCIPAL`
  - route is intended for principals whose id is prefixed with `service:`
  - this corresponds to the current model's service-principal convention
  - how that identity was authenticated is out of scope for the path rule model

Validation rules for decorator usage:

- `ANON` rules must not specify `permissions_required`
- `PRINCIPAL` and `SERVICE_PRINCIPAL` rules may specify empty `permissions_required`, preserving the current behavior for authenticated-but-permissionless endpoints
- any specified `permissions_required` must belong to the declared `permission_namespace`

Additional validation rules:

- every plugin-owned route must have at least one path rule
- attaching no path rule is invalid
- attaching no path rule must fail validation before merge/startup
- `ANON` must always be explicit and may not be inferred as a fallback
- each rule on an endpoint must be valid on its own
- the final rule set for an endpoint is evaluated as OR over the rules

Rule semantics:

- within one rule, `callers` are OR'ed
- within one rule, `permissions_required` are AND'ed
- across multiple rules on the same endpoint, rules are OR'ed

Scope semantics preserved in this iteration:

- scopes remain supported as endpoint rule fields in this iteration
- plugin-defined scopes are out of scope for this spec
- endpoint rule scopes are normalized NeMo platform scopes
- provider-native OAuth/OIDC scopes are not used directly in endpoint rules
- token-provided scopes and endpoint-required scopes must be treated as distinct concepts in code and docs
- normalized NeMo platform scopes must use `:` as the segment separator

### Service-Level Authz Definition

Each `NemoService` may define service-owned permissions.

Proposed shape:

```python
class NemoService(_NamedPlugin):
    ...

    def get_authz_definition(self) -> ServiceAuthzDefinition | None:
        return None
```

Minimal model:

```python
@dataclass
class ServiceAuthzDefinition:
    permission_namespace: str
    permissions: list[PermissionDef] = field(default_factory=list)
```

This model intentionally does not include endpoint/path data. Path rules come from routers.

`permission_namespace` is the explicit source of truth for permission-prefix validation.

Rules:

- `permission_namespace` must use `.` as its segment separator
- every permission id defined or referenced by the service must start with `<permission_namespace>.`
- `permission_namespace` is service-owned metadata and does not need to be identical to `NemoService.name`

This avoids ambiguity between URL/service naming and permission naming.

This namespace boundary must be enforced during bundle-time validation.

### Type-Safe Authoring

Plugin services should be able to define permissions using typed enums or typed constants.

Example:

```python
class AgentsPermission(StrEnum):
    DEPLOYMENTS_READ = "agents.deployments.read"
    DEPLOYMENTS_CREATE = "agents.deployments.create"
```

The `@path_rule(...)` decorator and authz definition helpers should accept these typed values directly.

Goals of type-safe authoring:

- avoid string typos
- avoid cross-service permission leakage inside service code
- make service-owned permissions easy to refactor

This type safety is local to the service authoring layer. Cross-plugin composition remains a runtime concern because plugins are discovered dynamically.

## Derived Platform Behavior

The platform derives normalized plugin authz from services as follows:

1. Discover `nemo.services`.
2. Instantiate each service once.
3. Read `get_authz_definition()`.
4. Read `get_routers()`.
5. For each mounted route:
   - compute the fully mounted path from service name, `RouterSpec.prefix`, and route path
   - read attached authz metadata
   - emit one or more normalized path rules
6. Validate the combined result.
7. Convert the normalized result into the existing runtime/static authz structures consumed by the auth service.

This derived result replaces the need for a separate `nemo.authz` plugin surface.

The PDP continues to receive request method, path, principal identity, and scopes as it does today. This spec changes how plugin-owned endpoint rules are authored and merged. It does not require replacing the current PDP structure.

The implementation must preserve the current core-role grant behavior for plugin-defined permissions when converting the derived result into the existing runtime/static authz structures.

Specifically:

- `.read` and `.list` permissions continue to be granted to `Viewer` and `Editor`
- other plugin-defined permissions continue to be granted to `Editor`

Redesigning that heuristic is explicitly out of scope for this spec and is handled by a separate follow-up spec.

## Validation Rules

The platform must validate plugin-owned authz before merge and bundle generation.

Required checks:

- `permission_namespace` is present on every `ServiceAuthzDefinition`.
- `permission_namespace` uses `.` as its segment separator.
- Every plugin-defined permission id starts with `<permission_namespace>.`.
- Every plugin-defined permission id uses `.` as its segment separator.
- Every path rule references only `<permission_namespace>.*` permissions in `permissions_required`.
- Every `permissions_required` entry exists in the service permission registry.
- Every plugin-defined permission includes a description.
- Every endpoint-required scope uses `:` as its segment separator.
- Every plugin-owned route has at least one path rule.
- No plugin-owned route is implicitly anonymous/public.

Bundle-time validation must fail if a plugin contributes malformed permission ids, undeclared permissions referenced by path rules, missing permission descriptions, or malformed normalized scopes.
Merge-time validation must also verify rule-set correctness, not just individual rule correctness.

Bundle-time validation must also enforce that a service cannot define or reference permissions outside its declared `permission_namespace`.

Additional merge-time checks:

- reject exact duplicate rules on the same endpoint
- reject semantically conflicting rules on the same endpoint
- reject semantically shadowed rules where one rule makes another meaningless
- reject ambiguous same-caller overlaps that cannot be explained as clear alternatives

Merge behavior:

- merging authz definitions is a validation boundary, not a best-effort concatenation step
- invalid or conflicting rules must fail merge
- plugin endpoints with no path rules must fail merge rather than receiving any implicit default behavior

## Factory-Generated Routes

This design must work for generated routers, not only handwritten endpoints.

Examples include:

- job route factories
- reusable CRUD/router builders
- helper functions that return `APIRouter`

Requirement:

- factories must be able to attach the same authz metadata that `@path_rule(...)` attaches

### Current State

The current plugin authz helpers already embed route-to-permission conventions for some generated routes.

Example: `authz_for_workspace_job_collection(...)` effectively hard-codes the standard job route policy shape:

- collection `POST` -> `<prefix>.create`
- collection `GET` -> `<prefix>.list`
- item `GET` -> `<prefix>.read`
- item `DELETE` -> `<prefix>.delete`

It also pairs those routes with the current scope convention:

- read routes -> `<api_area>:read`, `platform:read`
- write routes -> `<api_area>:write`, `platform:write`

So the platform already has factory-local authz conventions today, but they are embedded in helpers rather than expressed as part of a normalized route-metadata model.

### Desired Outcome

The desired end state is:

- plugin authors do not have to restate authz for generated routes outside the factory call
- factories do not hide authz behavior in a way that cannot be validated or overridden
- the final emitted route metadata is explicit and normalized before merge and bundle generation

### Concrete Examples

#### Example 1: Standard Job Collection Factory

Current customization-style usage looks roughly like:

```python
router = job_route_factory(
    service_name="customization",
    job_type="Customization",
    job_input=CustomizationJobInput,
    job_output=CustomizationJobOutput,
    input_to_output=transform_input_to_output,
    platform_job_config_compiler=platform_job_config_compiler,
    generate_job_name=generate_customization_id,
    route_options=[JobRouteOption.CORE],
)
```

In the model described by this spec:

- the plugin defines permissions explicitly in `get_authz_definition()`
- the factory provides the default route-to-permission template
- the factory emits normalized path rules for the generated `POST`, `GET`, item `GET`, and item `DELETE` routes

Conceptually:

```python
def get_authz_definition(self) -> ServiceAuthzDefinition:
    return ServiceAuthzDefinition(
        permission_namespace="customization.jobs",
        permissions=[
            PermissionDef("customization.jobs.create", "Create customization jobs"),
            PermissionDef("customization.jobs.list", "List customization jobs"),
            PermissionDef("customization.jobs.read", "Read customization jobs"),
            PermissionDef("customization.jobs.delete", "Delete customization jobs"),
        ],
    )
```

And the factory would internally emit rules equivalent to:

- collection `POST` -> `customization.jobs.create`
- collection `GET` -> `customization.jobs.list`
- item `GET` -> `customization.jobs.read`
- item `DELETE` -> `customization.jobs.delete`

#### Example 2: Rebasing A Generated Router

Some services generate the standard job routes and then rebase them onto a different collection path, as evaluator does for metric jobs.

Conceptually:

```python
_jobs_router = job_route_factory(
    service_name="evaluator-metrics",
    job_type="MetricEvaluation",
    job_input=MetricJob,
    platform_job_config_compiler=platform_job_config_compiler,
)

router.include_router(_metric_jobs_router, prefix="/v2/workspaces/{workspace}/metric-jobs")
```

In this case, the important requirement is that rebasing the route paths must not lose the attached authz metadata.

That means:

- the factory may emit metadata before rebasing
- the rebasing helper must preserve or restamp that metadata onto the final mounted routes
- bundle validation must operate on the final mounted paths, not the factory's temporary `/jobs` paths
- rebasing alone must not change permissions or other authz semantics

This matters because some rebasing patterns rebuild routes by creating new `APIRoute` objects.

If authz metadata is attached only to the original route object, rebuilding may drop that metadata unless the rebasing helper explicitly preserves or restamps it.

Validation must therefore inspect the final mounted route set, after any rebasing or remounting has occurred.

### Ownership Model

For factory-generated routes, authz ownership should be split clearly:

- the factory owns the route shape
  - which routes are generated
  - which HTTP methods exist
  - what authz template is applied by default

- the plugin owns the concrete policy inputs
  - permission definitions
  - permission prefixes or ids referenced by the factory
  - optional endpoint rule scopes
  - caller kinds
  - explicit overrides, where the factory allows them

- the factory emits the final path-rule metadata
  - generated endpoints must end up with the same normalized metadata shape as handwritten endpoints

This spec standardizes the required outcome, not a single shared factory API shape.

That means:

- factories may expose their authz inputs through factory-specific parameters
- the core plugin API does not require a universal factory authz interface in this iteration
- regardless of factory signature, the emitted route metadata and referenced permissions must satisfy the same validation rules as handwritten routes

### Validation Requirement

Bundle-time validation must operate on the final emitted rule set, regardless of whether the rules came from:

- handwritten decorators
- factory defaults
- plugin-supplied factory parameters
- explicit plugin overrides

In other words:

- factories may synthesize rules
- plugins may parameterize those rules
- but merge and bundle validation must only accept the final normalized route metadata
- any missing, conflicting, or malformed generated rules must fail validation before bundle generation

This may be implemented by:

- applying the same decorator internally, or
- attaching the normalized metadata directly to the generated endpoint callable/route object

This is important for routes like service-owned job collections, where authz should be derived from the same route factory that creates the endpoints.

## Compatibility

This design assumes the plugin authz surface has not been released yet and therefore does not need a backward-compatibility layer.

Requirements:

- Do not preserve `nemo.authz` as a supported plugin surface.
- Do not preserve `NemoService.get_authz_contribution()` as a supported API.
- Do not add fallback merge logic that supports both the old and new models indefinitely.

Implementation expectation:

- internal code may be updated in one pass to the new service-owned model
- route factories such as job helpers should emit the new path-rule metadata directly
- auth runtime and static sync tooling should consume only the new derived service authz model

## Decision

Adopt a service-owned authz model for plugin HTTP authorization with exactly two plugin-defined concepts:

- permissions
- path rules

Use a single `@path_rule(...)` decorator for path rules, with `callers` and optional `permissions_required`, allow multiple rules per endpoint as explicit OR alternatives, validate rule correctness at merge time, and remove the separate `nemo.authz` surface entirely as part of the initial implementation.
