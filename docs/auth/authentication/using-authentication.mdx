# Using Authentication

How to log in, make authenticated API calls, and manage tokens with the CLI and SDK.

**Prerequisites**: OIDC must be configured on the platform. See [OIDC Setup](oidc.md).

## Log In

The device flow is the recommended login method. It opens your browser to authenticate with your organization's identity provider.

```bash
nemo auth login
```

Expected output:

```text
To sign in, use a web browser to open the page https://microsoft.com/devicelogin
and enter the code ABCD-EFGH to authenticate.
Waiting for authentication...
```

Open the URL, enter the code, and sign in with your IdP credentials. After consent, verify:

```bash
nemo auth status
```

```text
Logged in as alice@company.com
Scopes: platform:read platform:write
Token expires: 2026-02-15T14:30:00Z
```

All CLI and SDK commands now use the stored token automatically.

### Requesting Specific Scopes

By default, the CLI requests the scopes configured in `auth.oidc.default_scopes` (typically `platform:read platform:write` plus OIDC standard scopes like `openid profile email offline_access`). Restrict the token's access by specifying fewer scopes:

```bash
nemo auth login --scope "platform:read"
```

See [API Scopes](../authorization/api-scopes.md) for the full list of available scopes.

### Non-Interactive Login (CI/CD)

For CI pipelines, use the password grant to obtain a token without a browser: `nemo auth login --username <user> --password <pass>` (or set `NMP_OIDC_USERNAME` / `NMP_OIDC_PASSWORD` environment variables). If your CI system can obtain tokens directly (e.g., workload identity federation), pass the token via `access_token` as shown in [Make API Calls](#make-api-calls) below.

!!! warning
    Password grant sends credentials directly to the IdP and **bypasses MFA**. Many production IdPs disable it. Use a dedicated service account with minimal scopes where possible.

## Make API Calls

### Python SDK

The SDK reads credentials from the CLI config automatically — no manual token handling needed:

```python
from nemo_platform import NeMoPlatform

# After `nemo auth login` (OIDC) or `nemo auth login --unsigned-token ...` (quickstart),
# the SDK reads base_url, workspace, and the stored token from the CLI config.
# This is the recommended pattern for interactive / OIDC-authenticated usage.
client = NeMoPlatform()

workspaces = client.workspaces.list()
```

If you need explicit token control (for example, a token from a CI system or environment variable), pass it via `access_token`:

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
    access_token=os.environ.get("NMP_ACCESS_TOKEN"),
)
```

### HTTP (curl)

```bash
TOKEN=$(nemo auth token)
curl -H "Authorization: Bearer $TOKEN" \
 https://nmp.company.com/v2/workspaces
```

### Token Inspection

Retrieve the raw JWT for debugging or use in other clients:

```bash
nemo auth token
```

Decode the token to inspect claims:

```bash
nemo auth token | cut -d. -f2 | base64 -d 2>/dev/null | python -m json.tool
```

Key claims to check:

- `email` or `upn` — the principal identity
- `scp` or `scope` — granted scopes
- `exp` — expiry timestamp
- `iss` — issuer URL (must match your config)
- `aud` — audience (must match your config)

## Token Management

### How Auto-Refresh Works

You never need to refresh tokens manually — the CLI and SDK handle it transparently:

- **SDK**: Refreshes lazily before each API call when the token is within 60 seconds of expiry. No background threads or timers — the cost is paid only when a refresh is actually needed (typically once per hour). Multiple `NeMoPlatform()` clients in the same Python process share a single token, so only one refresh happens even with many clients.
- **CLI**: Checks the token before every command and refreshes if it expires within 5 minutes. To disable for a specific command: `nemo --no-auto-refresh workspaces list`.

Running multiple scripts or CLI commands simultaneously is safe — file-level locking prevents conflicts when refreshing tokens across processes.

If the refresh token itself has expired (e.g., after days of inactivity), re-login with `nemo auth login`.

### Manual Refresh and Logout

```bash
# Force a token refresh
nemo auth refresh

# Clear stored tokens
nemo auth logout
```

<a id="config-file"></a>
### Config File

Tokens are stored in `~/.config/nmp/config.yaml`:

```yaml
users:
 - type: oauth
 name: default
 token: "<access_token_jwt>"
 refresh_token: "<refresh_token>"
```

The OIDC token endpoint is **not** stored — it is discovered at runtime from your cluster's `/apis/auth/discovery` endpoint. This keeps the config portable across environments.

!!! warning
    **Token storage security** — Access and refresh tokens are stored in plaintext. Protect this file:

    - **File permissions**: Ensure `0600` (owner read/write only). The CLI sets this by default — verify after manual edits: `chmod 600 ~/.config/nmp/config.yaml`.
    - **Shared directories**: Do not store in cloud-synced folders (Dropbox, OneDrive, Google Drive) or shared home directories.
    - **Refresh token rotation**: Configure your IdP to rotate refresh tokens on each use. A stolen refresh token becomes invalid after the legitimate client uses it once.
    - **Logout when done**: Run `nemo auth logout` on shared or temporary machines.

## Related

- [OIDC Setup](oidc.md) — Configure your identity provider.
- [API Scopes](../authorization/api-scopes.md) — Scope model and available scopes.
- [Security Model](../security-model.md) — Trust boundaries and the principal model.
- [Troubleshooting](../troubleshooting.md) — Fix common 401/403 errors and login failures.
