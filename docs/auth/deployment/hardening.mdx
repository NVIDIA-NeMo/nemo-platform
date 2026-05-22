# Production Hardening

Security checklist for deploying {{platform_name}} to production. Work through each section and verify your deployment meets these requirements.

For the security architecture, see [Security Model](../security-model.md). For configuration details, see [Auth Configuration](configuration.md).

## Authentication

- [ ] **Enable auth**: Set `auth.enabled: true` in platform config.
- [ ] **Configure OIDC**: Connect a production identity provider. See [OIDC Setup](../authentication/oidc.md).
- [ ] **Disable password grant in production**: Password grant bypasses MFA. If your IdP supports it, disable the resource owner password grant for the {{platform_name}} application registration. Restrict it to dedicated service accounts if CI/CD requires it.
- [ ] **Set `admin_email` to a real platform admin**: Use a specific person's email, not a shared mailbox. The PlatformAdmin role bypasses all authorization checks.
- [ ] **Verify token lifetime**: Check your IdP's access token and refresh token lifetimes. Shorter access token lifetimes (1 hour or less) reduce the impact of token theft.
- [ ] **Review additional issuers**: If `additional_issuers` is configured, verify all listed issuers are trusted. Each issuer can produce tokens that {{platform_name}} will accept.

## Authorization

- [ ] **Review default workspace bindings**: The `default` workspace grants Editor to `*` (all authenticated users). If your deployment requires tighter control, restrict this after bootstrap.
- [ ] **Restrict PlatformAdmin**: Only one email should have PlatformAdmin. This role bypasses all authorization — treat it like a root account.
- [ ] **Use scoped tokens for CI/CD**: Request `platform:read` only for pipelines that don't need to modify resources. See [API Scopes](../authorization/api-scopes.md).
- [ ] **Audit workspace access**: Periodically review workspace members (`nemo members list --workspace <name>`) and remove stale access.
- [ ] **Use wildcard bindings carefully**: Only grant `*` (all users) a role when you intentionally want shared access. Prefer Viewer over Editor for public workspaces.

## Gateway and Network

- [ ] **Strip auth headers from external requests**: Configure your ingress/gateway to remove `X-NMP-Principal-Id`, `X-NMP-Principal-Email`, `X-NMP-Principal-Groups`, `X-NMP-Principal-On-Behalf-Of`, `X-NMP-Authorized`, and `X-NMP-Scopes` from all incoming external traffic. See [Gateway Integration](gateway.md).
- [ ] **Enable TLS termination**: Terminate TLS at the ingress or load balancer. Tokens in `Authorization` headers are sent in the clear without TLS.
- [ ] **Consider gateway-level auth**: For reduced latency and centralized authorization, configure Envoy `ext_authz` to call the PDP at the edge. See [Gateway Integration](gateway.md).

## Policy Engine

- [ ] **Choose the right PDP provider**: Use embedded (default) for new deployments. Use external OPA if you already run OPA for other services. See [Policy Engine](../authorization/policy-engine.md).
- [ ] **Set appropriate refresh interval**: `policy_data_refresh_interval` (embedded) or `bundle_cache_seconds` (external OPA) controls how quickly role changes take effect. Lower values = faster propagation but more load on the entity store.
- [ ] **Monitor PDP health**: Ensure the auth service (embedded) or OPA sidecar (external) is healthy. If the PDP is unreachable, the middleware fails closed (returns 503).

## Secrets and Credentials

- [ ] **Verify CLI config file permissions**: Token storage at `~/.config/nmp/config.yaml` should have permissions `0600` (owner read/write only). Avoid storing this file in cloud-synced or shared directories. See [Using Authentication — Config File](../authentication/using-authentication.md#config-file) for full guidance.
- [ ] **Rotate IdP client secrets**: If your OIDC application uses a client secret, rotate it periodically per your organization's policy.
- [ ] **Avoid storing tokens in source code or CI configs**: Use environment variables or secret managers for tokens in CI/CD pipelines.

## Deployment Validation

After applying these settings, verify your deployment:

```bash
# 1. Verify auth is enabled
curl -s ${BASE_URL}/apis/auth/discovery | python -m json.tool
# Expected: "auth_enabled": true

# 2. Verify unauthenticated requests are rejected
curl -s -o /dev/null -w "%{http_code}" ${BASE_URL}/v2/workspaces
# Expected: 401

# 3. Verify authenticated requests work
nemo auth login
nemo workspaces list
# Expected: success

```

## Related

- [Security Model](../security-model.md) — Architecture, trust boundaries, and authorization layers.
- [Auth Configuration](configuration.md) — Full configuration reference.
- [Gateway Integration](gateway.md) — Gateway auth and header stripping.
- [Roles & Permissions](../authorization/roles-and-permissions.md) — Permission matrix for role auditing.
