# OIDC Scope And Claim Mapping Spec

## Summary

This spec defines a normalization and mapping layer between upstream OAuth/OIDC provider claims and the NeMo Platform authorization model.

It is intentionally separate from `plugin-service-authz-spec.md`.

The plugin service authz spec covers:

- permissions
- service-scoped roles
- path rules

This spec covers:

- how OAuth/OIDC claims become a NeMo principal
- how provider-native scopes become NeMo-understood scopes
- whether and how external claims should influence NeMo roles

## Problem

Different OAuth/OIDC providers emit different claims and scope formats.

Examples:

- `openid profile email`
- `api://foo/read`
- `resource.read`
- provider-specific group claims
- provider-specific subject formats

The current NeMo auth model expects:

- a principal id
- optional principal email
- optional principal groups
- optional platform-understood scopes such as `models:read`

Without normalization, plugin and platform authz policy becomes tightly coupled to whichever provider a deployment uses.

## Goals

- Normalize provider-native identity claims into a NeMo principal model.
- Normalize provider-native scopes into NeMo-understood scopes before PDP evaluation.
- Preserve the current separation between:
  - OAuth/OIDC identity
  - NeMo role bindings
  - NeMo endpoint permissions
- Keep the plugin endpoint model provider-independent.

## Non-Goals

- Replacing NeMo role bindings with OAuth scopes.
- Defining plugin-owned path rules.
- Redesigning the PDP permission model.

## Current System

Today the platform:

- extracts principal id/email/groups
- extracts token scopes
- sends both to the PDP

Role bindings are loaded from the entity store and merged into the authorization data.

Important current behavior:

- there is no built-in facility that maps OIDC scopes directly to NeMo roles
- there is no built-in facility that maps provider-native scopes directly to NeMo permissions
- roles come from NeMo role bindings, not from OAuth scopes

This means:

- OAuth/OIDC provides identity and token metadata
- NeMo owns the authorization grants

## Design Principles

### Principle 1: Identity and Authorization Stay Separate

The mapping layer may normalize:

- subject
- email
- groups
- scopes

But it must not collapse the platform permission model into provider-native claims.

NeMo permissions should continue to come from NeMo role bindings and role definitions.

### Principle 2: Endpoint Policy Must Be Provider-Independent

Plugin services and platform services should not encode provider-native scopes or claims in endpoint policy.

Endpoint rules should only reference:

- NeMo permissions
- optionally NeMo-normalized scopes

### Principle 3: Mapping Must Be Deployment-Configurable

Different deployments may use different providers and different claim conventions.

The normalization layer should therefore be deployment-configurable rather than hardcoded into plugin/service definitions.

## Scope Mapping

### Input

Provider-native token scopes, for example:

- `openid`
- `profile`
- `api://foo/read`
- `resource.read`

### Output

NeMo-understood scopes, for example:

- `models:read`
- `platform:write`

### Proposed Behavior

Before PDP evaluation:

1. extract raw token scopes
2. apply configured scope mapping rules
3. produce normalized NeMo scopes
4. pass normalized scopes to the Policy Decision Point (PDP)

The PDP should not need to know which upstream provider produced the token.

### Mapping Shape

At a minimum, the mapping layer should support:

- exact scope mapping
- dropping irrelevant scopes
- passing through already-normalized NeMo scopes unchanged

Conceptual example:

```yaml
scope_mapping:
  exact:
    "api://foo/models.read": "models:read"
    "api://foo/models.write": "models:write"
    "api://foo/platform.admin": "platform:write"
  passthrough_nemo_scopes: true
  ignore:
    - "openid"
    - "profile"
    - "email"
    - "offline_access"
```

## Claim Mapping

The mapping layer should also normalize identity claims into the NeMo principal model.

Possible sources:

- `sub`
- `email`
- `groups`
- provider-specific custom claims

Conceptual example:

```yaml
claim_mapping:
  principal_id: "sub"
  principal_email: "email"
  principal_groups: "groups"
```

This allows providers with different claim names to be normalized into the same internal principal structure.

## Roles

### Current Recommendation

Do not map OIDC scopes directly to NeMo roles in the first iteration.

Reason:

- it mixes identity-provider policy with platform authorization state
- it makes roles provider-dependent
- it bypasses the existing NeMo role binding model

Instead:

- normalize identity claims
- normalize scopes
- keep roles granted by NeMo role bindings

### Possible Future Extension

If needed later, the platform could support external-claim-driven role projection as a separate feature.

Examples:

- map a directory group to a NeMo role
- map a provider-specific claim to a NeMo role

But this should be modeled explicitly as external-role projection, not as the default meaning of scopes.

## Options

### Option 1: Normalize Scopes Only

- map provider scopes to NeMo scopes
- keep roles entirely in NeMo

Pros:

- minimal change
- stays close to the current system
- keeps permission grants under platform control

Cons:

- still requires separate role binding administration

### Option 2: Normalize Scopes and Claims

- map provider scopes to NeMo scopes
- map provider claims to principal id/email/groups
- keep roles entirely in NeMo

Pros:

- cleaner multi-provider support
- keeps endpoint policy provider-independent
- still preserves current role-binding model

Cons:

- slightly larger implementation surface than scope-only mapping

### Option 3: Map External Claims to Roles

- map scopes or claims directly to NeMo roles

Pros:

- can reduce manual role-binding administration in some deployments

Cons:

- more invasive change
- blurs ownership of authorization policy
- harder to reason about and audit

## Recommendation

Recommend Option 2:

- normalize provider claims into the NeMo principal model
- normalize provider-native scopes into NeMo scopes
- keep NeMo roles and permissions granted through NeMo role bindings

This minimizes change to the current authorization model while making the platform much easier to integrate with different OAuth/OIDC providers.

## Relationship To Plugin Service Authz

This mapping layer sits before plugin endpoint authorization.

Order of operations:

1. provider authenticates caller
2. mapping layer normalizes claims and scopes
3. platform constructs NeMo principal
4. PDP evaluates endpoint permissions/scopes/roles
5. plugin path rules are checked using normalized NeMo auth context

Plugin path rules should not contain provider-specific logic.
