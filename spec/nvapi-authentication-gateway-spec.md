# NVAPI Authentication Gateway Spec

## Summary

This spec proposes a way to let external callers authenticate to NeMo Platform using NVIDIA `nvapi-...` API keys.

The recommended first iteration is **not** a normal NeMo plugin service. It is an **edge authentication translator** that sits in front of NeMo Platform, validates NVIDIA API keys against NVIDIA-hosted APIs, maps validated keys to NeMo principals, and forwards requests with the `X-NMP-Principal-*` headers that NeMo Platform already understands.

This keeps authorization in NeMo Platform RBAC while avoiding a larger redesign of the in-process auth stack.

## Problem

Today NeMo Platform has two practical authentication paths:

- `Authorization: Bearer <jwt>` for OIDC JWTs validated by `packages/nmp_common/src/nmp/common/auth/jwt.py`
- trusted `X-NMP-Principal-*` headers inside the platform trust boundary

That leaves no first-class path for NVIDIA API keys:

- NVIDIA `nvapi-...` keys are not OIDC JWTs
- the current middleware has no pluggable external API-key authenticator
- plugin `NemoService` surfaces are too late in the request path to act as the primary authentication mechanism

The user goal is to let a caller present a NVIDIA API key and have NeMo Platform treat that caller as an authenticated principal that can be authorized through existing workspace RBAC.

## External Constraint: What NVIDIA Keys Are

As of June 8, 2026, NVIDIA documentation describes `NVIDIA_API_KEY` values that start with `nvapi-` as opaque API keys used as Bearer credentials against NVIDIA-hosted APIs such as `integrate.api.nvidia.com` and `ai.api.nvidia.com`.

Important implications:

- they are documented as **Bearer API keys**, not as JWTs
- NeMo Platform cannot validate them locally with the existing OIDC/JWKS path
- NVIDIA docs reviewed for this spec do **not** document a general-purpose introspection or userinfo endpoint that would return stable user claims and groups for a presented key

Because of that, any NeMo integration must separate:

- **key possession validation**
- **NeMo principal projection**
- **NeMo authorization**

## Goals

- Allow external clients to authenticate to NeMo Platform with NVIDIA `nvapi-...` keys.
- Reuse NeMo Platform's existing RBAC and PDP authorization model after authentication.
- Avoid forcing the auth middleware to pretend NVIDIA API keys are OIDC JWTs.
- Minimize core-platform changes in the first iteration.
- Keep the design compatible with Envoy `ext_authz` or a similar gateway callout model.
- Preserve fail-closed behavior if NVIDIA validation, mapping lookup, or downstream authorization fails.

## Non-Goals

- Replacing OIDC as the main human authentication story.
- Treating NVIDIA API keys as a source of NeMo roles or workspace grants.
- Inventing a general plugin-based authentication framework in the first iteration.
- Assuming NVIDIA exposes stable identity claims, groups, or workspace memberships for an API key.
- Storing raw NVIDIA API keys in NeMo unless a later workflow explicitly requires it.

## Current NeMo State

### What exists today

- Bearer authentication is handled in `AuthorizationMiddleware`.
- JWT validation is OIDC-oriented and backed by issuer/JWKS discovery.
- Trusted `X-NMP-Principal-*` headers are accepted and normalized into a `Principal`.
- Authorization remains a PDP call using the normalized principal plus optional scopes.
- OPA policies already support both direct middleware input and Envoy-style `ext_authz` input.

### What does not exist today

- no `auth.providers[]` or equivalent authenticator chain
- no first-class NVIDIA API-key validator
- no first-class API-key-to-principal mapping store
- no implemented in-process fast path for a trusted `X-NMP-Authorized: true` gateway decision in the middleware path reviewed for this spec

That last point matters: the docs describe gateway-level pre-authorization, but the current middleware still routes `X-NMP-Principal-*` requests through the normal PDP path when auth is enabled.

## Why This Should Not Be A Normal `NemoService` Plugin

