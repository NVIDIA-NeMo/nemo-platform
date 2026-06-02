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

### Choose a Context or Base URL

`nemo auth login` writes credentials to the current CLI context. If you work against multiple clusters, select the target context first or override it on the command line:

```bash
# Use an existing context
nemo --context staging auth login

# Set the base URL while logging in
nemo auth login --context staging --base-url https://nmp.staging.example.com
```

After login, `nemo auth status` shows the cluster and context that own the stored token.

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

This is the same config file the CLI uses. In practice, the common interactive flow is:

1. Run `nemo auth login`
2. Verify with `nemo auth status`
3. Construct `NeMoPlatform()` with no auth arguments
4. Let the SDK refresh tokens transparently when needed

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

### Token Lifecycle at a Glance

For OIDC login, the CLI stores:

- an **access token** used on API requests
- a **refresh token** if the IdP returned one
- the active **context** and cluster base URL in the same config file

The normal lifecycle is:

1. `nemo auth login` discovers OIDC settings from `{BASE_URL}/apis/auth/discovery`
2. the CLI exchanges your device-flow or password-grant login for an access token
3. if the IdP also returns a refresh token, the CLI stores it and later uses it to renew the access token
4. the CLI and SDK keep reusing that stored token pair until you run `nemo auth logout` or the refresh path stops working

If you log in with an unsigned quickstart token instead of OIDC, there is no refresh token. `nemo auth refresh` simply reissues another unsigned token with the same claims.

### How Auto-Refresh Works

You never need to refresh tokens manually — the CLI and SDK handle it transparently:

- **SDK**: Refreshes lazily before each API call when the token is within 60 seconds of expiry. No background threads or timers — the cost is paid only when a refresh is actually needed (typically once per hour). Multiple `NeMoPlatform()` clients in the same Python process share a single token, so only one refresh happens even with many clients.
- **CLI**: Checks the token before every command and refreshes if it expires within 5 minutes. To disable for a specific command: `nemo --no-auto-refresh workspaces list`.

Running multiple scripts or CLI commands simultaneously is safe — file-level locking prevents conflicts when refreshing tokens across processes, and the SDK reloads shared tokens before retrying a refresh. That matters when one process rotates the refresh token and another process is still holding an older copy.

### Refresh Token Expectations

Automatic renewal depends on your IdP returning a refresh token. In practice that usually means:

- the cluster's configured default scopes include `offline_access`, or
- you requested `offline_access` explicitly during login

If `offline_access` is missing, login still succeeds, but the CLI prints `Refresh token: not available` and the token will stop working once the access token expires.

Check the current state with:

```bash
nemo auth status
```

Look for:

- `Refresh Token: available` if silent renewal is configured correctly
- `Refresh Token: not available` if you need to log in again with `offline_access`

### Manual Refresh, Re-Auth, and Logout

Use manual refresh when you want to force rotation immediately instead of waiting for the next command or SDK call:

```bash
# Force a token refresh using the stored refresh token
nemo auth refresh

# Print the current access token
nemo auth token

# Remove stored credentials for the current context
nemo auth logout
```

Re-authenticate with `nemo auth login` instead of `nemo auth refresh` when:

- `nemo auth status` shows no refresh token
- the refresh token has expired because of long inactivity
- the IdP revoked the refresh token or consent changed
- you need different scopes than the ones currently granted

For example, if you originally logged in with read-only access:

```bash
nemo auth login --scope "platform:read"
```

and later need write access, re-run login with the broader scope request instead of expecting `nemo auth refresh` to change the granted scopes.

### When Refresh Fails

The common recovery paths are:

- **No refresh token available**: re-run `nemo auth login` and ensure `offline_access` is requested
- **Refresh token expired or revoked**: run `nemo auth login` again
- **Cluster OIDC configuration changed**: run `nemo auth login` again so the CLI re-discovers the token endpoint and client settings
- **Wrong context**: switch to the intended context and inspect with `nemo auth status`

<a id="config-file"></a>
### Config File

By default, tokens are stored in `~/.config/nmp/config.yaml`:

```yaml
users:
 - type: oauth
 name: default
 token: "<access_token_jwt>"
 refresh_token: "<refresh_token>"
```

You can override the location with `NMP_CONFIG_FILE=/path/to/config.yaml`, which is useful in CI, containers, or when you want isolated credentials for separate automation jobs.

The OIDC token endpoint is **not** stored — it is discovered at runtime from your cluster's `/apis/auth/discovery` endpoint. This keeps the config portable across environments and lets the CLI/SDK pick up cluster-side OIDC changes on the next login or refresh.

Each context stores its own user entry, so logging into `staging` does not overwrite the token for `prod` unless both contexts point at the same user record.

!!! warning
    **Token storage security** — Access and refresh tokens are stored in plaintext. Protect this file:

    - **File permissions**: Ensure `0600` (owner read/write only). The CLI sets this by default — verify after manual edits: `chmod 600 ~/.config/nmp/config.yaml`.
    - **Shared directories**: Do not store in cloud-synced folders (Dropbox, OneDrive, Google Drive) or shared home directories.
    - **Refresh token rotation**: Configure your IdP to rotate refresh tokens on each use. A stolen refresh token becomes invalid after the legitimate client uses it once.
    - **Logout when done**: Run `nemo auth logout` on shared or temporary machines.

## Troubleshooting Pointers

Start with:

```bash
nemo auth status
```

Then use the result to choose the next step:

- **`Authentication is disabled on this cluster`**: you do not need OIDC credentials for that target
- **`Refresh Token: not available`**: log in again and ensure `offline_access` is requested
- **`Expires: EXPIRED`** and commands still fail: run `nemo auth login`
- **wrong cluster or context**: switch contexts or re-run `nemo auth login --context ... --base-url ...`

For broader 401/403 and IdP-specific failures, see [Troubleshooting](../troubleshooting.md).

## Related

- [OIDC Setup](oidc.md) — Configure your identity provider.
- [API Scopes](../authorization/api-scopes.md) — Scope model and available scopes.
- [Security Model](../security-model.md) — Trust boundaries and the principal model.
- [Troubleshooting](../troubleshooting.md) — Fix common 401/403 errors and login failures.
