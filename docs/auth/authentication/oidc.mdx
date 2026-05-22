# OIDC Setup

Connect {{platform_name}} to an external OIDC identity provider (IdP) so users sign in with your organization's identity and receive OAuth2 access tokens for API access.

**Prerequisites**: You need an OAuth application registered in your IdP with the client ID, issuer URL, and device flow grant enabled. See the [Minimum IdP Checklist](#minimum-idp-checklist) below.

For login after setup, see [Using Authentication](using-authentication.md). For the full config reference, see [Auth Configuration](../deployment/configuration.md).

## How OIDC Fits in {{platform_name}}

When OIDC is enabled:

1. **Platform configuration** points to your IdP (issuer URL, client ID, optional scope prefix and claim names).
2. **Discovery**: Clients and the platform discover token and device-auth endpoints from the IdP's `.well-known/openid-configuration` (or from {{platform_name}}'s aggregated discovery at `{BASE_URL}/apis/auth/discovery`).
3. **Login**: Users obtain access tokens via **device flow** (browser) or **password grant** (CI) using the CLI.
4. **API calls**: Requests send the access token in the `Authorization: Bearer <token>` header. {{platform_name}} validates the JWT (signature, issuer, audience, expiry) and extracts the principal and scopes for authorization.

OIDC provides the identity; authorization (workspace roles, scopes) works the same as with any other auth method.

## Flows Supported

- **Device authorization flow**: User runs `nemo auth login`; the CLI shows a code and opens the IdP page; after the user signs in and consents, the CLI receives an access token (and optionally a refresh token). Best for interactive use.
- **Resource owner password grant**: For non-interactive environments (CI), `nemo auth login --username <user> --password <pass>` exchanges credentials for a token. Your IdP must support this grant type.

!!! warning
    Password grant sends user credentials directly to the IdP. It bypasses MFA and is disabled by many production IdPs. Use it only for CI/testing. Prefer device flow for interactive users.

## Step-by-Step Configuration

### Step 1: Register an OAuth Application

In your IdP (Azure AD, Okta, Keycloak, etc.):

1. Create a new application registration
2. Note the **client ID**
3. Enable **device flow** (device authorization grant)
4. *(Optional)* Create custom API scopes (`platform:read`, `platform:write`) if you want token-level scope restrictions. See [API Scopes](../authorization/api-scopes.md).
5. If you created custom scopes, grant admin consent for them (if required by your IdP)

### Step 2: Configure {{platform_name}}

Set the OIDC settings in your platform config under `auth.oidc`:

```yaml
auth:
 enabled: true
 admin_email: "platform-admin@company.com"
 oidc:
 enabled: true
 issuer: "https://your-idp.example.com/realm"
 client_id: "your-client-id"
 # Optional: strip IdP scope prefix (e.g., Azure AD prepends API URI)
 # scope_prefix: "api://your-client-id/"
 # Optional: override claim names if your IdP uses non-standard names
 # email_claim: "upn"
 # subject_claim: "oid"
 # groups_claim: "groups"
```

### Step 3: Configure Scopes (Optional)

This step is only needed if you created custom API scopes in Step 1. If you skip scopes, {{platform_name}} still enforces RBAC — scopes add an additional token-level restriction on top. See [API Scopes](../authorization/api-scopes.md).

If you are using scopes, configure the default scopes requested during login:

```yaml
auth:
 oidc:
 default_scopes: "openid profile email offline_access platform:read platform:write"
```

If your IdP prefixes scopes (e.g., Azure AD uses `api://client-id/platform:read`), set `scope_prefix` so {{platform_name}} strips it before authorization:

```yaml
auth:
 oidc:
 scope_prefix: "api://your-client-id/"
```

### Step 4: Verify

After deploying the configuration:

```bash
# Log in via device flow
nemo auth login

# Check login status
nemo auth status
# Expected: shows principal email, scopes, token expiry

# Verify API access
nemo workspaces list
```

## OIDC Configuration Reference

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enable OIDC token validation. |
| `issuer` | string | IdP issuer URL (e.g., `https://login.microsoftonline.com/<tenant>/v2.0`). |
| `client_id` | string | OAuth client ID for {{platform_name}}. |
| `additional_issuers` | list | Extra issuer URLs to accept (e.g., Azure AD v1 format). |
| `audience` | string | Expected token audience (defaults to `client_id`). |
| `email_claim` | string | JWT claim for email (default: `email`). |
| `subject_claim` | string | JWT claim for subject (default: `sub`). |
| `groups_claim` | string | JWT claim for groups (default: `groups`). |
| `default_scopes` | string | Space-separated scopes requested when user does not pass `--scope`. |
| `scope_prefix` | string | Prefix stripped from token scopes before authorization. |
| `token_endpoint` | string | Override token endpoint (otherwise discovered from IdP). |
| `device_authorization_endpoint` | string | Override device auth endpoint. |
| `jwks_uri` | string | Override JWKS URI. |

## Minimum IdP Checklist

Regardless of IdP, ensure:

1. You have registered an OAuth application and have the **client ID** (and client secret if required).
2. The application supports the **device authorization grant** (for `nemo auth login`).
3. The access token includes claims for email, subject, and groups (or you have configured `email_claim`, `subject_claim`, `groups_claim` to match your IdP's claim names).
4. *(If using scopes)* Custom API scopes (`platform:read`, `platform:write`) are exposed, included in access tokens, and admin consent is granted if required.

## Claim mapping

{{platform_name}} maps JWT claims to [trusted identity headers](../security-model.md#trusted-identity-headers) using `email_claim`, `subject_claim`, and `groups_claim` (defaults: `email`, `sub`, `groups`). Override them when your IdP uses different claim names — values must match what you use for workspace members and authorization.

| Purpose | Config key | Default | Header |
|---------|------------|---------|--------|
| Subject (Principal ID) | `subject_claim` | `sub` | `X-NMP-Principal-Id` |
| Email | `email_claim` | `email` | `X-NMP-Principal-Email` |
| Groups | `groups_claim` | `groups` | `X-NMP-Principal-Groups` |


!!! note
    Group values are extracted from the JWT and included in the `X-NMP-Principal-Groups` header and OPA policy data, but **automatic group-to-role mapping is not yet implemented**. Role assignments must be made explicitly via the members API. See [Managing Access](../authorization/managing-access.md).

## Provider-Specific Notes

- **Azure AD**: See [Azure AD Setup](providers/azure-ad.md) (issuer, `additional_issuers`, device flow, claim overrides).
- **Okta**: Choose the correct authorization server (custom vs org). Ensure device flow is enabled.
- **Keycloak**: Configure realm, client, and role mappers. Enable device flow in client settings.
- **Other providers**: See [Generic OIDC Provider](providers/generic.md) for a provider-agnostic checklist.

## Related

- [Using Authentication](using-authentication.md) — Log in, make API calls, and manage tokens.
- [Auth Configuration](../deployment/configuration.md) — Full auth config reference.
