# Core Role Default Grants Spec

## Summary

This spec explores two closely related follow-up questions for plugin-defined authorization data:

- how NeMo Platform should replace the current heuristic that automatically grants plugin-defined permissions to core roles based on permission suffix
- how plugin-defined roles should be surfaced in IAM, CLI, UI, and docs
- whether plugin-defined roles should remain global or become service-scoped in a future design

This is intentionally separate from `plugin-service-authz-spec.md`.

The plugin service authz spec preserves current behavior and keeps role surfacing out of scope. This document explores better long-term alternatives.

## Context

This follow-up work needs to be understood in the context of the current NeMo Platform auth model.

### Current Auth Flow

Today the platform separates identity, scopes, roles, and permissions.

1. An OAuth/OIDC provider authenticates the caller.
2. The platform extracts a NeMo principal from the request.
   - principal id
   - principal email
   - principal groups
3. The auth client sends the request method, path, principal, and token scopes to the Policy Decision Point (PDP).
4. The PDP evaluates:
   - endpoint permissions from `authz.endpoints`
   - endpoint scopes from `authz.endpoints`
   - role-derived permissions for the principal
5. The PDP returns allow/deny.

### Where Permissions Come From

OAuth/OIDC does not directly grant NeMo Platform permissions.

Instead:

- OAuth/OIDC provides identity and optionally groups/scopes.
- NeMo Platform binds that identity to roles.
- Roles grant permissions.

Role bindings are stored as platform data and loaded into the auth bundle at runtime.

This means:

- users do not receive platform permissions directly from the OAuth provider
- users receive platform permissions indirectly through NeMo role bindings
- those role bindings may target a principal id, email, or group

In other words, directory attributes can be inputs to authorization, but the actual permission grant is owned by NeMo Platform.

### Current Scope Behavior

The current system does use scopes, but only as an optional coarse-grained gate layered on top of the main permission model.

To avoid ambiguity:

- token-provided scopes: scopes extracted from OAuth/OIDC claims or equivalent request auth context
- endpoint-required scopes: scopes declared on a NeMo endpoint rule

Current PDP behavior is:

- if token-provided platform scopes are absent, the scope gate is skipped
- if token-provided platform scopes are present, they must satisfy the endpoint-required scopes
- if endpoint-required scopes are empty, the scope gate passes regardless of token-provided scopes

### Current State Of Plugin-Defined Roles

The backend can already store and evaluate arbitrary role names.

However, plugin-defined roles are not currently supported as a first-class end-to-end product feature.

Today:

- backend authz data can contain arbitrary global role names
- role bindings can target arbitrary role strings
- Studio workspace-member flows only understand the core workspace roles
- CLI role arguments are mostly free-form, but the surrounding UX and docs still center on the core roles

So this follow-up spec is not only about policy shape. It is also about whether plugin-defined roles should become a real surfaced platform concept.

## Current Behavior

Today the platform automatically grants plugin-defined permissions to core roles using a suffix heuristic.

Current heuristic:

- permissions ending in `.read` or `.list` are granted to `Viewer` and `Editor`
- all other permissions are granted to `Editor`

This behavior exists today in the auth merge logic and is preserved by `plugin-service-authz-spec.md`.

## Problem

The current heuristic is simple, but it is also brittle and semantically weak.

Problems:

- permission suffix does not always reflect real sensitivity
- different services may use different naming patterns
- some permissions should not be granted to core roles automatically at all
- plugin authors may not realize they are implicitly granting access to core roles
- security review becomes harder because grants are inferred rather than declared

Examples:

- a permission ending in `.read` may still expose sensitive operational state
- a permission ending in `.exec` might not belong in `Editor`, but the heuristic would grant it there
- different plugin teams may invent new permission suffixes that do not fit the model

## Goals

- Replace suffix-based inference with a more explicit and reviewable model.
- Preserve a simple authoring experience for common services.
- Allow services to declare core-role grants intentionally.
- Avoid surprising implicit privilege expansion.

## Non-Goals

- Redesigning the plugin path-rule model.
- Replacing service-scoped roles.
- Changing how role bindings are stored.
- Changing the initial plugin authz implementation plan.

## Design Principles

### Principle 1: Core-Role Grants Should Be Explicit

If a service wants a permission to be granted to `Viewer`, `Editor`, or `Admin`, that should be visible in the service-owned authz definition.

### Principle 2: Safe Defaults Matter

It should be hard to accidentally expose a new permission broadly through inference.

### Principle 3: Common Cases Should Stay Ergonomic

Services will often want straightforward defaults for read/list vs mutating operations. The replacement should not force every service to write large repetitive grant maps unless necessary.

### Principle 4: Role Surfacing Should Follow an Explicit Product Model

If plugin-defined roles appear in IAM, CLI, UI, or docs, that exposure should come from an intentional platform model rather than falling out of backend permissiveness.

### Principle 5: Role Scope Should Be an Explicit Policy Choice

The platform should make an explicit decision about whether plugin-defined roles remain global or become service-scoped later. That choice should not be implied accidentally by naming conventions or backend permissiveness alone.