A standard plugin service is mounted as application routers after the platform process is already accepting the request.

That is too late for primary authentication because:

- authentication must happen before request routing reaches arbitrary services
- the auth middleware lives in shared core code, not in service routers
- any solution that depends on a plugin route still needs some earlier component to trust the caller first

So the right boundary for v1 is not "auth as a plugin service". It is "auth as an edge translator/callout that produces NeMo-trusted identity headers".

## Design Options

### Option 1: Native In-Process NVAPI Auth Provider

Add a new authenticator into `AuthorizationMiddleware`, for example:

- inspect `Authorization: Bearer <token>`
- if token starts with `nvapi-`, call a NVIDIA validation routine
- map the validated key to a NeMo principal
- continue into the existing PDP flow

Pros:

- first-class internal implementation
- no extra gateway component
- clean UX for clients

Cons:

- larger core-auth redesign
- needs new config surface, new secrets/caching rules, and new tests in every service process
- still cannot derive claims from the key without a local mapping or NVIDIA introspection API
- pushes an external network dependency into every platform service

### Option 2: Standalone Gateway / Translator In Front Of NeMo

Put a small service or proxy in front of NeMo Platform:

1. receive external request
2. strip all incoming `X-NMP-*` identity headers
3. validate `Authorization: Bearer nvapi-...`
4. map the key to a NeMo principal
5. forward request to NeMo with `X-NMP-Principal-*` headers

Pros:

- minimal NeMo core change
- clean trust boundary
- can be deployed independently
- lets NeMo continue using current principal-header path

Cons:

- one more deployable component
- requires strict network topology so callers cannot bypass the gateway
- NeMo still performs its own PDP check, so this is authentication translation rather than full authn+authz offload

### Option 3: Envoy `ext_authz` Callout

Use Envoy plus a custom ext_authz service:

1. Envoy receives request
2. ext_authz service validates NVIDIA key and computes principal projection
3. Envoy injects `X-NMP-Principal-*` headers
4. request proceeds to NeMo

Pros:

- aligns with the existing auth docs and OPA input model
- operationally standard for production gateways
- easiest path if a team already runs Envoy

Cons:

- functionally similar to Option 2, but with Envoy-specific deployment complexity
- still subject to the current NeMo middleware gap around trusted pre-auth short-circuiting

## Recommendation

Recommend **Option 2 or Option 3**, depending on deployment preference:

- **Option 2** if we want the simplest path that can be developed and tested quickly
- **Option 3** if the target deployment already uses Envoy and wants `ext_authz`

In both cases, the NeMo-facing contract should be the same:

- NeMo receives only trusted `X-NMP-Principal-*` headers from the gateway
- NeMo continues to own authorization through the existing PDP and workspace RBAC

This is the least invasive v1 and does not require pretending NVIDIA API keys are JWTs.

## Proposed Architecture

```text
external client
  -> edge gateway / ext_authz service
     -> NVIDIA key validation probe
     -> local key-fingerprint -> principal mapping lookup
     -> inject X-NMP-Principal-* headers
  -> NeMo Platform
     -> existing AuthorizationMiddleware
     -> existing PDP / RBAC
```

## Request Flow

### Phase 1 request flow

1. Client sends `Authorization: Bearer nvapi-...`.
2. Edge translator strips any inbound `X-NMP-*` auth headers.
3. Translator checks that the token matches expected NVIDIA key shape.
4. Translator computes a **non-reversible fingerprint** of the raw key.
5. Translator looks up a local mapping for that fingerprint.
6. Translator validates the key with a configurable NVIDIA probe request.
7. If validation succeeds, translator injects:
   - `X-NMP-Principal-Id`
   - `X-NMP-Principal-Email` when available locally
   - `X-NMP-Principal-Groups` when configured locally
   - optional `X-NMP-Scopes` when local mapping assigns normalized NeMo scopes
8. Translator forwards to NeMo Platform.
9. NeMo middleware treats the request like any other trusted principal-header request and performs the normal PDP authorization check.

