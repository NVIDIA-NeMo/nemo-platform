# Azure AD (Entra ID) Setup

Complete walkthrough for connecting {{platform_name}} to Azure AD (Entra ID), from app registration to first successful login.

**Prerequisites**: Access to Azure Portal with permission to create app registrations. Familiarity with [OIDC Setup](../oidc.md).

## App Registration

1. In Azure Portal, go to **Azure Active Directory** → **App registrations** → **New registration**.
2. Name the application (e.g., "{{platform_name}}").
3. Set **Supported account types** to your tenant configuration.
4. No redirect URI is needed for device flow, but setting one is good practice.
5. Note the **Application (client) ID** and **Directory (tenant) ID**.

## Enable Device Flow

1. Go to **Authentication** in the app registration.
2. Under **Advanced settings**, set **Allow public client flows** to **Yes**.
3. Save.

## Expose API Scopes

1. Go to **Expose an API**.
2. Set the **Application ID URI** (e.g., `api://<client-id>`).
3. Add scopes:
 - `platform:read` — "Read access to {{platform_name}} platform resources"
 - `platform:write` — "Write access to {{platform_name}} platform resources"
4. Go to **API permissions** → **Add a permission** → **My APIs** → select your app → add the scopes.
5. Click **Grant admin consent** for the scopes.

## Configure Group Claims (Optional)

1. Go to **Token configuration** → **Add groups claim**.
2. Select **Security groups** (or the group types your organization uses).
3. For the **Access token**, select **Group ID**.

## {{platform_name}} Configuration

```yaml
auth:
 enabled: true
 admin_email: "platform-admin@company.com"
 oidc:
 enabled: true
 issuer: "https://login.microsoftonline.com/<tenant-id>/v2.0"
 client_id: "<client-id>"
 audience: "api://<client-id>"
 # Azure AD v1 tokens may have a different issuer
 additional_issuers:
 - "https://sts.windows.net/<tenant-id>/"
 email_claim: "upn"
 subject_claim: "oid"
 groups_claim: "groups"
 # Azure AD prefixes custom scopes with the API URI
 scope_prefix: "api://<client-id>/"
 default_scopes: "openid profile email offline_access api://<client-id>/platform:read api://<client-id>/platform:write"
```

## Verification

```bash
nemo auth login
# Browser opens to Microsoft login page
# Sign in and consent to the requested permissions

nemo auth status
# Expected: Logged in as user@company.com, scopes: platform:read platform:write
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| AADSTS70011 | Scope not configured or no admin consent | Add scopes in "Expose an API" and grant admin consent |
| AADSTS50011 | Reply URL mismatch | Not typically needed for device flow; check Authentication settings |
| Audience mismatch | `audience` doesn't match token's `aud` claim | Set `audience: "api://<client-id>"` |
| Empty email claim | Azure AD didn't populate `email` | Use `email_claim: "upn"` instead |

## Related

- [OIDC Setup](../oidc.md) — Generic OIDC configuration.
- [OIDC Setup — Claim mapping](../oidc.md#claim-mapping) — JWT claims vs config defaults.
- [Auth Configuration](../../deployment/configuration.md) — Full config reference.