## Additional Problems: Role Surfacing and Role Scope

The current backend can already store and evaluate arbitrary role names, but the user-facing surfaces are still strongly oriented around the platform core roles.

Examples:

- workspace member flows assume `Viewer`, `Editor`, and `Admin`
- role-selection UX uses hard-coded core-role labels and descriptions
- documentation is written around the core role hierarchy

So there are really two separate follow-up questions:

- how core roles should receive plugin-defined permissions by default
- how plugin-defined roles should become visible and manageable across product surfaces
- whether plugin-defined roles should remain global or become service-scoped

These questions are related because both determine what role model administrators actually see and use.

## Role Scope Options

### Option 1: Keep Plugin-Defined Roles Global

Pros:

- preserves current backend behavior
- simplest migration path
- no additional namespace or validation rules

Cons:

- weaker isolation between plugin-defined role sets
- role names from different plugins may collide semantically
- harder to reason about ownership boundaries later

### Option 2: Require Service-Scoped Role Names and Grants

Examples:

- `agents.Reviewer`
- `customization.Approver`

Pros:

- clearer ownership
- easier to validate role-to-permission boundaries
- reduces accidental cross-service privilege expansion

Cons:

- changes current behavior
- adds validation and UX complexity
- may be unnecessary for the first implementation

## Role Surfacing Options

### Option A: Surface Plugin-Defined Roles Immediately Everywhere

Plugin-defined roles would appear in IAM, CLI, UI, and docs as soon as they exist in the normalized authz model.

Pros:

- consistent with backend behavior
- no hidden role model
- administrators can use plugin-defined roles directly

Cons:

- requires a role catalog and metadata model
- role-management UX becomes more complex immediately
- documentation and workspace-member flows need redesign

### Option B: Keep Plugin-Defined Roles Backend-Only Initially

Plugin-defined roles would participate in authorization but would not immediately be surfaced in all user-facing management flows.

Pros:

- smaller initial product-surface change
- allows the authz redesign to ship without redesigning role UX

Cons:

- creates a gap between backend capability and visible platform behavior
- makes plugin-defined roles harder to adopt intentionally

### Option C: Surface Plugin-Defined Roles Through an Explicit Role Catalog

Introduce a dedicated role catalog model and API that describes:

- role name
- description
- owning service
- scope
- whether the role is intended for user-facing assignment

Then let IAM, CLI, UI, and docs consume that model explicitly.

Pros:

- clean long-term structure
- avoids hard-coded core-role assumptions
- separates role evaluation from role presentation

Cons:

- requires additional platform work
- larger change than simply preserving current backend behavior

## Options

### Option 1: Keep the Current Heuristic

Pros:

- no extra authoring burden
- preserves current behavior exactly

Cons:

- remains implicit and brittle
- hard to review
- poor fit for security-sensitive services

### Option 2: Explicit Core-Role Grants Per Permission

Each permission definition declares which core roles receive it.

Conceptual example:

```python
PermissionDef(
    id="agents.deployments.read",
    description="Read agent deployments",
    core_roles=["Viewer", "Editor"],
)
```

Pros:

- explicit
- reviewable
- predictable

Cons:

- more verbose
- repetitive for services with many standard CRUD permissions

### Option 3: Service-Level Default Grant Policy With Explicit Overrides

Each service declares a default policy for core-role grants, and individual permissions may override it.

Conceptual example:

```python
CoreRoleGrantPolicy(
    read_like_roles=["Viewer", "Editor"],
    write_like_roles=["Editor"],
)
```

With explicit override:

```python
PermissionDef(
    id="agents.internal.read",
    description="Read internal agent state",
    core_roles=[],
)
```

Pros:

- keeps authoring ergonomic
- allows service-level consistency
- allows sensitive permissions to opt out

Cons:

- still partly inferential
- requires defining what counts as "read-like" or "write-like"

### Option 4: No Automatic Core-Role Grants

Plugin-defined permissions never go to core roles unless explicitly declared.

Pros:

- safest
- simplest to reason about
- no hidden behavior

Cons:

- more authoring overhead
- makes simple services more verbose

## Recommendation

For core-role default grants, recommend Option 3 as the likely best long-term balance:

- remove the global suffix heuristic
- allow each service to declare an explicit core-role default grant policy
- allow each permission to override that default

For plugin-role surfacing, recommend Option C:

- introduce an explicit role catalog model
- use that model to decide what appears in IAM, CLI, UI, and docs
- avoid treating backend role permissiveness as sufficient product-surface design

This keeps common cases simple while making policy ownership and product exposure much clearer.

For role scope, preserve the current global-role behavior in the near term and treat service-scoping as optional future work to be evaluated deliberately rather than introduced implicitly.

## Relationship To Plugin Service Authz

This spec is downstream of `plugin-service-authz-spec.md`.

That spec should preserve current behavior and avoid changing the existing core-role grant semantics during the decorator/path-rule work.

If this spec is adopted later, it should be implemented as a focused follow-up change to:

- core-role default grant behavior
- plugin-role surfacing and management
- plugin-role scope rules

rather than bundled into the initial plugin authz redesign.