If any step fails, the translator returns `401` or `403` and does not forward the request.

## Principal Mapping Model

Because NVIDIA API keys do not currently provide the claims NeMo needs, the system needs a local mapping layer.

### Mapping record

Conceptual shape:

```yaml
nvapi_identity:
  fingerprint: "hmac-sha256:..."
  principal_id: "user@example.com"
  principal_email: "user@example.com"
  principal_groups:
    - "team-ml"
    - "nvidia-build-users"
  scopes:
    - "platform:read"
    - "platform:write"
  status: "active"
```

### Why fingerprint, not raw key

- avoids persisting raw NVIDIA API keys in the platform for normal request handling
- supports deterministic lookup
- limits blast radius if the mapping store is leaked

The fingerprint should be derived with a server-side HMAC secret, not plain SHA256, to make offline guessing harder.

### Identity source of truth

The mapping store should be local to NeMo deployment operations, not inferred from NVIDIA at request time.

Possible implementations:

- YAML config for early prototypes
- entity-store backed records in a later iteration
- secret-backed registration flow if users self-enroll keys

## NVIDIA Validation Strategy

### Recommended v1 validation

Use a configurable probe against a documented NVIDIA-hosted API that accepts the same Bearer key, for example a lightweight request to a models endpoint.

The validator should treat a success response as "the key is live" and any auth failure as invalid.

### Validation config

Conceptual config:

```yaml
auth:
  nvapi:
    enabled: true
    validation_url: "https://integrate.api.nvidia.com/v1/models"
    timeout_seconds: 3
    cache_ttl_seconds: 300
```

### Cache behavior

- cache positive validations for a short TTL
- cache negative validations for a much shorter TTL
- key cache key should be the local fingerprint, not the raw key
- all cache misses and validation failures fail closed

### Important limitation

This proves that the caller holds a currently valid NVIDIA API key.
It does **not** prove:

- who the human is, unless the local mapping says so
- what groups they belong to in NVIDIA
- what NeMo workspaces they should access

Those remain local NeMo concerns.

## Authorization Behavior

Authorization should stay exactly where it already lives:

- NeMo PDP
- workspace role bindings
- endpoint permissions
- optional normalized scopes

The NVIDIA key only gets the caller through authentication.
It must never directly grant platform permissions.

## Registration / Enrollment Modes

### Mode A: Operator-managed mapping

An operator creates mapping entries manually.

Pros:

- simplest implementation
- no raw key storage required

Cons:

- operationally manual

### Mode B: Self-service registration

A user registers a NVIDIA key once through a dedicated enrollment workflow:

1. present key
2. gateway validates it
3. system stores fingerprint and metadata
4. operator or automation binds it to a principal

Pros:

- better UX

Cons:

- needs a dedicated onboarding API and lifecycle management

### Mode C: Full dynamic identity federation

Only viable if NVIDIA eventually exposes a documented introspection or userinfo API that returns stable identity claims for a presented key.

This spec does not assume that exists.

## Security Requirements

### Network boundary

The translator or gateway must be the **only** externally reachable path to NeMo services that trust `X-NMP-Principal-*` headers.

Direct access to platform services from untrusted networks must be blocked.

### Header stripping

The edge must remove inbound:

- `X-NMP-Principal-Id`
- `X-NMP-Principal-Email`
- `X-NMP-Principal-Groups`
- `X-NMP-Principal-On-Behalf-Of`
- `X-NMP-Scopes`
- `X-NMP-Authorized`

before any translation logic runs.

### Storage

- do not log raw NVIDIA API keys
- do not persist raw keys for normal request auth unless a separate enrollment feature explicitly requires it
- redact keys in traces and structured logs

### Failure mode

If NVIDIA validation is unavailable, the translator should fail closed by default.

This is stricter than best-effort auth and is the correct default for a primary authentication system.

## Operational Concerns

### Latency

Per-request remote validation adds latency.
That is why short-lived positive caches are required.

