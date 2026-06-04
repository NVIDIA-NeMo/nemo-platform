# Security Model

This page describes the security architecture of {{platform_name}} authentication and authorization — how requests are authenticated, how access decisions are made, and where trust boundaries lie. It is intended for platform operators and security reviewers evaluating {{platform_name}} for production deployment.

For hands-on setup, see [Auth Configuration](deployment/configuration.md). For the authorization model, see [Concepts](concepts.md).

## Architecture Overview

```text
 ┌─────┐
 │ IdP │
 └──▲──┘
 │
 Validate credentials
 │
 ┌────────┐ │
 │ Client │──── Bearer token ────┐ │
 └────────┘ │ │
 │ │
┌────────────────────────────────┼───────┼───────────────────────────────────┐
│ Trust Boundary │ │
│ │ │ │
│ ┌───────────▼───┐ │ │
│ │ Gateway │───┘ │
│ │ (e.g. Envoy)│ │
│ │ │── X-NMP-Principal-* ──►┌────────────┐ │
│ └───────┬───────┘ │ PDP │ │
│ │ │ (Embedded │ │
│ │◄──── Allow/Deny ───────────────│ or OPA) │ │
│ │ └─────┬──────┘ │
│ │ │ │
│ X-NMP-Principal-* Fetches policy │
│ X-NMP-Authorized + role data │
│ │ │ │
│ ▼ ▼ │
│ ┌─────────┐ Check permissions ┌──────────────┐ │
│ │ Service │◄───────────────────────►│ │ │
│ │ │ (if not pre-authorized) │ Auth Service │ │
│ └────┬────┘ │ │ │
│ │ └──────────────┘ │
│ Forward X-NMP-Principal-* │
│ │ │
│ ▼ │
│ ┌──────────┐ │
│ │Downstream│ (Jobs, inference, other services) │
│ │ Service │ │
│ └──────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

The request flow:

1. **Client** sends a request with a JWT in the `Authorization: Bearer` header.
2. **Gateway** (or the service itself) validates the JWT signature, issuer, audience, and expiry against the configured OIDC provider.
3. **PDP** (Policy Decision Point) evaluates authorization — checks the principal's role bindings and token scopes against the operation's requirements.
4. If allowed, the service handles the request. In gateway deployments, the gateway forwards the request with trusted `X-NMP-Principal-*` headers so downstream services skip re-validation.

!!! note
    In quickstart deployments without an OIDC provider, the `X-NMP-Principal-*` headers are set directly by the client instead of being derived from a validated JWT. See [Getting Started](index.md).

## Authentication Modes

{{platform_name}} supports two authentication modes: **service-level** (the service validates the JWT) and **gateway-level** (the gateway validates at the edge).

In both modes, identity arrives as a **JWT** from the client. The JWT is validated exactly once — either by the first {{platform_name}} service or by the gateway. After validation, the authenticated identity (email, subject, groups) is propagated to downstream services via **trusted `X-NMP-Principal-*` headers**. Downstream services accept these headers without re-validating the JWT.

This "validate once, propagate via headers" design means that **network perimeter security is critical**: anything inside the trust boundary that receives `X-NMP-Principal-*` headers will trust them unconditionally. The gateway must strip these headers from all incoming external requests to prevent clients from forging an identity. See [Gateway Integration](deployment/gateway.md).

### Service-Level Authentication

The first {{platform_name}} service that receives the request validates the JWT directly:

1. Extracts the `Authorization: Bearer <token>` header
2. Validates the JWT signature, issuer, audience, and expiry against the configured OIDC provider
3. Extracts the principal identity (email, subject, groups) from JWT claims
4. Calls the PDP for an authorization decision
5. Forwards `X-NMP-Principal-*` headers to downstream services

No gateway is required. This is the simplest mode and the default.

### Gateway-Level Authentication

The gateway (e.g., Envoy with `ext_authz`) authenticates and authorizes the request before it reaches any service:

1. Gateway validates the JWT and calls the PDP
2. On success, sets `X-NMP-Authorized: true` and the `X-NMP-Principal-*` headers
3. Services see `X-NMP-Authorized: true` and skip their own JWT validation and PDP call

This rejects unauthorized requests as early as possible, before they reach any service. Services may still call the PDP for fine-grained permission checks (e.g., workspace-level access), but they skip JWT validation and the initial authorization decision.

## Principal Model

A **principal** is an authenticated identity — typically a human user identified by email address. Each request has exactly one principal.

When OIDC is enabled, the principal is resolved from JWT claims: the `sub` claim becomes the principal ID (or `oid` for Azure AD), the `email` claim provides the email (or `upn` for Azure AD), and group memberships come from the `groups` claim. These claim names are configurable. In gateway deployments, the gateway performs this extraction and forwards the result in `X-NMP-Principal-*` headers.

!!! note
    **Quickstart shortcut** — When running without OIDC (`email-as-API-key` mode), the principal is the raw value of the `X-NMP-Principal-Id` header, without any token validation. This is intended for quick testing only.

### Trusted Identity Headers

The following headers carry the authenticated identity through the system:

| Header | Description |
|---|---|
| `X-NMP-Principal-Id` | Unique identifier for the principal (required). Resolved from the JWT `sub` claim (or `oid` for Azure AD). |
| `X-NMP-Principal-Email` | The principal's email address. |
| `X-NMP-Principal-Groups` | Comma-separated list of groups the principal belongs to (from JWT group claims). |
| `X-NMP-Scopes` | Space-separated list of token scopes (extracted from the JWT `scp` or `scope` claim). Used by the PDP for scope-based authorization checks. |

These headers are set after JWT validation and forwarded on every internal service-to-service call. As described in [Authentication Modes](#authentication-modes), services inside the trust boundary accept them unconditionally — they are never re-validated.

Whichever component performs the initial authentication and authorization — the gateway in [gateway-level mode](#gateway-level-authentication), or the first service in [service-level mode](#service-level-authentication) — also sets `X-NMP-Authorized: true`. Downstream services see this header and skip their own JWT validation and PDP call.

### Service Principals

Not all requests originate from human users. Platform services that need cross-workspace access — for example, the jobs controller monitoring jobs across all users, or the evaluator coordinating evaluations — authenticate as **service principals**.

A service principal's ID has the form `service:<name>` (e.g., `service:jobs`, `service:evaluator`). Service principals are auto-authorized without a PDP call and have access to all workspaces and all operations. They are created internally by the platform and are never exposed to external callers.

**Internal endpoints** (`/internal/*`) are also auto-authorized — they bypass PDP checks entirely and are reserved for service-to-service communication.

!!! info
    Service principals rely on perimeter security — the gateway strips `X-NMP-Principal-*` headers from incoming requests, so external callers cannot forge a `service:` identity. The gateway must also block external access to `/internal/*` paths. See [Gateway Integration](deployment/gateway.md).

#### On-Behalf-Of Delegation

Some operations require a service to act with its own credentials while preserving the original user's identity for attribution and audit purposes. Two key examples:

- **Secret access**: A user cannot fetch a secret value directly — only the platform can — but the platform still needs to verify that the user has permission to access the secret's workspace.
- **Entity store access**: Feature-specific APIs (Models, Evaluation, etc.) check user permissions at the service level, then access the entity store using service credentials with the user's identity attached for `created_by`/`updated_by` attribution.

In these cases, the calling service sets the `X-NMP-Principal-On-Behalf-Of` header to a JSON object containing the original user's identity:

```json
{
  "id": "user-principal-id",
  "email": "alice@example.com",
  "groups": [
    "team-ml",
    "data-eng"
  ]
}
```

The downstream service constructs a principal from this object and evaluates the *user's* permissions — including group-based access — while accepting the request from the service identity.

#### Job Credential Propagation

Many {{platform_name}} operations — customization, evaluation, synthetic data generation — run as asynchronous jobs. When a user submits a job, the platform propagates the submitting user's identity into the job container via the `NMP_PRINCIPAL` environment variable.

!!! info
    Job containers need to run inside the trust boundary — they call {{platform_name}} APIs using the propagated identity headers and are subject to the same authorization checks as any other caller. The key distinction is that jobs act as the *user*, not as a privileged service principal, so they can only access resources the submitting user is permitted to reach.

## Authorization: Workspace-Scoped RBAC

{{platform_name}} uses **workspace-scoped Role-Based Access Control (RBAC)**. All resources (models, datasets, jobs, evaluations) belong to exactly one workspace, and access is controlled at the workspace level — not per-resource.

- Users are granted roles (Viewer, Editor, Admin) per workspace via **role bindings**
- The wildcard principal `*` binds a role for all authenticated users at once
- Workspaces are private by default; the creator becomes Admin automatically

On top of RBAC, {{platform_name}} supports **API scopes** as a second authorization layer at the token level. Every authorized request passes through two independent checks:

1. **Scope check** (token level): The JWT must carry at least one of the scopes required by the endpoint (e.g., `platform:read` or `platform:write`). Scopes limit what the *token* can do.
2. **Permission check** (role level): The principal must have the necessary permissions via role bindings in the workspace. Roles limit what the *user* can do.

Both must pass. This enables least-privilege token usage — for example, an Editor can create a read-only token (`platform:read` only) for monitoring scripts.

For details, see [Authorization Concepts](concepts.md), [Roles & Permissions](authorization/roles-and-permissions.md), and [API Scopes](authorization/api-scopes.md).

## What {{platform_name}} Does NOT Do

The following are explicitly out of scope for the current implementation:

- **Multi-tenancy with database isolation.** Workspaces provide logical isolation, not separate databases or schemas per tenant.
- **Service mesh mTLS.** Service-to-service encryption and mutual authentication are delegated to the customer's infrastructure (e.g., Istio, Linkerd).
- **Built-in audit logging.** The embedded PDP does not produce a dedicated audit trail. If you need structured decision logs, use [External OPA](authorization/policy-engine.md#external-opa) — OPA's [decision logging](https://www.openpolicyagent.org/docs/latest/management-decision-logs/) can export every authorization decision to your log aggregator.
- **Custom RBAC at runtime.** Custom roles can be defined at deployment time via YAML configuration, but cannot be created or modified at runtime through the API.

## Related

- [Authorization Concepts](concepts.md) — Workspaces, roles, bindings, and the RBAC model.
- [Auth Configuration](deployment/configuration.md) — Enabling auth, PDP provider, OIDC settings.
- [Gateway Integration](deployment/gateway.md) — Gateway-level auth and header configuration.
- [Production Hardening](deployment/hardening.md) — Security checklist for production deployments.
