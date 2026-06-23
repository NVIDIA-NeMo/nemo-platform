# Unify plugin HTTP authz under `NemoService` with explicit permission definitions and route path rules

## Description

Implement the new plugin HTTP authorization model described in `spec/plugin-service-authz-spec.md`.

Today plugin HTTP authz is split between `nemo.services` and `nemo.authz` / `get_authz_contribution()`. This work should remove that split and make `NemoService` the sole source of plugin HTTP auth policy.

## Scope

- Add service-owned authz definition support on `NemoService`
- Require plugin permissions to be declared explicitly, with required descriptions
- Add route-level path rule metadata via `@path_rule(...)` or equivalent programmatic stamping for generated routers
- Derive normalized plugin authz from:
  - `get_authz_definition()`
  - mounted routers / emitted route metadata
- Preserve current core-role grant behavior when converting derived plugin permissions into runtime/static authz
- Support factory-generated routes, including rebased routers
- Validate final emitted plugin authz before merge/bundle generation

## Key Requirements

- `nemo.authz` is removed as a supported plugin surface
- `NemoService.get_authz_contribution()` is removed as a supported API
- Permissions must be declared in `get_authz_definition()`
- Path rules may reference permissions but may not define them
- Every permission must include:
  - id
  - description
- Every service authz definition must declare `permission_namespace`
- Bundle-time validation must fail if a service:
  - defines permissions outside its `permission_namespace`
  - references undeclared permissions
  - emits malformed permission ids
  - emits malformed normalized scopes
- Every plugin-owned route must have at least one final path rule
- Validation must run against the final mounted route set, after any factory generation / rebasing
- Rebasing generated routers must preserve authz metadata and must not change permissions or authz semantics

## Caller Model

- `ANON`
- `PRINCIPAL`
- `SERVICE_PRINCIPAL`

## Out Of Scope

- Plugin-defined roles
- IAM/UI/CLI role surfacing
- Redesign of core-role default grant heuristics
- Plugin-defined scopes as a first-class model
- OIDC scope/claim mapping redesign

## Acceptance Criteria

- Plugin HTTP authz is derived only from `NemoService`
- Existing plugin permission behavior remains functional after migration
- Generated/rebased routes produce correct final path rules
- Bundle/merge validation fails closed on missing or invalid plugin authz metadata
- No plugin-owned route becomes implicitly public due to missing metadata
