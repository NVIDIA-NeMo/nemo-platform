# Permissionless Authenticated Routes Spec

## Summary

This spec explores whether NeMo Platform should continue to allow authenticated routes that require no explicit platform permission.

This is intentionally separate from `plugin-service-authz-spec.md`.

The plugin service authz spec preserves the current behavior. This document questions whether that behavior should continue long-term.

## Current Behavior

Today the platform allows endpoints that are:

- authenticated
- permissionless

In practice this means an endpoint may be configured with:

- `permissions: []`

and, assuming the caller is authenticated, the route is allowed.

This behavior exists today and is preserved by `plugin-service-authz-spec.md`.

## Problem

Permissionless authenticated routes are convenient, but they weaken the clarity of the authorization model.

Problems:

- they make "authenticated" and "authorized" easier to conflate
- they create endpoints that are broad by default for all authenticated callers
- they make it harder to audit access expectations
- they encourage endpoints whose security semantics are underspecified

## Goals

- Determine whether permissionless authenticated routes should remain a supported pattern.
- Improve clarity and auditability of protected endpoint behavior.
- Preserve an ergonomic path for simple authenticated-only endpoints if needed.

## Non-Goals

- Redesigning plugin path-rule decorators.
- Changing the current behavior immediately.

## Options

### Option 1: Preserve Current Behavior

Keep allowing `USER` and `WORKLOAD` rules with empty `permissions_required`.

Pros:

- no behavioral change
- easy for simple authenticated-only endpoints
- closest to the current system

Cons:

- weaker security model
- less explicit review surface

### Option 2: Require Explicit Permissions For All Non-Anonymous Routes

Require every `USER` or `WORKLOAD` rule to name at least one permission.

Pros:

- strongest model
- easiest to audit
- every protected route is governed by a platform permission

Cons:

- more authoring overhead
- requires inventing permissions for lightweight endpoints

### Option 3: Preserve The Pattern, But Make It Explicit

Allow permissionless authenticated routes only through a distinct explicit marker.

Examples:

- `authenticated_only=True`
- `authorization_mode="authenticated_only"`

Pros:

- clearer than empty `permissions_required`
- keeps convenience for rare cases

Cons:

- adds another concept to the rule model

## Recommendation

Do not change current behavior as part of the first plugin authz redesign.

Instead:

- preserve the existing behavior in `plugin-service-authz-spec.md`
- revisit this separately after the decorator/path-rule model lands

Long-term, Option 2 or Option 3 is likely preferable to the implicit empty-permissions pattern.

## Relationship To Plugin Service Authz

`plugin-service-authz-spec.md` should preserve the current behavior for compatibility with the existing platform authorization model.

If the platform later decides to tighten or reformulate permissionless authenticated routes, that should happen as follow-up work under this spec rather than being bundled into the initial plugin authz implementation.
