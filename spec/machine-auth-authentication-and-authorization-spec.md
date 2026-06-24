# Machine Auth Authentication And Authorization Spec

## Summary

This spec defines a first-class machine-to-machine authentication and authorization model for NeMo Platform.

Today NeMo Platform has two practical auth paths:

- human callers authenticate through OAuth/OIDC Bearer tokens
- internal callers often identify themselves through trusted `X-NMP-Principal-*` headers using `service:<name>` principal ids

That leaves a gap for non-human callers that need real authentication without going through an interactive OAuth flow.

This spec fills that gap by introducing machine authentication as a separate platform capability with its own identity verification path, while preserving the existing NeMo authorization model.

The first recommended mechanism is Kubernetes service account JWT authentication, including k3s, because it matches the platform's deployment shape and avoids inventing a NeMo-specific secret distribution scheme.

## Problem

The current platform is OAuth-centric at the external authentication layer, but not all callers are humans or human-operated CLIs.

Examples:

- NeMo platform services calling other NeMo platform services
- controllers, jobs, and workers running inside the cluster
- automation outside the browser and outside the CLI device flow
- infrastructure-adjacent workloads that need a narrow machine identity

The current service-principal model is not enough for this.

Current behavior is closer to "trusted transport plus trusted headers" than true machine authentication:

- `Principal.is_privileged` is inferred from `principal.id.startswith("service:")`
- outbound SDK helpers synthesize `X-NMP-Principal-Id: service:<name>`
- middleware accepts `X-NMP-Principal-*` headers as identity input
- policy defaults service principals to the `ServiceSystem` role with wildcard `*` permissions

This creates several problems:

- machine identity is not cryptographically verified by the platform
- the boundary between trusted internal traffic and authenticated machine callers is unclear
- all service principals are effectively equivalent today
- service-to-service authorization is much broader than it needs to be
- external non-OAuth automation has no first-class authentication path

## Goals

- Add a first-class authentication path for machine callers that does not require interactive OAuth.
- Preserve the separation between authentication, principal normalization, and NeMo-owned authorization.
- Replace implicit trust in `service:` header conventions with verifiable machine identity.
- Support Kubernetes-native workloads, including k3s, as the first deployment target.
- Allow route policy to distinguish user principals from machine principals without hardcoding a specific transport.
- Create a migration path away from broad wildcard access for all service principals.

## Non-Goals

- Replacing human OAuth/OIDC authentication for browsers, CLI users, or SDK users.
- Defining a full general-purpose secret-management system for every non-Kubernetes environment.
- Introducing provider-native OAuth scopes into endpoint policy.
- Solving mesh mTLS identity, SPIFFE, and probe identity in the first iteration.
- Redesigning all plugin path-rule surfaces in this spec.

## Current State

### Human Authentication

Human auth is first-class today.

- the platform exposes `/apis/auth/discovery` for CLI/SDK OIDC discovery
- middleware validates Bearer JWTs against configured OIDC settings
- token claims are normalized into a NeMo principal
- PDP evaluation uses:
  - principal id
  - principal email
  - principal groups
  - optional token scopes

This path is documented and productized.

### Machine Authentication

Machine auth is not first-class today.

What exists instead:

- header-based principal propagation
- `service:<name>` ids
- on-behalf-of forwarding
- policy defaults that treat service principals as highly privileged

This is useful for internal plumbing, but it is not a full authentication design.

### Authorization

The core authorization model should remain intact:

- authentication establishes caller identity
- NeMo normalizes that identity into a principal
- NeMo role bindings and endpoint policy determine authorization

This is consistent with the existing OIDC scope/claim mapping direction and should remain true for machine auth.

## Design Principles

### Principle 1: Machine Auth Is Not Human OAuth

Machine callers should not be forced through browser login, device flow, or refresh-token lifecycle just to call internal APIs.

### Principle 2: Verified Identity Before Elevated Authorization

The platform must verify how a machine caller proved its identity before accepting a privileged `service:`-style principal.

### Principle 3: Authorization Stays In NeMo

Upstream machine credentials identify the workload. They do not directly grant NeMo permissions.

NeMo still owns:

- principal normalization
- role binding
- endpoint permission checks
- service-level authorization policy

### Principle 4: Prefer Platform-Native Identity Over Shared Secrets

For in-cluster machine auth, Kubernetes service account identity is preferable to static API keys because it is:

- already present in the runtime
- audience-bound
- rotatable by the platform
- less operationally brittle than hand-managed shared secrets

### Principle 5: Narrow Machine Identities

`service:evaluator` and `service:guardrails` should not automatically mean the same thing.

Machine identities should be individually attributable and authorizable.

## Requirements

### Requirement 1: Multiple Principal Kinds

The platform should recognize at least these normalized principal classes:

- user principal
- machine principal
- delegated machine principal acting on behalf of a user principal

