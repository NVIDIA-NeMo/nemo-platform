# Plugin-Defined Scopes Spec

## Summary

This spec explores whether NeMo Platform should support plugin-defined scopes as a first-class concept.

This is intentionally separate from `plugin-service-authz-spec.md`.

That spec allows plugin endpoints to reference normalized platform scopes in path rules, but it does not define how plugins declare, validate, surface, or document scopes themselves. This document explores that missing scope model.

## Current State

Today, plugin-contributed endpoint authz can include `scopes`, but those scopes are just strings attached to endpoint rules.

Current behavior:

- plugin authz contributions may attach `scopes` to endpoint methods
- the PDP enforces those endpoint-required scopes when token-provided platform scopes are present
- platform scopes are recognized by the presence of `:` in the scope string
- standard OIDC scopes such as `openid`, `profile`, `email`, and `offline_access` are ignored for authorization

What does not currently exist:

- a plugin-defined scope registry
- a scope definition model with required metadata
- bundle-time validation beyond basic endpoint usage
- a first-class docs or discovery surface for plugin-contributed scopes

## Problem

Permissions are treated as a first-class platform concept with explicit definitions and descriptions.

Scopes are not.

That creates several problems:

- plugin authors can reference scope strings without defining them anywhere
- scopes may drift in spelling or naming conventions
- there is no canonical place to attach descriptions or documentation
- it is unclear whether a scope is platform-owned, plugin-owned, or provider-specific
- docs generation and discovery become inconsistent

## Goals

- Define whether plugin scopes should be first-class platform objects.
- Require a canonical declaration path if plugin-defined scopes are supported.
- Enforce scope naming conventions at bundle-validation time.
- Keep plugin endpoint rules able to reference normalized platform scopes.
- Separate provider-native scope handling from platform-defined scope handling.

## Non-Goals

- Redesigning the current optional scope-checking behavior in the PDP.
- Replacing permissions with scopes.
- Solving IdP-specific scope issuance or consent UX.
- Changing the current plugin-service authz implementation plan.

## Design Questions

This spec should answer at least these questions:

1. Should plugins be allowed to define new normalized platform scopes?
2. If yes, where are those scopes declared?
3. Should scope definitions require descriptions, like permissions do?
4. Should plugin-defined scopes be namespaced by service or API area?
5. Should plugin-defined scopes appear in docs, discovery APIs, and UI?
6. How should plugin-defined scopes relate to provider-native OAuth/OIDC scopes?

## Options

### Option 1: Keep Scopes As Endpoint-Only Strings

Plugins may continue to reference normalized scope strings in path rules, but there is no first-class scope definition model.

Pros:

- smallest change
- closest to current behavior
- no extra registry or docs work

Cons:

- weak validation
- no canonical descriptions
- scope drift remains easy

### Option 2: Add A Plugin Scope Registry

Plugins define scopes explicitly, similar to permissions.

Conceptual example:

```python
@dataclass(frozen=True)
class ScopeDef:
    id: str
    description: str
```

And:

```python
class NemoService(_NamedPlugin):
    ...

    def get_scope_definition(self) -> ServiceScopeDefinition | None:
        return None
```

Pros:

- explicit
- validates well
- supports docs and discovery

Cons:

- more machinery
- needs a clear relationship to permissions

### Option 3: Reuse The Existing Service Authz Definition Pattern

Plugin-defined scopes become part of the same service-level authz definition shape used for permissions.

Conceptual example:

```python
@dataclass
class ServiceAuthzDefinition:
    permissions: list[PermissionDef] = field(default_factory=list)
    scopes: list[ScopeDef] = field(default_factory=list)
```

Pros:

- one service-owned definition surface
- consistent with permission definitions
- keeps scope ownership close to other auth metadata

Cons:

- makes the authz definition surface broader
- requires the main authz model to grow later

## Recommendation

Recommend Option 3 if plugin-defined scopes are adopted later.

If scopes become first-class, they should follow the same general pattern as permissions:

- explicit service-level declaration
- required descriptions
- bundle-time validation
- normalized naming conventions

Endpoint rules should reference previously defined scopes rather than inventing raw scope strings inline.

## Validation Expectations

If plugin-defined scopes are introduced later, bundle-time validation should enforce at least:

- normalized platform scopes use `:` as the segment separator
- provider-native scopes are not used directly in plugin endpoint rules
- every referenced plugin-defined scope exists in the service scope registry
- every plugin-defined scope includes a description
- duplicate or conflicting scope definitions fail validation

## Relationship To Other Specs

- `plugin-service-authz-spec.md`
  - keeps scopes as normalized strings referenced by path rules
  - does not define plugin-defined scopes as a first-class model

- `oidc-scope-and-claim-mapping-spec.md`
  - covers mapping provider-native OAuth/OIDC scopes into normalized NeMo platform scopes
  - should remain separate from plugin-owned scope definition

- `core-role-default-grants-spec.md`
  - permissions and roles remain a separate follow-up track from scope definition
