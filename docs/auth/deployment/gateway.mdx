# Gateway Integration

In production, a gateway (reverse proxy, ingress controller, or service mesh) often sits in front of the {{platform_name}}. This page explains how authorization works with and without gateway-level auth, what headers the gateway must set, and which paths skip authorization.

For the security architecture, see [Security Model](../security-model.md).

## Overview

{{platform_name}}'s authorization middleware runs **inside each service**. Every request is evaluated there unless auth is disabled or the request matches a bypass path. Optionally, the **gateway** can perform the authorization check (e.g., via Envoy `ext_authz`) and forward the request with a special header so that services **trust the gateway's decision** and do not call the PDP again. That reduces latency and centralizes auth at the edge.

## Two Authorization Models

### Service-Level Auth (Default)

- The gateway forwards requests unchanged (aside from routing/TLS).
- Each service's middleware validates the token (or principal headers) and calls the PDP.
- **No gateway auth configuration required.** Easiest to set up.

### Gateway-Level Auth

- The gateway calls the PDP (e.g., via Envoy `ext_authz`) before forwarding.
- If the PDP allows the request, the gateway adds headers and forwards; otherwise it returns 403.
- Services see `x-nmp-authorized: true` and the principal headers, and **skip** their own PDP call.
- **Benefit**: One auth check per request at the edge; lower latency and fewer PDP calls.

To use gateway-level auth you must configure your gateway to call the {{platform_name}} PDP and set the headers described below on allowed requests.

!!! warning
    **Security Requirement**: Your ingress/gateway **must** strip the following headers from all incoming external requests before forwarding to {{platform_name}}:

    - `X-NMP-Principal-Id`, `X-NMP-Principal-Email`, `X-NMP-Principal-Groups`, `X-NMP-Principal-On-Behalf-Of`
    - `X-NMP-Authorized`, `X-NMP-Scopes`

    If external clients can set these headers, they can forge any identity or bypass authorization entirely. The gateway should also block external access to `/internal/*` paths (used for service-to-service communication).

## Required Headers (Gateway-Level Auth)

When the gateway has already authorized the request, it must set:

| Header | Description |
|--------|-------------|
| `X-NMP-Authorized` | Must be `true` so services trust the gateway's decision and skip PDP. |
| `X-NMP-Principal-Id` | Principal identifier (e.g., user ID or email). Required. |
| `X-NMP-Principal-Email` | User email (optional but recommended). |
| `X-NMP-Principal-Groups` | Comma-separated group names (optional). |

Header names are case-insensitive; services normalize them.

## Bypass Paths

The following are **not** subject to authorization checks; they are always allowed:

- **Health and readiness**: `/health`, `/healthz`, `/ready`, `/readyz`, `/health/live`, `/health/ready`, `/metrics`
- **Discovery**: `/apis/auth/discovery` (for CLI/SDK OIDC discovery)
- **PDP endpoints**: Paths under `/apis/auth/v2/authz/` are restricted to service principals only. The middleware rejects external and regular-user requests automatically.
- **Studio**: Paths under `/studio` (the Studio UI handles its own OIDC login)

Configure the gateway so these paths are not sent to the PDP (or are always allowed) when using gateway-level auth.

## Gateway Configuration Examples

### Envoy `ext_authz`

??? "Envoy ext_authz filter configuration"
    :icon: gear

    Replace placeholder values before applying this configuration.

    ```yaml
    http_filters:
      - name: envoy.filters.http.jwt_authn
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
          providers:
            <OIDC_PROVIDER_NAME>:
              issuer: "<OIDC_ISSUER_URL>"
              remote_jwks:
                http_uri:
                  uri: "<OIDC_JWKS_URI>"
                  cluster: <OIDC_JWKS_CLUSTER>
                  timeout: 5s
                cache_duration: 600s
              claim_to_headers:
                - header_name: "X-NMP-Principal-Id"
                  claim_name: "sub"
                - header_name: "X-NMP-Principal-Email"
                  claim_name: "email"
          rules:
            - match:
                prefix: "/"
              requires:
                provider_name: "<OIDC_PROVIDER_NAME>"
      - name: envoy.filters.http.ext_authz
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz
          grpc_service:
            envoy_grpc:
              cluster_name: <OPA_PDP_GRPC_CLUSTER>
            transport_api_version: V3
          failure_mode_allow: false
      - name: envoy.filters.http.router
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
    ```

### Header Stripping

Configure your gateway to remove {{platform_name}} auth headers from incoming external requests. This prevents clients from forging identities.

??? "Envoy header stripping"
    :icon: shield

    Add `request_headers_to_remove` to your route configuration:

    ```yaml
    route_config:
    virtual_hosts:
    - name: nmp_service
    domains: ["*"]
    request_headers_to_remove:
    - "x-nmp-principal-id"
    - "x-nmp-principal-email"
    - "x-nmp-principal-groups"
    - "x-nmp-principal-on-behalf-of"
    - "x-nmp-scopes"
    - "x-nmp-authorized"
    routes:
    - match: { prefix: "/" }
    route: { cluster: nmp_backend }
    ```

## Testing Gateway Auth

After configuring gateway-level auth, verify:

1. **Headers are set correctly** — Make a request through the gateway and check that `X-NMP-Authorized` and `X-NMP-Principal-Id` are present on the service side.
2. **Headers are stripped from external requests** — Try sending `X-NMP-Authorized: true` from outside; verify it is stripped by the gateway.

## Related

- [Auth Configuration](configuration.md) — Enabling auth and PDP provider (embedded vs OPA).
- [Security Model](../security-model.md) — Trust boundaries and gateway trust model.
- [Production Hardening](hardening.md) — Security checklist including gateway requirements.