The existing `service:` naming convention may remain as a principal-id format, but it must no longer be the authentication mechanism.

### Requirement 2: Credential-Type-Aware Authentication

Middleware must distinguish at least:

- human OIDC Bearer token
- machine Bearer token
- trusted propagated principal headers from an already-authenticated internal hop

These are different authentication modes and should not be conflated.

### Requirement 3: Machine Identity Projection

Verified machine credentials must normalize into a stable NeMo principal id and optional machine attributes.

Examples:

- `service:auth`
- `service:evaluator`
- `service:workspace-controller`

Optional attributes may include:

- Kubernetes namespace
- Kubernetes service account name
- Kubernetes cluster issuer
- workload audience

### Requirement 4: Least-Privilege Authorization

The platform must support explicit authorization grants for machine principals instead of relying on universal wildcard service access.

### Requirement 5: Delegation Must Stay Explicit

If a machine acts on behalf of a user, that must remain explicit through the existing delegated-principal semantics.

Machine auth alone must not silently imply user identity.

## Options

### Option 1: Kubernetes Service Account JWT Authentication

Machine callers present a projected Kubernetes service account token as `Authorization: Bearer <jwt>`.

The platform validates the token as a machine credential and maps it to a NeMo machine principal.

Validation approaches:

- local JWT validation against a configured Kubernetes service-account issuer and JWKS
- Kubernetes TokenReview-based validation
- a deployment-selectable validator abstraction that can support either mode

Additional constraints:

- require expected audience such as `nemo-platform`
- require expected issuer
- require claim extraction for namespace and service account identity

Pros:

- fits Kubernetes and k3s deployment environments
- avoids distributing NeMo-specific long-lived shared secrets
- gives each workload a native identity
- supports rotation and audience scoping

Cons:

- Kubernetes-specific in the first iteration
- needs careful validator configuration across distributions
- external non-Kubernetes automation still needs a separate story later

### Option 2: Static NeMo API Keys

Machine callers authenticate with a platform-issued API key.

Pros:

- simple mental model
- works outside Kubernetes
- no dependency on Kubernetes identity

Cons:

- shared-secret lifecycle is harder
- rotation, storage, and leakage risks are worse
- weaker provenance than workload identity
- easy to overuse as a generic escape hatch

### Option 3: mTLS / SPIFFE Workload Identity

Machine callers authenticate through service mesh identity or mutual TLS and the platform maps that identity into a machine principal.

Pros:

- strong workload identity
- good long-term story for service meshes

Cons:

- much larger deployment dependency surface
- not aligned with current platform implementation shape
- harder to make consistent across environments in the first iteration

## Recommendation

Adopt Option 1 as the first-class machine-auth mechanism:

- Kubernetes service account JWT authentication for machine callers
- explicit normalization into NeMo machine principals
- explicit NeMo authorization grants for those principals

Do not start with static API keys as the main model.

API keys may be worth a later follow-up for external automation, but they should not be the foundation for in-cluster platform auth.

## Proposed Design

## Authentication Model

Add a new machine-auth configuration block under `auth`.

Conceptual shape:

```yaml
auth:
  enabled: true
  oidc:
    enabled: true
    ...
  machine_auth:
    enabled: true
    default_audience: "nemo-platform"
    providers:
      - type: kubernetes_service_account
        issuer: "https://kubernetes.default.svc"
        audiences:
          - "nemo-platform"
        principal_template: "service:{service_account_name}"
        namespace_claim: "kubernetes.io/serviceaccount/namespace"
        service_account_name_claim: "kubernetes.io/serviceaccount/service-account.name"
```

The final config shape may differ, but it needs these concepts:

- machine auth enabled switch
- one or more machine identity providers
- issuer/audience validation
- claim mapping into normalized principal identity

## Principal Normalization

Introduce an explicit machine-principal normalization path.

Conceptual output:

```python
Principal(
    id="service:evaluator",
    email=None,
    groups=[],
)
```

But machine-specific metadata should also be available to authorization and logging, for example through an attached auth context:

- principal kind: `machine`
- provider type: `kubernetes_service_account`
- kubernetes namespace
- kubernetes service account name
- token issuer

This metadata should not force a redesign of the public `Principal` model in the first iteration if a side-channel auth context is simpler.

## Middleware Behavior

Update middleware authentication order conceptually as follows:

1. health and public bypasses
2. trusted internal principal propagation path
3. Bearer token path
   - try human OIDC validator
   - try machine-auth validator
   - reject if neither succeeds
4. auth-disabled behavior
5. anonymous/PDP path where allowed

Important rule:

- machine Bearer tokens must not be treated as human OIDC tokens
- trusted propagated `X-NMP-Principal-*` headers should only be accepted from already-authenticated internal hops, not as a substitute for first-hop machine authentication

