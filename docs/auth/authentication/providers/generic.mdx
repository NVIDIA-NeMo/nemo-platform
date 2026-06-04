# Generic OIDC Provider

A checklist for connecting {{platform_name}} to any OIDC-compliant identity provider not covered by the [Azure AD](azure-ad.md) page.

**Prerequisites**: Familiarity with [OIDC Setup](../oidc.md).

## Provider Checklist

Verify your IdP meets these requirements:

- [ ] Supports **OpenID Connect** (not just OAuth2)
- [ ] Exposes a `.well-known/openid-configuration` discovery document
- [ ] Supports the **device authorization grant** (required for `nemo auth login`)
- [ ] Allows creating **custom API scopes** (`platform:read`, `platform:write`)
- [ ] Includes **email** (or equivalent claim) in access tokens
- [ ] Supports **JWKS** for token signature validation

## Configuration Template

```yaml
auth:
 enabled: true
 oidc:
 enabled: true
 issuer: "<your-idp-issuer-url>"
 client_id: "<your-client-id>"
 # Uncomment and adjust if your IdP uses non-standard claim names:
 # email_claim: "email"
 # subject_claim: "sub"
 # groups_claim: "groups"
 # Uncomment if your IdP prefixes scopes:
 # scope_prefix: "<prefix>/"
 default_scopes: "openid profile email offline_access platform:read platform:write"
```

## Claim Mapping Reference

| IdP | Email Claim | Subject Claim | Groups Claim |
|-----|-------------|---------------|--------------|
| Azure AD | `upn` | `oid` | `groups` |
| Okta | `email` | `sub` | `groups` |
| Keycloak | `email` | `sub` | `groups` |
| Auth0 | `email` | `sub` | custom |
| Google Workspace | `email` | `sub` | N/A |
| Generic OIDC | `email` | `sub` | `groups` |

## Related

- [OIDC Setup](../oidc.md) — Full OIDC configuration guide.
- [OIDC Setup — Claim mapping](../oidc.md#claim-mapping) — JWT claims vs config defaults.
- [Auth Configuration](../../deployment/configuration.md) — Full config reference.
