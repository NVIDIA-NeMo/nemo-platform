# Authentication

{{platform_name}} authenticates requests using **OpenID Connect (OIDC)**. You register an OAuth application in your identity provider, configure {{platform_name}} with the issuer and client ID, and users sign in via the CLI, SDK, or browser. {{platform_name}} validates the JWT on every request and extracts the user's identity for authorization.

For the quickstart (no IdP), see the [email-based shortcut](../index.md). For the authorization model, see [Authorization Concepts](../concepts.md).

## Connect Your Identity Provider

Start here — register an OAuth application in your IdP and configure {{platform_name}}:

- [OIDC Setup](oidc.md) — Step-by-step: register an app, configure {{platform_name}}, verify login.
- [Azure AD (Entra ID)](providers/azure-ad.md) — Azure-specific walkthrough (app registration, scopes, claim mapping).
- [Generic OIDC Provider](providers/generic.md) — Checklist for any OIDC-compliant IdP.

## Log In and Make API Calls

Once your IdP is connected, see [Using Authentication](using-authentication.md) for the full walkthrough: device flow login, SDK and curl examples, token management, and config file reference.

| Method | Command / Action | Best For |
|--------|-----------------|----------|
| **Device flow** (browser) | `nemo auth login` | Interactive use — opens browser to sign in with your IdP |
| **Password grant** | `nemo auth login --username <user> --password <pass>` | CI/CD pipelines — non-interactive |
| **Direct from IdP** | Use your IdP's token endpoint or workload identity | Custom integrations, service accounts |

The CLI stores the token and auto-refreshes it before expiry. The SDK reads the stored token from the CLI config automatically — after `nemo auth login`, `NeMoPlatform()` works with no arguments.

## Discovery Endpoint

{{platform_name}} exposes an unauthenticated endpoint that clients and the SDK use to discover OIDC settings:

```text
GET {BASE_URL}/apis/auth/discovery
```

Response:

```json
{
  "auth_enabled": true,
  "oidc": {
    "issuer": "https://login.microsoftonline.com/{tenant}/v2.0",
    "token_endpoint": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    "device_authorization_endpoint": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
    "client_id": "...",
    "default_scopes": "platform:read platform:write openid profile email offline_access",
    "scope_prefix": "api://nmp/"
  }
}
```

The CLI and SDK call this endpoint automatically during `nemo auth login` or when initializing the client.

## Related

- [Using Authentication](using-authentication.md) — Log in, make API calls, and manage tokens.
- [Security Model](../security-model.md) — Trust boundaries and the principal model.
