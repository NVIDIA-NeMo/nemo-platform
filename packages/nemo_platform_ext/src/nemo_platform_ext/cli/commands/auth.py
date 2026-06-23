# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authentication commands for NeMo Platform CLI.

Scope normalization, JWT decode, and scope validation logic live in
nemo_platform_ext.auth.helpers.
"""

from __future__ import annotations

import asyncio
import time
from typing import Annotated, cast

import httpx
import typer

from nemo_platform_ext.auth.helpers import (
    AuthError,
    build_effective_scope,
    decode_jwt_claims,
    discover_nmp_config,
    generate_unsigned_jwt,
    is_unsigned_jwt,
    normalize_scope_prefix,
    validate_requested_scopes_granted,
)
from nemo_platform_ext.auth.token_provider import OIDCTokenProvider, TokenSet
from nemo_platform_ext.cli.core.context import CLIContext
from nemo_platform_ext.cli.core.errors import handle_errors
from nemo_platform_ext.cli.core.help_formatter import create_typer_app
from nemo_platform_ext.config.models import ConfigParams, Context

app = create_typer_app(
    name="auth",
    help="Manage authentication for NeMo Platform.",
)


def is_auth_disabled(base_url: str, timeout: float = 3.0) -> bool | None:
    """Check whether authentication is disabled on the cluster.

    Returns:
        True if auth is definitely disabled, False if enabled, None if unreachable.
    """
    try:
        return not discover_nmp_config(base_url, timeout=timeout).auth_enabled
    except httpx.HTTPError:
        return None


def ensure_valid_token(context: Context, refresh_buffer_seconds: int = 300) -> bool:
    """
    Check if the current token is valid and refresh if needed.

    This function should be called before making API requests to ensure
    the access token is valid. If the token is expired or about to expire
    (within refresh_buffer_seconds), it will automatically refresh using
    the stored refresh token.

    Args:
        refresh_buffer_seconds: Refresh the token if it expires within this many seconds.
            Default is 300 (5 minutes).

    Returns:
        True if a valid token is available (possibly after refresh), False otherwise.
    """
    from datetime import datetime, timezone

    from nemo_platform_ext.config.config import Config
    from nemo_platform_ext.config.models import OAuthUser

    # Only OAuthUser supports token refresh
    if not context.user or not isinstance(context.user, OAuthUser):
        return True  # Non-OAuth users don't need refresh

    # Check if token is expired or about to expire
    token = context.user.token.get_secret_value()
    claims = decode_jwt_claims(token)
    if not claims:
        # Not a JWT, can't check expiry
        return True

    exp = claims.get("exp")
    if not exp:
        return True

    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    # Token is still valid with buffer
    if exp_dt > now + __import__("datetime").timedelta(seconds=refresh_buffer_seconds):
        return True

    # Token expired or about to expire - try to refresh
    if not context.user.refresh_token:
        return exp_dt > now  # Return True only if not yet expired

    base_url = str(context.cluster.base_url).rstrip("/")
    try:
        nmp_config = discover_nmp_config(base_url)
    except httpx.HTTPError:
        return exp_dt > now

    if not nmp_config.client_id or not nmp_config.token_endpoint:
        return exp_dt > now

    effective_scope = build_effective_scope(nmp_config.default_scopes, nmp_config.scope_prefix)

    try:
        provider = OIDCTokenProvider(
            token_endpoint=nmp_config.token_endpoint,
            client_id=nmp_config.client_id,
            tokens=TokenSet.from_access_token(
                context.user.token.get_secret_value(),
                context.user.refresh_token.get_secret_value(),
            ),
            refresh_scope=effective_scope,
            refresh_margin_seconds=float(refresh_buffer_seconds),
        )
        provider.force_refresh()

        config_params = {
            "access_token": provider.tokens.access_token,
        }
        if provider.tokens.refresh_token:
            config_params["refresh_token"] = provider.tokens.refresh_token

        Config.write(config_params, context_name=context.context_name)  # type: ignore[arg-type]
        typer.echo("[Auto-refreshed expired token]", err=True)

        return True
    except Exception:
        return exp_dt > now


@app.callback(invoke_without_command=True)
def auth_callback(ctx: typer.Context) -> None:
    """Manage authentication for NeMo Platform."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("login")
