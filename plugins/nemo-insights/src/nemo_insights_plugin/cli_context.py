# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared CLI-context resolution for the ``nemo insights`` command group.

The base URL a command talks to comes from the shared CLI context object
on ``typer.Context.obj``, so ``nemo insights`` targets the same deployment
as every other ``nemo`` command.

Reading the *ambient* Click context (rather than re-reading the config file)
is what makes the global ``nemo --base-url ...`` and ``nemo --context ...``
flags apply here: the root callback stashes them as overrides on that object,
and they are invisible to a fresh config load.
"""

import logging
from collections.abc import Callable
from typing import Annotated, Any

import click
import typer
from nemo_insights_plugin.contracts.profile import DEFAULT_BASE_URL

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = "default"

BASE_URL_HELP = (
    "Base URL of the running NMP instance. Resolution order: "
    "(1) this --base-url flag or NMP_BASE_URL; "
    "(2) the active CLI context, including a global `nemo --base-url` / `--context` "
    "and `nemo config set --base-url`; "
    f"(3) {DEFAULT_BASE_URL}."
)

WORKSPACE_HELP = (
    "Workspace to operate in. Resolution order: "
    "(1) this --workspace flag or NMP_WORKSPACE; "
    "(2) the active CLI context, including a global `nemo --context` "
    "and `nemo config set --workspace`; "
    f"(3) the {DEFAULT_WORKSPACE!r} workspace."
)

# One definition of the option so its flag, env var and help text cannot drift
# between commands. ``None`` means "unset", which lets ``resolve_base_url``
# fall through to the CLI context.
BaseUrlOption = Annotated[
    str | None,
    typer.Option("--base-url", envvar="NMP_BASE_URL", help=BASE_URL_HELP),
]

# Likewise for the workspace. Every insights command means the same thing by
# it, so one definition keeps the six help strings from drifting apart.
WorkspaceOption = Annotated[
    str | None,
    typer.Option("--workspace", envvar="NMP_WORKSPACE", help=WORKSPACE_HELP),
]


def current_cli_state() -> Any:
    """Return the shared CLI context object (``typer.Context.obj``) if present.

    ``None`` when the plugin runs outside a Click invocation — a direct unit
    test, or the analyst job runtime — so callers fall back to their own
    defaults instead of failing.
    """
    ctx = click.get_current_context(silent=True)
    return ctx.obj if ctx is not None else None


def _from_sdk_context(read: Callable[[Any], str | None], what: str) -> str | None:
    """Read one value off the shared CLI context, or None when unavailable.

    Resolves the SDK context directly rather than through helpers like
    ``get_base_url``, which report every failure as "nothing here". That would
    turn a deliberate abort — ``--context`` naming a context that does not
    exist — into a silent fallback onto whatever the default context says.
    """
    state = current_cli_state()
    if state is None or not hasattr(state, "get_sdk_context"):
        return None
    try:
        return read(state.get_sdk_context())
    except (click.exceptions.Exit, click.exceptions.Abort):
        # The CLI is exiting on purpose and has already said why; re-raise so
        # the command fails instead of quietly using somewhere else.
        raise
    except Exception:
        logger.debug("Failed to resolve %s from CLI context", what, exc_info=True)
        return None


def base_url_from_context() -> str | None:
    """Return the base URL held by the shared CLI context, if any."""
    return _from_sdk_context(lambda ctx: str(ctx.cluster.base_url), "base URL")


def workspace_from_context() -> str | None:
    """Return the workspace held by the shared CLI context, if any."""
    return _from_sdk_context(lambda ctx: ctx.workspace, "workspace")


def active_context_base_url() -> str:
    """Return the base URL of the active ``nemo config`` context.

    Prefers the ambient CLI context so global flags win, and falls back to a
    direct config read for callers with no Click context of their own. When
    there is no usable config at all — no file, an unreadable one, or a
    context naming a missing cluster — this yields :data:`DEFAULT_BASE_URL`.
    A caller reaching here has already run out of explicit sources, so a
    broken config should not be more fatal than an absent one.
    """
    from_context = base_url_from_context()
    if from_context is not None:
        return from_context.rstrip("/")

    # Imported lazily: the platform config package pulls in the whole CLI
    # config stack, which a plain `nemo insights --help` should not pay for.
    from nemo_platform_ext.config.config import get_context

    try:
        base_url = get_context().cluster.base_url
    except (ValueError, OSError):
        # ValueError covers an unparsable or internally inconsistent config
        # (Config.load wraps YAML errors); OSError covers an NMP_CONFIG_FILE
        # pointing at a file that is missing or unreadable.
        return DEFAULT_BASE_URL
    # pydantic's HttpUrl appends a trailing slash to a bare host; that is an
    # artifact of the model, not something the user configured.
    return str(base_url).rstrip("/")


def active_context_workspace() -> str:
    """Return the workspace of the active ``nemo config`` context.

    Same shape as :func:`active_context_base_url`: ambient CLI context first
    so global flags win, then a direct config read, then the built-in default.
    """
    from_context = workspace_from_context()
    if from_context:
        return from_context

    from nemo_platform_ext.config.config import get_context

    try:
        return get_context().workspace or DEFAULT_WORKSPACE
    except (ValueError, OSError):
        return DEFAULT_WORKSPACE


def resolve_workspace(explicit: str | None) -> str:
    """Apply explicit-flag, then active-context precedence for the workspace.

    NMP_WORKSPACE is handled by Typer's ``envvar`` on the flag and again by
    the config layer, so it lands ahead of the context either way.
    """
    return explicit if explicit is not None else active_context_workspace()