## Header Propagation

The current principal propagation headers are still useful for downstream identity forwarding after the first hop authenticates.

That means:

- first hop into the platform may authenticate with a machine token
- platform normalizes that into a machine principal
- downstream internal requests may propagate normalized principal headers

But the spec should tighten trust boundaries:

- propagated principal headers are an internal propagation format
- they are not a standalone external authentication mechanism

## Authorization Model

Machine-authenticated principals should continue through the normal PDP flow.

The PDP input remains conceptually similar:

- principal id
- method
- path
- optional delegated user identity
- optional normalized scopes if relevant

But authorization behavior changes in one key way:

- machine principals should no longer universally inherit wildcard access through `ServiceSystem`

Instead, the platform should move toward explicit grants.

## Role And Grant Model

### Current Problem

Today a `service:*` principal effectively gets broad access through the default `ServiceSystem` role.

That is too broad for first-class machine auth.

### Proposed Direction

Add explicit support for machine-principal bindings.

Examples:

- bind `service:evaluator` to a narrow set of evaluator and model-read permissions
- bind `service:guardrails` to only the permissions it needs
- reserve a very small number of platform-internal break-glass principals for bootstrap paths if absolutely necessary

This can be implemented in stages.

#### Stage 1

- keep compatibility with existing `service:*` behavior for already-deployed internal services
- add the ability to create explicit machine-principal bindings
- prefer explicit bindings for new machine-authenticated callers

#### Stage 2

- shrink the default `ServiceSystem` grant surface
- require explicit bindings for most machine principals

#### Stage 3

- remove wildcard-by-default service-principal behavior entirely, or reduce it to a tightly scoped internal bootstrap set

## Route Policy

The existing caller distinction in `plugin-service-authz-spec.md` is compatible with this direction.

`SERVICE_PRINCIPAL` can remain the route-level concept for machine callers, but it should mean:

- a principal authenticated as a machine
- not merely a caller that presented `service:` in a trusted header

This spec does not require immediate route-decorator redesign.

It does require semantic tightening of what counts as a valid `SERVICE_PRINCIPAL`.

## Validation Strategy

Support a pluggable machine-token validator interface.

Conceptual interface:

```python
class MachineTokenValidator(Protocol):
    async def validate_token(self, token: str) -> MachineClaims | None: ...
```

Initial implementation:

- `KubernetesServiceAccountTokenValidator`

Returned claims should include enough data to:

- prove token validity
- identify provider type
- map to a normalized principal id
- surface audit metadata

## Auditing And Observability

Machine auth must be visible in logs and traces.

At minimum record:

- authenticated principal id
- principal kind: user or machine
- auth provider type
- delegated user id if present
- authorization decision reason when denied

This is important because the platform is moving from implicit trust to explicit machine identity.

## Discovery And Client UX

The current auth discovery endpoint is human-auth focused.

Machine auth may eventually need discovery metadata, but the first iteration does not need to expose full machine-auth discovery publicly.

For now:

- human CLI/SDK discovery remains unchanged
- machine callers are configured operationally through Kubernetes service account projection and cluster config

A follow-up may expose a minimal machine-auth capability advertisement if needed.

## Migration Plan

### Phase 1: Add Machine Validation

- add machine-auth config and validator abstraction
- support Kubernetes service account token validation
- normalize validated machine tokens into machine principals
- leave existing internal header propagation intact

### Phase 2: Bind Explicit Machine Principals

- add role-binding guidance and APIs for machine principals
- use explicit machine-principal grants for new services and automations

### Phase 3: Tighten Trust Boundaries

- restrict acceptance of raw `X-NMP-Principal-*` headers to trusted internal propagation contexts
- stop treating first-hop header injection as sufficient machine authentication

### Phase 4: Reduce Wildcard Service Grants

- narrow or remove default `ServiceSystem` wildcard authorization
- require explicit authorization for most machine principals

## Open Questions

1. Should Kubernetes service account validation use local JWKS validation, TokenReview, or both behind one provider abstraction?
2. How should internal first-hop trust be defined for header propagation during migration?
3. Should machine principal ids stay `service:<name>` or grow a more structured format such as `service:<namespace>:<name>`?
4. Which small set of bootstrap/internal services, if any, still need broad default access during migration?
5. Does the platform need a later API-key model for external automation that cannot use Kubernetes identity?

## Recommended Decision

NeMo Platform should add first-class machine authentication based on Kubernetes service account identity and treat that as the authoritative replacement for today's implicit service-principal trust model.

The core authorization model should remain NeMo-owned:

- machine credential proves identity
- platform normalizes that identity into a machine principal
- NeMo roles and endpoint policy determine what that machine may do

This gives the platform a real machine-auth story without forcing everything through OAuth and without preserving the current "trusted `service:` header means privileged caller" model as the long-term design.