@handle_errors
def login(
    ctx: typer.Context,
    context_name: Annotated[
        str | None,
        typer.Option(
            "--context",
            help="Context to use for this login command.",
        ),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            help="Set cluster base URL for the selected context before login",
        ),
    ] = None,
    no_browser: Annotated[
        bool,
        typer.Option("--no-browser", help="Don't open browser (device flow only)"),
    ] = False,
    scope: Annotated[
        str | None,
        typer.Option(
            "--scope",
            help='OAuth scopes to request (space-separated; quote for multiple, e.g. --scope "platform:read secrets:write")',
        ),
    ] = None,
    username: Annotated[
        str | None,
        typer.Option("--username", help="Username for password grant (CI / non-interactive)"),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", help="Password for password grant (prefer env NMP_OIDC_PASSWORD)"),
    ] = None,
    unsigned_token: Annotated[
        bool,
        typer.Option(
            "--unsigned-token",
            help="Generate and save an unsigned JWT for local/testing authentication.",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = False,
    principal_id: Annotated[
        str | None,
        typer.Option(
            "--principal-id",
            help="Principal ID for the unsigned token (`sub` claim). Defaults to --email.",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = None,
    email: Annotated[
        str | None,
        typer.Option(
            "--email",
            help="Email claim for the unsigned token (required with --unsigned-token).",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = None,
    groups: Annotated[
        list[str] | None,
        typer.Option(
            "--group",
            help="Group claim value for unsigned token (repeat for multiple).",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = None,
    expires_in: Annotated[
        int,
        typer.Option(
            "--expires-in",
            help="Unsigned token expiry in seconds from now.",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = 3600,
    no_exp: Annotated[
        bool,
        typer.Option(
            "--no-exp",
            help="Omit the exp claim from the unsigned token.",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = False,
    audience: Annotated[
        str | None,
        typer.Option(
            "--audience",
            help="Audience (`aud`) claim for unsigned token.",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = None,
    issuer: Annotated[
        str | None,
        typer.Option(
            "--issuer",
            help="Issuer (`iss`) claim for unsigned token.",
            rich_help_panel="Unsigned Token Options",
        ),
    ] = None,
) -> None:
    """Authenticate with the NeMo Platform cluster.

    Uses device flow (browser) by default, or password grant when username and password are provided (e.g. for CI).

    For quickstart, use [cyan]`--unsigned-token`[/] to generate an unsigned JWT.

    Examples:
    # Set base URL and log in
    nemo auth login --base-url https://nemo.example.com
    # Context-specific login
    nemo auth login --context dev --base-url https://nemo.dev.example.com
    # Device flow, open browser
    nemo auth login
    # Device flow, show code only
    nemo auth login --no-browser
    """
    import os

    from rich.console import Console

    from nemo_platform_ext.auth.device_flow import (
        DeviceFlowError,
        authenticate_with_device_flow,
        authenticate_with_password_grant,
    )
    from nemo_platform_ext.config.config import Config

    cli_context: CLIContext = ctx.obj
    selected_context = cast(str | None, cli_context.overrides.get("current_context"))

    if context_name is not None:
        selected_context = context_name
        cli_context.overrides["current_context"] = context_name
        cli_context.reset_sdk_context()

    if base_url is not None:
        base_url_params: ConfigParams = {"base_url": base_url}
        if selected_context is not None:
            base_url_params["current_context"] = selected_context
        try:
            Config.write(base_url_params, context_name=selected_context)
        except Exception as exc:
            context_label = selected_context or "default"
            raise AuthError(f"Failed to set base URL for context '{context_label}': {exc}") from exc
        cli_context.reset_sdk_context()

    console = Console()

    unsigned_option_flags = {
        "principal_id": "--principal-id",
        "email": "--email",
        "groups": "--group",
        "expires_in": "--expires-in",
        "no_exp": "--no-exp",
        "audience": "--audience",
        "issuer": "--issuer",
    }

    if not unsigned_token:
        from click.core import ParameterSource

        unsigned_options_used = [
            flag
            for param_name, flag in unsigned_option_flags.items()
            if ctx.get_parameter_source(param_name) != ParameterSource.DEFAULT
        ]
        if unsigned_options_used:
            raise AuthError(f"Unsigned token option(s) {', '.join(unsigned_options_used)} require --unsigned-token.")

    if unsigned_token:
        if username or password:
            raise AuthError("Cannot combine --unsigned-token with --username/--password.")
        if email is None:
            raise AuthError("--email is required when using --unsigned-token.")

        effective_principal_id = principal_id or email

        context = cli_context.get_sdk_context()
        base_url = str(context.cluster.base_url).rstrip("/")

        try:
            oidc_config = discover_nmp_config(base_url)
            oidc_login_configured = bool(oidc_config.token_endpoint and oidc_config.client_id)
            if oidc_login_configured:
                raise AuthError(
                    "Cluster has OIDC authentication configured. Use 'nemo auth login' instead of '--unsigned-token'."
                )
            if oidc_config.auth_enabled:
                console.print(
                    "Cluster authentication is enabled. Ensure [cyan]auth.allow_unsigned_jwt=true[/] on the cluster."
                )
        except httpx.HTTPError:
            console.print("[yellow]Could not verify cluster auth settings via discovery endpoint.[/]")

        requested_scopes = scope.split() if scope else None
        token = generate_unsigned_jwt(
            principal_id=effective_principal_id,
            email=email,
            groups=groups,
            scopes=requested_scopes,
            expires_in_seconds=None if no_exp else expires_in,
            audience=audience,
            issuer=issuer,
        )

        config_params: ConfigParams = {"access_token": token}
        if selected_context is not None:
            config_params["current_context"] = context.context_name
        Config.write(config_params, context_name=context.context_name)

        console.print("\n[bold yellow]Warning:[/] Generated an unsigned JWT (`alg=none`).")
        console.print("Use this only for local/testing environments.")

        console.print("\n[bold green]Unsigned token saved to config file.[/]")
        console.print(f"Principal: [cyan]{effective_principal_id}[/]")
        console.print("\n[dim]Run 'nemo auth status' to inspect the token.[/]")
        return

    context = cli_context.get_sdk_context()
    base_url = str(context.cluster.base_url).rstrip("/")

    console.print(f"\nDiscovering auth configuration from {base_url}...")

    try:
        oidc_config = discover_nmp_config(base_url)
    except httpx.HTTPError as exc:
        raise AuthError(f"Failed to discover auth configuration: {exc}") from exc

    if not oidc_config.auth_enabled:
        console.print("[yellow]Authentication is not enabled on this cluster.[/]")
        console.print("You can use the API without authentication.")
        raise typer.Exit(0)

    if not oidc_config.token_endpoint:
        raise AuthError(
            "This cluster does not have OIDC token endpoint configured.\n"
            "Use OIDC configuration for device/password login, or for local testing use:\n"
            "nemo auth login --unsigned-token --email <email>"
        )

    login_username = username or os.environ.get("NMP_OIDC_USERNAME")
    login_password = password or os.environ.get("NMP_OIDC_PASSWORD")
    use_password_grant = bool(login_username and login_password)

    if use_password_grant:
        if not oidc_config.client_id:
            raise AuthError("OIDC client_id is required for password grant.")
    else:
        if not oidc_config.device_authorization_endpoint:
            raise AuthError(
                "This cluster does not support device flow authentication.\n"
                "For non-interactive login use: nemo auth login --username <user> --password <pass>\n"
                "Or set NMP_OIDC_USERNAME and NMP_OIDC_PASSWORD (e.g. in CI)."
            )

    console.print(f"[green]Found OIDC configuration[/] (issuer: {oidc_config.issuer})")

    # Use only generic scopes from cluster defaults (exclude platform/custom scopes like platform:read)
    # so platform scopes come only from --scope. Merge with --scope if provided.
    raw_defaults = oidc_config.default_scopes
    default_baseline = " ".join(s for s in raw_defaults.split() if ":" not in s)
    if scope:
        seen: set[str] = set()
        parts: list[str] = []
        for s in default_baseline.split():
            if s not in seen:
                seen.add(s)
                parts.append(s)
        for s in scope.split():
            if s not in seen:
                seen.add(s)
                parts.append(s)
        requested_scopes = " ".join(parts)
    else:
        requested_scopes = raw_defaults

    scope_prefix = normalize_scope_prefix(oidc_config.scope_prefix)
    effective_scope = build_effective_scope(requested_scopes, oidc_config.scope_prefix)

    # Display the scopes being requested
    console.print("\n[bold]Requesting scopes:[/]")
    for s in requested_scopes.split():
        if scope_prefix and (":" in s or s.endswith(".default")):
            console.print(f"  [cyan]{s}[/] [dim]({scope_prefix}{s})[/]")
        else:
            console.print(f"  [cyan]{s}[/]")
    console.print()

    if use_password_grant:
        if login_username is None or login_password is None:
            raise AuthError("Username and password are required for password grant.")
        client_id = cast(str, oidc_config.client_id)
        try:
            token_response = authenticate_with_password_grant(
                token_endpoint=oidc_config.token_endpoint,
                client_id=client_id,
                username=login_username,
                password=login_password,
                scope=effective_scope,
            )
        except DeviceFlowError as exc:
            raise AuthError(f"Authentication failed: {exc}") from exc
    else:
        if oidc_config.device_authorization_endpoint is None:
            raise AuthError("This cluster does not support device flow authentication.")
        client_id = cast(str, oidc_config.client_id)
        device_authorization_endpoint = oidc_config.device_authorization_endpoint
        try:
            token_response = asyncio.run(
                authenticate_with_device_flow(
                    device_authorization_endpoint=device_authorization_endpoint,
                    token_endpoint=oidc_config.token_endpoint,
                    client_id=client_id,
                    scope=effective_scope,
                    open_browser=not no_browser,
                )
            )
        except DeviceFlowError as exc:
            raise AuthError(f"Authentication failed: {exc}") from exc

    token = token_response.token_for_nmp

    claims = decode_jwt_claims(token)
    user_email = claims.get("upn") or claims.get("email") or claims.get("preferred_username")
    raw_granted_scopes = claims.get("scp") or claims.get("scope")
    granted_scopes: list[str] = []
    if isinstance(raw_granted_scopes, str):
        granted_scopes = raw_granted_scopes.split()
    elif isinstance(raw_granted_scopes, list):
        granted_scopes = [scope for scope in raw_granted_scopes if isinstance(scope, str)]

    validate_requested_scopes_granted(effective_scope, granted_scopes, scope_prefix)

    config_params: ConfigParams = {"access_token": token}
    if token_response.refresh_token:
        config_params["refresh_token"] = token_response.refresh_token
    if selected_context is not None:
        config_params["current_context"] = context.context_name
    Config.write(config_params, context_name=context.context_name)

    console.print("\n[bold green]Authentication successful![/]")
    if user_email:
        console.print(f"  Logged in as: [cyan]{user_email}[/]")

    if granted_scopes:
        # Normalize scopes by stripping prefix for display
        display_scopes = []
        for s in granted_scopes:
            if scope_prefix and s.startswith(scope_prefix):
                display_scopes.append(s[len(scope_prefix) :])
            else:
                display_scopes.append(s)
        console.print(f"  Granted scopes: [cyan]{' '.join(display_scopes)}[/]")

    if token_response.refresh_token:
        console.print("  Refresh token: [green]saved[/] (enables automatic token renewal)")
    else:
        console.print("  Refresh token: [yellow]not available[/] (add 'offline_access' scope to enable)")

    console.print("\n[bold green]Credentials saved to config file.[/]")
    console.print("\n[dim]Run 'nemo workspaces list' to verify your access.[/]")


@app.command("logout")
@handle_errors
def logout(ctx: typer.Context) -> None:
    """Remove stored credentials for the current context."""
    from rich.console import Console

    from nemo_platform_ext.config.config import Config

    cli_context: CLIContext = ctx.obj
    context = cli_context.get_sdk_context()

    console = Console()

    base_url = str(context.cluster.base_url).rstrip("/")
    if is_auth_disabled(base_url) is True:
        console.print("[yellow]Authentication is disabled on this cluster — nothing to log out from.[/]")
        return

    logout_params: ConfigParams = {"access_token": None, "refresh_token": None}
    Config.write(logout_params, context_name=context.context_name)
    console.print("[green]Logged out successfully.[/]")


@app.command("refresh")
@handle_errors
def refresh(ctx: typer.Context) -> None:
    """Refresh the current access token.

    This command uses the saved refresh token to obtain a new access token without requiring you to re-authenticate through the browser.
    """
    from rich.console import Console

    from nemo_platform_ext.config.config import Config
    from nemo_platform_ext.config.models import OAuthUser

    cli_context: CLIContext = ctx.obj
    context = cli_context.get_sdk_context()

    console = Console()

    # Only OAuthUser stores tokens in config
    if not context.user or not isinstance(context.user, OAuthUser):
        raise AuthError("No OAuth authentication configured. Run 'nemo auth login' first.")

    token_value = context.user.token.get_secret_value()

    if is_unsigned_jwt(token_value):
        claims = decode_jwt_claims(token_value)
        principal_id = claims.get("sub")
        if not isinstance(principal_id, str) or not principal_id:
            raise AuthError("Unsigned token is missing required 'sub' claim.")

        email_claim = claims.get("email")
        email = email_claim if isinstance(email_claim, str) else None

        groups_claim = claims.get("groups")
        if isinstance(groups_claim, str):
            groups = [groups_claim]
        elif isinstance(groups_claim, list) and all(isinstance(group, str) for group in groups_claim):
            groups = groups_claim or None
        else:
            groups = None

        scope_claim = claims.get("scope")
        scopes = scope_claim.split() if isinstance(scope_claim, str) and scope_claim else None

        expires_in_seconds = None
        exp_claim = claims.get("exp")
        iat_claim = claims.get("iat")
        if isinstance(exp_claim, int):
            if isinstance(iat_claim, int):
                expires_in_seconds = max(exp_claim - iat_claim, 0)
            else:
                expires_in_seconds = max(exp_claim - int(time.time()), 0)

        audience = claims.get("aud") if isinstance(claims.get("aud"), str) else None
        issuer = claims.get("iss") if isinstance(claims.get("iss"), str) else None

        excluded_claims = {
            "sub",
            "email",
            "groups",
            "scope",
            "iat",
            "exp",
            "aud",
            "iss",
        }
        extra_claims = {k: v for k, v in claims.items() if k not in excluded_claims}
        if "aud" in claims and not isinstance(claims.get("aud"), str):
            extra_claims["aud"] = claims.get("aud")

        refreshed_token = generate_unsigned_jwt(
            principal_id=principal_id,
            email=email,
            groups=groups,
            scopes=scopes,
            expires_in_seconds=expires_in_seconds,
            audience=audience,
            issuer=issuer,
            extra_claims=extra_claims or None,
        )

        Config.write(
            cast(ConfigParams, {"access_token": refreshed_token, "refresh_token": None}),
            context_name=context.context_name,
        )

        refreshed_claims = decode_jwt_claims(refreshed_token)
        exp = refreshed_claims.get("exp")
        if exp:
            from datetime import datetime, timezone

            exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            console.print(f"[green]Unsigned token refreshed successfully![/] Expires: {exp_dt.isoformat()}")
        else:
            console.print("[green]Unsigned token refreshed successfully![/]")
        return

    if not context.user.refresh_token:
        raise AuthError("No refresh token available. Re-run 'nemo auth login' with 'offline_access' scope.")

    # Fetch client_id from cluster discovery
    base_url = str(context.cluster.base_url).rstrip("/")
    try:
        oidc_config = discover_nmp_config(base_url)
    except httpx.HTTPError as e:
        raise AuthError(f"Failed to discover auth configuration: {e}")

    if not oidc_config.client_id or not oidc_config.token_endpoint:
        raise AuthError("OIDC not configured on cluster.")

    effective_scope = build_effective_scope(oidc_config.default_scopes, oidc_config.scope_prefix)

    console.print("Refreshing access token...")

    provider = OIDCTokenProvider(
        token_endpoint=oidc_config.token_endpoint,
        client_id=oidc_config.client_id,
        tokens=TokenSet.from_access_token(
            context.user.token.get_secret_value(),
            context.user.refresh_token.get_secret_value(),
        ),
        refresh_scope=effective_scope,
    )

    try:
        provider.force_refresh()
    except RuntimeError as e:
        raise AuthError(f"Token refresh failed: {e}") from e

    # Save new tokens (refresh token may be rotated)
    config_params = {"access_token": provider.tokens.access_token}
    if provider.tokens.refresh_token:
        config_params["refresh_token"] = provider.tokens.refresh_token
    Config.write(config_params, context_name=context.context_name)  # type: ignore[arg-type]

    # Show new token info
    claims = decode_jwt_claims(provider.tokens.access_token)
    exp = claims.get("exp")
    if exp:
        from datetime import datetime, timezone

        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        console.print(f"[green]Token refreshed successfully![/] Expires: {exp_dt.isoformat()}")
    else:
        console.print("[green]Token refreshed successfully![/]")


@app.command("token")
@handle_errors
def token(ctx: typer.Context) -> None:
    """Print the current access token (for use with SDK or curl).

    This outputs the raw token to stdout, suitable for piping or capture.

    Examples:
    # Print token
    nemo auth token
    # Capture in env var
    export TOKEN=$(nemo auth token)
    curl -H "Authorization: Bearer $(nemo auth token)" ...
    """
    from nemo_platform_ext.config.models import OAuthUser

    cli_context: CLIContext = ctx.obj
    context = cli_context.get_sdk_context()

    if not context.user:
        raise AuthError("No authentication configured. Run 'nemo auth login' first.")

    if isinstance(context.user, OAuthUser):
        typer.echo(context.user.token.get_secret_value())
    else:
        raise AuthError("No token available for current user type.")


@app.command("status")
@handle_errors
def status(ctx: typer.Context) -> None:
    """Show current authentication status."""
    from datetime import datetime, timezone

    from rich.console import Console
    from rich.table import Table

    from nemo_platform_ext.config.models import OAuthUser

    cli_context: CLIContext = ctx.obj
    context = cli_context.get_sdk_context()

    console = Console()

    # Check whether the cluster has auth enabled before showing token details.
    base_url = str(context.cluster.base_url).rstrip("/")
    if is_auth_disabled(base_url) is True:
        console.print()
        console.print(f"[cyan]Cluster:[/] {base_url}")
        console.print(f"[cyan]Context:[/] {context.context_name}")
        console.print()
        console.print("[green]Authentication is disabled on this cluster.[/]")
        console.print("All API requests are accepted without credentials.")
        return

    table = Table(title="Authentication Status", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Cluster", str(context.cluster.base_url))
    table.add_row("Context", context.context_name)

    if context.user:
        table.add_row("Auth Type", context.user.type)

        if isinstance(context.user, OAuthUser):
            # OAuth token authentication
            token_value = context.user.token.get_secret_value()
            if is_unsigned_jwt(token_value):
                table.add_row("Warning", "[yellow]Unsigned JWT (alg=none). Use only for local/testing.[/]")

            claims = decode_jwt_claims(token_value)

            if claims:
                # Show decoded JWT info
                email = claims.get("upn") or claims.get("email") or claims.get("preferred_username")
                if email:
                    table.add_row("Email", email)

                subject = claims.get("oid") or claims.get("sub")
                if subject:
                    table.add_row("User ID", subject)

                scopes = claims.get("scp") or claims.get("scope") or ""
                if isinstance(scopes, str):
                    scopes = scopes.split()
                if scopes:
                    table.add_row("Scopes", " ".join(scopes))
                else:
                    table.add_row("Scopes", "[dim]none[/]")

                groups = claims.get("groups") or claims.get("cognito:groups") or []
                if isinstance(groups, str):
                    groups = [groups]
                if groups:
                    table.add_row("Groups", ", ".join(groups))

                exp = claims.get("exp")
                if exp:
                    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
                    now = datetime.now(tz=timezone.utc)
                    if exp_dt > now:
                        remaining = exp_dt - now
                        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                        minutes, _ = divmod(remainder, 60)
                        table.add_row("Expires", f"{exp_dt.isoformat()} ({hours}h {minutes}m remaining)")
                    else:
                        table.add_row("Expires", f"[red]EXPIRED[/] ({exp_dt.isoformat()})")

            # Show refresh token status
            if context.user.refresh_token:
                table.add_row("Refresh Token", "[green]available[/] (run 'nemo auth refresh' to renew)")
            else:
                table.add_row("Refresh Token", "[yellow]not available[/]")

            # Show redacted token
            redacted = f"{token_value[:20]}...{token_value[-10:]}" if len(token_value) > 30 else "***"
            table.add_row("Token", redacted)

    else:
        table.add_row("User", "None")
        table.add_row("Auth Type", "no-auth")

    console.print()
    console.print(table)