### Availability

This design adds a dependency on NVIDIA API availability for uncached validations.

### Rate limits

The validation probe may consume NVIDIA API quota or hit rate limits.
The probe endpoint and cache TTL must be chosen accordingly.

### Revocation window

Positive caching creates a short window where a recently revoked key may still authenticate until cache expiry.

## Compatibility With Current NeMo Code

### Works today without large core changes

The translator approach fits the existing principal-header path in:

- `packages/nmp_common/src/nmp/common/auth/middleware.py`
- `packages/nmp_common/src/nmp/common/auth/models.py`
- the current PDP and OPA policies

### Known gap

The docs discuss gateway-level pre-authorization via `X-NMP-Authorized: true`, but the middleware path reviewed for this spec does not currently consume that as a skip-PDP fast path.

So phase 1 should assume:

- gateway translates authentication
- NeMo still performs authorization

That is acceptable for v1.

## Optional Phase 2: Trusted Pre-Authorization Fast Path

After the translator is working, we may add a small core improvement:

- if request arrives from a configured trusted proxy identity or network
- and `X-NMP-Authorized: true` is present
- and `X-NMP-Principal-*` headers are present and valid
- then middleware may skip its own PDP call

This would turn the edge component into a full authn+authz offload point.

This should be a separate change because it expands the trust surface and needs careful hardening.

## Suggested Implementation Plan

### Phase 1

- build a small standalone translator service or Envoy ext_authz service
- add local key-fingerprint mapping
- add configurable NVIDIA validation probe
- forward mapped `X-NMP-Principal-*` headers to NeMo
- document required network and header-stripping constraints

### Phase 1.5

- add entity-store backed mapping records
- add operator CRUD APIs or CLI for mapping management
- add audit events for mapping create/revoke/use

### Phase 2

- add trusted gateway pre-auth support in middleware
- optionally support gateway-injected `X-NMP-Authorized: true`
- optionally add a generalized authenticator chain in core auth if multiple non-OIDC auth methods are needed

## Open Questions

- Which NVIDIA endpoint is the best long-lived validation probe for key liveness?
- Do we want mapping records to point at human principals, service principals, or both?
- Should NeMo-managed scopes be assignable in the mapping record, or should RBAC alone be sufficient?
- Is manual operator mapping enough for the first usable version?
- Do we want the translator to be repo-owned, or treated as a deployment-side reference implementation?

## Recommendation

Proceed with a **gateway/ext_authz translator** as v1.

Do **not** start with a normal `NemoService` plugin and do **not** start by teaching the current JWT validator to parse NVIDIA API keys.

The right first step is:

- validate NVIDIA API key possession at the edge
- map the key to a local NeMo principal
- forward trusted principal headers
- let existing NeMo authorization decide access

That matches the current platform architecture with the smallest amount of core churn.

## References

- NeMo Platform middleware and principal model:
  - `packages/nmp_common/src/nmp/common/auth/middleware.py`
  - `packages/nmp_common/src/nmp/common/auth/models.py`
  - `packages/nmp_common/src/nmp/common/auth/jwt.py`
- NeMo Platform auth docs:
  - `docs/auth/deployment/gateway.md`
  - `docs/auth/security-model.md`
  - `docs/auth/authentication/oidc.md`
- Existing repo specs:
  - `spec/machine-auth-authentication-and-authorization-spec.md`
  - `spec/oidc-scope-and-claim-mapping-spec.md`
- NVIDIA docs reviewed on June 8, 2026:
  - NeMo Retriever docs: `NVIDIA_API_KEY` authorizes HTTP calls to NVIDIA-hosted NIMs and keys typically start with `nvapi-`
  - NeMo Evaluator docs: NVIDIA Build authentication example uses `Authorization: Bearer $NGC_API_KEY` against `https://integrate.api.nvidia.com/v1/models`
  - NVIDIA Build model docs: gRPC examples pass `authorization: Bearer $NVIDIA_API_KEY`
