# Configuration Reference

Complete reference for enabling and configuring platform authorization: the `auth` section in config, Helm values, environment variables, and the choice between embedded and external OPA.

For quickstart setup, see [Authentication and Authorization](../index.md). For OIDC settings, see [OIDC Setup](../authentication/oidc.md).

## Enabling Authorization

Authorization is enabled in the platform config by setting `auth.enabled: true`. This can be done in the platform config file:

```yaml
auth:
 enabled: true
```

When using Helm, this is done by setting `platformConfig.auth.enabled: true` in your Helm values; this becomes `auth.enabled` in the calculated platform config.

```yaml
# values.yaml

platformConfig:
 auth:
 enabled: true
```

When `auth.enabled` is `false` (the default), all API requests are allowed without checks. When `true`, every request is evaluated by the Policy Decision Point (PDP). In Helm deployments, this setting is controlled via `platformConfig.auth.enabled`.

### Bootstrap Admin

When authorization is enabled, a platform administrator can be configured. Setting **`admin_email`** gives that identity the **PlatformAdmin** role at platform start. Use it to create the first workspaces and grant roles to other users. After bootstrap, manage access via workspaces and members as described in [Managing Access](../authorization/managing-access.md).

```yaml
auth:
 enabled: true
 admin_email: "your-admin@company.com"
```

For a complete reference of all `auth` fields and their defaults, see the [platform configuration reference](../../set-up/config-reference.md). Auth-related values are found under `platformConfig.auth` in the values file.

For OIDC-specific fields (`auth.oidc`), see [OIDC Setup](../authentication/oidc.md).

## Authorization Engine: Embedded vs External OPA

The PDP can run in two modes. For technical details, see [Policy Engine](../authorization/policy-engine.md).

### Embedded (default)

- **Provider**: `policy_decision_point_provider: "embedded"`.
- The auth service runs a built-in WASM policy engine. No OPA sidecar is required.
- Policy data (role bindings, scopes, etc.) is loaded from the entity store and refreshed on an interval (`policy_data_refresh_interval`).

Use embedded for new deployments and when you do not already have an OPA fleet.

### External OPA

- **Provider**: `policy_decision_point_provider: "opa"`.
- An external OPA sidecar (or server) fetches policy bundles from the auth service and evaluates requests.
- Set `policy_decision_point_base_url` to the OPA service URL (e.g., `http://opa:8181`).
- `bundle_cache_seconds` controls how long OPA caches the bundle.

Use external OPA when you already use OPA for other services or need a single policy engine at the edge.

## Environment Variables

Configuration can be overridden with environment variables using the **`NMP_AUTH_`** prefix. Names are derived from the config keys in UPPER_SNAKE_CASE.

Examples:

```bash
NMP_AUTH_ENABLED=true
NMP_AUTH_POLICY_DECISION_POINT_BASE_URL=http://auth:8000
NMP_AUTH_POLICY_DECISION_POINT_PROVIDER=embedded
NMP_AUTH_ADMIN_EMAIL=admin@example.com
```

Nested keys (e.g., OIDC) use double underscore: `NMP_AUTH_OIDC__ISSUER`, `NMP_AUTH_OIDC__CLIENT_ID`.

## Example Configurations

### Quickstart / development (auth disabled)

```yaml
auth:
 enabled: false
```

### Quickstart / development (auth enabled)

```yaml
auth:
 enabled: true
 policy_decision_point_provider: embedded
 policy_decision_point_base_url: "http://localhost:8080"
 admin_email: "admin@example.com"
```

### Production with embedded PDP

```yaml
auth:
 enabled: true
 policy_decision_point_base_url: "http://auth:8000"
 policy_decision_point_provider: embedded
 policy_data_refresh_interval: 30
 admin_email: "platform-admin@company.com"
 oidc:
 enabled: true
 issuer: "https://login.microsoftonline.com/<tenant>/v2.0"
 client_id: "<client-id>"
```

### Production with external OPA

```yaml
auth:
 enabled: true
 policy_decision_point_base_url: "http://opa:8181"
 policy_decision_point_provider: opa
 bundle_cache_seconds: 5
```

## Related

- [Authentication and Authorization](../index.md) — Overview, auth methods, and getting started.
- [OIDC Setup](../authentication/oidc.md) — IdP configuration and CLI login.
- [Gateway Integration](gateway.md) — Using a gateway for authorization.
- [Managing Access](../authorization/managing-access.md) — Workspaces and member management.
- [Policy Engine](../authorization/policy-engine.md) — PDP internals and configuration.
