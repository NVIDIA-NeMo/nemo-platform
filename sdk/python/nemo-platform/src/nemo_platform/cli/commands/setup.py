# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Interactive setup wizard for NeMo Platform.

Full onboarding flow: start local services, register an inference provider,
install AI agent skills, and optionally deploy a demo agent.
Supports both interactive and non-interactive (``--auto``) modes.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import httpx
import typer
import yaml as _yaml
from nemo_platform import NeMoPlatform
from nmp.common.config import nmp_user_data_dir
from rich import box
from rich.console import Console
from rich.panel import Panel

from nemo_platform.cli.commands.skills.base import Scope, Skill
from nemo_platform.cli.commands.skills.registry import get_installer, load_skills
from nemo_platform.cli.core.context import CLIContext
from nemo_platform.cli.core.errors import handle_errors
from nemo_platform.config.config import Config
from nemo_platform.config.models import ConfigFile, ConfigParams, LocalServicesConfig
from nemo_platform.ui.prompts import (
    UserCancelled,
    is_interactive,
    non_empty_validator,
    prompt_choice,
    prompt_confirm,
    prompt_multiselect,
    prompt_password,
    prompt_select,
    prompt_text,
    provider_name_validator,
)

logger = logging.getLogger(__name__)
console = Console(stderr=True)

CHECK = "[green]✓[/green]"
CROSS = "[red]✗[/red]"
WARN = "[yellow]![/yellow]"

# ---------------------------------------------------------------------------
# Known provider catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnownProvider:
    """A well-known inference provider with pre-configured connection details."""

    name: str
    label: str
    description: str
    host_url: str
    auth_header_format: str | None = None
    default_extra_headers: dict[str, str] | None = None
    env_var: str | None = None
    requires_api_key: bool = True


KNOWN_PROVIDERS: tuple[KnownProvider, ...] = (
    KnownProvider(
        name="nvidia-build",
        label="NVIDIA Build",
        description="NVIDIA-hosted models via build.nvidia.com",
        host_url="https://integrate.api.nvidia.com",
        env_var="NVIDIA_API_KEY",
    ),
    KnownProvider(
        name="openai",
        label="OpenAI",
        description="GPT-4.1, o3, o4-mini",
        host_url="https://api.openai.com/v1",
        env_var="OPENAI_API_KEY",
    ),
    KnownProvider(
        name="anthropic",
        label="Anthropic",
        description="Claude Opus 4, Sonnet 4, Haiku",
        host_url="https://api.anthropic.com",
        auth_header_format="X-Api-Key: {{ auth_secret }}",
        default_extra_headers={"anthropic-version": "2023-06-01"},
        env_var="ANTHROPIC_API_KEY",
    ),
    KnownProvider(
        name="google-gemini",
        label="Google Gemini",
        description="Gemini 2.5 Flash, Pro",
        host_url="https://generativelanguage.googleapis.com/v1beta/openai",
        env_var="GEMINI_API_KEY",
    ),
    KnownProvider(
        name="ollama",
        label="Ollama (local)",
        description="Local models, no API key needed",
        host_url="http://localhost:11434/v1",
        requires_api_key=False,
    ),
)

_KNOWN_PROVIDERS_BY_NAME: dict[str, KnownProvider] = {p.name: p for p in KNOWN_PROVIDERS}

# ---------------------------------------------------------------------------
# Onboarding paths — shown after setup completes
# ---------------------------------------------------------------------------


_NEMO_DOCS_URL = "https://nvidia-nemo.github.io/nemo-platform/main/"


@dataclass(frozen=True)
class OnboardingPath:
    """A goal-oriented onboarding option shown at the end of interactive setup."""

    value: str
    label: str
    skill_prompt: str
    docs_url: str
    note: str | None = None


ONBOARDING_PATHS: tuple[OnboardingPath, ...] = (
    OnboardingPath(
        value="optimize",
        label="Build and optimize agents",
        skill_prompt="Build and optimize an agent using NeMo Platform",
        docs_url=f"{_NEMO_DOCS_URL}/agents",
        note="Open a coding agent session in your agent's project directory",
    ),
    OnboardingPath(
        value="explore",
        label="Explore the platform",
        skill_prompt="What can I do with NeMo Platform?",
        docs_url=_NEMO_DOCS_URL,
    ),
)

_ONBOARDING_PATHS_BY_VALUE: dict[str, OnboardingPath] = {p.value: p for p in ONBOARDING_PATHS}


@dataclass(frozen=True)
class ProbeConfig:
    """How to probe a provider's auth-required endpoint for key validation."""

    method: str
    path: str
    body: dict | None = None


# NVIDIA's gateway routes by model name before checking auth, so a fake model
# returns 404 without ever validating the key.  We use a real, stable model so
# the gateway reaches the auth layer and returns 401/403 for bad credentials.
_NVIDIA_BUILD_PROBE_MODEL = "meta/llama-3.1-8b-instruct"

_PROBE_CONFIGS: dict[str, ProbeConfig] = {
    "nvidia-build": ProbeConfig(
        "POST",
        "v1/chat/completions",
        {"model": _NVIDIA_BUILD_PROBE_MODEL, "messages": [], "max_tokens": 1},
    ),
    "openai": ProbeConfig("GET", "models"),
    "anthropic": ProbeConfig("GET", "v1/models"),
    "google-gemini": ProbeConfig("GET", "models"),
}


@dataclass(frozen=True)
class KeyValidationResult:
    """Outcome of an API key validation probe."""

    passed: bool
    message: str


# Env vars probed during --auto mode, in priority order.
_AUTO_ENV_VARS: tuple[tuple[str, str], ...] = (
    ("NEMO_DEFAULT_INFERENCE_KEY", "NEMO_DEFAULT_INFERENCE_BASE_URL"),
    ("NVIDIA_API_KEY", ""),
    ("OPENAI_API_KEY", ""),
    ("ANTHROPIC_API_KEY", ""),
    ("GEMINI_API_KEY", ""),
)

_KEY_VALIDATION_TIMEOUT = 10.0
_KEY_REJECTED_STATUS_CODES = (401, 403)
_KEY_REJECTED_MESSAGE = "API key validation failed. The provider rejected the credentials."

_MODEL_DISCOVERY_ROUND_SECONDS = 30
_MODEL_DISCOVERY_MAX_ROUNDS = 2
_MODEL_DISCOVERY_POLL_INTERVAL = 1
_SERVICE_STARTUP_TIMEOUT_SECONDS = 240
_SERVICE_STARTUP_POLL_INTERVAL = 0.5
_AGENT_DEPLOY_TIMEOUT_SECONDS = 120
_AGENT_DEPLOY_POLL_INTERVAL = 1
_AGENT_API_READINESS_TIMEOUT = 30
_AGENT_API_READINESS_POLL_INTERVAL = 1
_KILL_WAIT_TIMEOUT = 10
_CONTROLLER_HEALTH_RETRY_DELAY = 3.0
_POST_START_REACHABLE_RETRIES = 6
_POST_START_REACHABLE_DELAY = 2.0

_DEMO_AGENT_NAME = "calculator-agent"


def _pause(seconds: float) -> None:
    time.sleep(seconds)


# Filesystem markers that indicate which coding agents are in use.
_AGENT_MARKERS: tuple[tuple[str, str], ...] = (
    ("AGENTS.md", "codex"),
    (".cursor", "cursor"),
    (".opencode", "opencode"),
    (".claude", "claude"),
)


# ---------------------------------------------------------------------------
# Helpers — platform reachability
# ---------------------------------------------------------------------------


def _bootstrap_config_if_missing(base_url: str, workspace: str) -> None:
    """Write a minimal cluster + context into the config file when one isn't seeded.

    ``nemo setup`` can run before any config is on disk (first-time install)
    *or* with a partial config containing only ``local_services.data_dir``
    written earlier in the same setup invocation by ``_save_data_dir``.
    Later steps — in particular ``_save_default_model`` — call
    ``Config.write`` with *only* a ``default_model`` param. If there's no
    cluster on disk at that point, ``ensure_context`` will fail with
    ``Cluster '<name>' does not exist and no base_url provided to create
    it`` because it has no ``base_url`` to attach to a new cluster.

    Calling this once after the platform is confirmed reachable seeds the
    cluster + context so that all subsequent writes succeed. Idempotent:
    if a cluster is already present, the call is a no-op. Any existing
    ``local_services`` block (e.g. the persisted data dir) is preserved.
    """
    config_path = Config.get_default_config_path()
    if config_path.exists():
        try:
            existing = Config.load(config_path=config_path).get_config_file()
        except Exception:
            # Unreadable existing config — fall through and rewrite.
            logger.debug("Failed to load existing config; will reseed", exc_info=True)
        else:
            if existing.clusters:
                # Cluster already present — assume bootstrap is done.
                return
    params: ConfigParams = {"base_url": base_url, "workspace": workspace}
    Config.write(params)


def _check_platform_reachable(base_url: str, timeout: float = 5.0) -> bool:
    """Return True if the platform health endpoint responds."""
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/health/ready", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _check_platform_reachable_with_retries(
    base_url: str,
    retries: int = _POST_START_REACHABLE_RETRIES,
    delay: float = _POST_START_REACHABLE_DELAY,
) -> bool:
    """Check platform reachability with retries.

    Right after startup the platform may briefly report ready then flip back
    to not-ready while controllers begin heavy work (e.g. model reconciliation).
    A single-shot check can hit this window and falsely report failure.
    """
    for attempt in range(retries):
        if _check_platform_reachable(base_url):
            return True
        if attempt < retries - 1:
            _pause(delay)
    return False


def _check_controller_health(base_url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Query ``/status`` and assess controller health.

    Returns ``(True, "")`` when controllers are populated and all healthy.
    Returns ``(False, detail)`` when unhealthy, unreachable, or empty after retry.

    If ``controllers.status`` is empty on the first call (startup timing race),
    waits ``_CONTROLLER_HEALTH_RETRY_DELAY`` seconds and retries once.
    """
    for attempt in range(2):
        try:
            resp = httpx.get(f"{base_url.rstrip('/')}/status", timeout=timeout)
            if resp.status_code != 200:
                return False, f"Unexpected status {resp.status_code} from /status endpoint."
            data = resp.json()
        except httpx.RequestError:
            return False, "Could not reach platform status endpoint."
        except ValueError:
            return False, "Invalid JSON from /status endpoint."

        controllers = data.get("controllers") if isinstance(data, dict) else None
        if not isinstance(controllers, dict):
            return False, "Invalid /status payload (missing controllers)."
        status_map = controllers.get("status")
        if not isinstance(status_map, dict):
            status_map = {}

        if status_map:
            unhealthy = [name for name, ok in status_map.items() if not ok]
            if unhealthy:
                return False, f"Unhealthy controllers: {', '.join(unhealthy)}"
            return True, ""

        if attempt == 0:
            _pause(_CONTROLLER_HEALTH_RETRY_DELAY)

    return False, "No controllers reported status. Controller threads may have crashed before registering."


def _verify_platform_health(base_url: str) -> bool:
    """Final health gate before declaring setup complete.

    Returns True if the platform is healthy (caller prints the success banner).
    Returns False after printing red or yellow diagnostics to the console.
    """
    ok, detail = _check_controller_health(base_url)
    if ok:
        return True

    if "no controllers" in detail.lower():
        console.print(f"\n{WARN} [yellow]Could not confirm controller health ({detail}).[/yellow]")
        console.print("  Setup may have succeeded, but verify with:")
        console.print("    [cyan]nemo services status[/cyan]")
    else:
        console.print(f"\n{CROSS} [red]Platform controllers are unhealthy.[/red]")
        console.print(f"  {detail}")
        console.print()
        console.print("  The models controller may have crashed during startup.")
        console.print("  Check service logs with: [cyan]nemo services logs[/cyan]")
        console.print()
        console.print("  Try: [cyan]nemo services run[/cyan]   (restart services)")

    return False


def _provider_exists(client: NeMoPlatform, name: str, workspace: str) -> bool:
    """Return True if a provider with *name* already exists."""
    try:
        client.inference.providers.retrieve(name, workspace=workspace)
        return True
    except Exception:
        return False


def _secret_exists(client: NeMoPlatform, name: str, workspace: str) -> bool:
    """Return True if a secret with *name* already exists."""
    try:
        client.secrets.retrieve(name, workspace=workspace)
        return True
    except Exception:
        return False


def _create_secret(client: NeMoPlatform, name: str, value: str, workspace: str) -> None:
    client.secrets.create(name=name, value=value, workspace=workspace)


def _update_secret(client: NeMoPlatform, name: str, value: str, workspace: str) -> None:
    client.secrets.update(name, value=value, workspace=workspace)


def _create_provider(
    client: NeMoPlatform,
    *,
    name: str,
    host_url: str,
    secret_name: str | None,
    workspace: str,
    auth_header_format: str | None = None,
    default_extra_headers: dict[str, str] | None = None,
) -> None:
    kwargs: dict = {
        "name": name,
        "host_url": host_url,
        "workspace": workspace,
    }
    if secret_name:
        kwargs["api_key_secret_name"] = secret_name
    if auth_header_format:
        header_name, _, header_value = auth_header_format.partition(":")
        if header_name and header_value:
            kwargs["required_extra_headers"] = {header_name.strip(): header_value.strip()}
    if default_extra_headers:
        kwargs["default_extra_headers"] = default_extra_headers
    client.inference.providers.create(**kwargs)


def _update_provider(
    client: NeMoPlatform,
    *,
    name: str,
    host_url: str,
    secret_name: str | None,
    workspace: str,
    default_extra_headers: dict[str, str] | None = None,
) -> None:
    kwargs: dict = {
        "host_url": host_url,
        "workspace": workspace,
    }
    if secret_name:
        kwargs["api_key_secret_name"] = secret_name
    if default_extra_headers:
        kwargs["default_extra_headers"] = default_extra_headers
    client.inference.providers.update(name, **kwargs)


_PROVIDER_UNHEALTHY_STATUSES = frozenset({"ERROR", "LOST"})
_NON_COMPLIANT_MARKER = "Non-OpenAI compliant"


def _wait_for_models(
    client: NeMoPlatform,
    provider_name: str,
    workspace: str,
    host_url: str = "",
    round_seconds: int = _MODEL_DISCOVERY_ROUND_SECONDS,
    max_rounds: int = _MODEL_DISCOVERY_MAX_ROUNDS,
) -> list[str]:
    """Poll until provider has at least one served model. Returns entity IDs.

    Retries in rounds so the user sees progress rather than a long silence.
    Checks provider status each poll and exits early if the provider is
    flagged as non-compliant or unhealthy, so the user isn't left waiting
    for models that will never arrive.
    """
    start = time.monotonic()
    for attempt in range(max_rounds):
        deadline = time.monotonic() + round_seconds
        with console.status("[bold cyan]Waiting for model discovery...") as status:
            while time.monotonic() < deadline:
                elapsed = int(time.monotonic() - start)
                status.update(f"[bold cyan]Waiting for model discovery... ({elapsed}s)")
                try:
                    provider = client.inference.providers.retrieve(provider_name, workspace=workspace)
                    served = getattr(provider, "served_models", None) or []
                    if served:
                        model_ids = [m.model_entity_id for m in served if getattr(m, "model_entity_id", None)]
                        if model_ids:
                            return model_ids

                    provider_status = getattr(provider, "status", None) or ""
                    provider_msg = getattr(provider, "status_message", None) or ""

                    if _NON_COMPLIANT_MARKER in provider_msg:
                        url_hint = f" ({host_url})" if host_url else ""
                        console.print(
                            f"\n  {WARN} Provider '{provider_name}'{url_hint} returned a non-OpenAI "
                            f"compliant response from GET /v1/models."
                        )
                        console.print("  Check that the host URL points to an OpenAI-compatible API endpoint.")
                        console.print(
                            "  The provider is still registered and usable for direct inference, "
                            "but automatic model discovery is disabled."
                        )
                        return []

                    if provider_status in _PROVIDER_UNHEALTHY_STATUSES:
                        url_hint = f" ({host_url})" if host_url else ""
                        console.print(f"\n  {WARN} Provider '{provider_name}'{url_hint} is in {provider_status} state.")
                        if provider_msg:
                            console.print(f"  {provider_msg}")
                        console.print("  Check the host URL and API key, then re-run [cyan]nemo setup[/cyan].")
                        return []

                except Exception:
                    logger.debug("Model discovery poll for '%s' failed", provider_name, exc_info=True)
                _pause(_MODEL_DISCOVERY_POLL_INTERVAL)
        if attempt < max_rounds - 1:
            console.print(f"  {WARN} Models not available yet, retrying...")
    return []


def _get_all_model_entity_ids(client: NeMoPlatform, workspace: str) -> list[str]:
    """Return all model entity IDs across all providers."""
    entity_ids: list[str] = []
    try:
        page = client.inference.providers.list(workspace=workspace)
        for provider in page.data:
            for model in getattr(provider, "served_models", None) or []:
                if hasattr(model, "model_entity_id") and model.model_entity_id:
                    entity_ids.append(model.model_entity_id)
    except Exception:
        logger.debug("Failed to list model entity IDs", exc_info=True)
    return sorted(set(entity_ids))


def _get_all_model_choices(client: NeMoPlatform, workspace: str) -> list[tuple[str, str]]:
    """Return picker choices as (entity_id, label) across all providers."""
    choices: list[tuple[str, str]] = []
    try:
        page = client.inference.providers.list(workspace=workspace)
        for provider in page.data:
            provider_name = getattr(provider, "name", "unknown-provider")
            for model in getattr(provider, "served_models", None) or []:
                model_entity_id = getattr(model, "model_entity_id", None)
                if model_entity_id:
                    label = f"{_display_model_name(model_entity_id)} ({provider_name})"
                    choices.append((model_entity_id, label))
    except Exception:
        logger.debug("Failed to list model choices", exc_info=True)
    return sorted(set(choices), key=lambda item: item[1])


def _display_model_name(model_entity_id: str) -> str:
    """Strip workspace prefix from a model entity ID for display."""
    return model_entity_id.split("/", 1)[-1] if "/" in model_entity_id else model_entity_id


def _resolve_provider_for_url(base_url: str) -> KnownProvider | None:
    """Find a known provider whose host_url matches *base_url*."""
    normalized = base_url.rstrip("/")
    for p in KNOWN_PROVIDERS:
        if p.host_url.rstrip("/") == normalized:
            return p
    return None


# ---------------------------------------------------------------------------
# Service startup
# ---------------------------------------------------------------------------


def _load_persisted_data_dir() -> str | None:
    """Return the local data directory previously chosen via ``nemo setup``."""
    config_path = Config.get_default_config_path()
    if not config_path.exists():
        return None
    try:
        config = Config.load(config_path=config_path)
    except Exception:
        logger.debug("Failed to load config for local_services lookup", exc_info=True)
        return None
    local = config.get_config_file().local_services
    return local.data_dir if local else None


def _save_data_dir(data_dir: str) -> None:
    """Persist the chosen local data directory to the user's config file.

    Reads any existing config so other fields (contexts, clusters, etc.) are
    preserved, then overwrites just ``local_services.data_dir``.
    """
    config_path = Config.get_default_config_path()
    if config_path.exists():
        config = Config.load(config_path=config_path)
    else:
        config = Config.create(config_path, ConfigFile())
    config_file = config.get_config_file()
    config_file.local_services = LocalServicesConfig(data_dir=data_dir)
    config.save()


def _prompt_data_dir() -> str:
    """Prompt the user for a local data directory and persist the choice.

    Pre-fills the prompt with the previously-persisted directory if any,
    otherwise the XDG default (``~/.local/share/nemo``).  The chosen
    directory is where local services persist SQLite DB, encryption key,
    and uploaded files.
    """
    persisted = _load_persisted_data_dir()
    default_dir = persisted or str(nmp_user_data_dir())

    chosen = prompt_text(
        message="Local data directory:",
        default=default_dir,
        validator=non_empty_validator("Data directory"),
    ).strip()

    _save_data_dir(chosen)
    return chosen


def _resolve_services_port(base_url: str) -> int:
    """Extract the port from *base_url*, defaulting to 8080."""
    parsed = urlparse(base_url)
    return parsed.port or 8080


def _start_services_background(base_url: str, data_dir: str | None = None) -> subprocess.Popen:
    """Launch ``nemo services run`` as a background process.

    Delegates to the shared process lifecycle module which uses flock-based
    instance tracking.  If *data_dir* is provided, it's forwarded so the
    subprocess inherits ``NMP_DATA_DIR`` (unless the parent shell already
    exported it).
    """
    from nemo_platform.cli.commands.services._process import compute_scope, start_background

    port = _resolve_services_port(base_url)
    scope = compute_scope(port=port)
    return start_background(scope=scope, port=port, data_dir=data_dir)


def _last_startup_service(log_path: Path | None) -> str:
    """Read the most recently logged ``[STARTUP] service:<name>`` from the service log."""
    if log_path is None or not log_path.exists():
        return ""
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return ""
    last = ""
    tag = "[STARTUP] service:"
    for line in text.splitlines():
        if tag in line:
            last = line.split(tag, 1)[1].split(":")[0]
    return last


def _wait_for_platform(
    base_url: str,
    timeout: int = _SERVICE_STARTUP_TIMEOUT_SECONDS,
    poll_interval: float = _SERVICE_STARTUP_POLL_INTERVAL,
    log_path: Path | None = None,
) -> bool:
    """Poll until the platform health endpoint responds. Returns True on success.

    When *log_path* is provided, the spinner shows the last service that
    finished loading so users see that progress is being made during a
    slow cold start.
    """
    start = time.monotonic()
    deadline = start + timeout
    with console.status("[bold cyan]Waiting for platform...") as status:
        while time.monotonic() < deadline:
            elapsed = int(time.monotonic() - start)
            svc = _last_startup_service(log_path)
            hint = f" — loaded {svc}" if svc else ""
            status.update(f"[bold cyan]Waiting for platform... ({elapsed}s){hint}")
            if _check_platform_reachable(base_url, timeout=1.0):
                return True
            _pause(poll_interval)
    return False


def _kill_existing_services(base_url: str) -> None:
    """Find and kill any running ``nemo services run`` processes.

    Delegates to the shared process lifecycle module.
    """
    from nemo_platform.cli.commands.services._process import compute_scope, stop_instance

    port = _resolve_services_port(base_url)
    scope = compute_scope(port=port)
    stop_instance(scope, timeout=2.0, force=True)


def _maybe_start_services(
    base_url: str,
    auto: bool,
    start_services: bool | None,
    timeout: int = _SERVICE_STARTUP_TIMEOUT_SECONDS,
) -> None:
    """Start services if requested, restarting if already running.

    In interactive mode (auto=False), prompts the user if start_services is None.
    In auto mode, only starts if start_services is explicitly True.

    When start_services is True and the platform is already running, the
    existing processes are stopped and restarted so the full service set
    (including any newly installed plugins) is picked up. Data lives in
    SQLite so nothing is lost across restarts.
    """
    already_running = _check_platform_reachable(base_url)

    if already_running and start_services is not True:
        console.print(f"{CHECK} Platform already running at {base_url}\n")
        return

    should_start = start_services
    if should_start is None:
        if auto:
            console.print(f"{CROSS} Cannot reach platform at {base_url}")
            console.print("  Start the platform first, or pass --start-services:")
            console.print("    [cyan]nemo setup --auto --start-services[/cyan]")
            console.print("    [cyan]nemo services run[/cyan]")
            raise typer.Exit(1)
        should_start = (
            prompt_choice(
                message=f"Platform not reachable at {base_url}. Start local services?",
                options=[("yes", "Yes, start services now"), ("no", "No, I'll start them myself")],
                default="yes",
            )
            == "yes"
        )

    if not should_start:
        console.print(f"{CROSS} Cannot reach platform at {base_url}")
        console.print("  Start the platform first:")
        console.print("    [cyan]nemo services run[/cyan]   (local development)")
        raise typer.Exit(1)

    # Pick (and persist) the local data directory before launching services
    # so the chosen path takes effect on this run.  Interactive mode prompts;
    # ``--auto`` reuses whatever was previously persisted (or service default).
    if auto:
        data_dir = _load_persisted_data_dir()
    else:
        data_dir = _prompt_data_dir()

    if already_running:
        console.print("  Restarting platform services...")
        _kill_existing_services(base_url)
        deadline = time.time() + _KILL_WAIT_TIMEOUT
        while time.time() < deadline and _check_platform_reachable(base_url, timeout=1.0):
            _pause(1)
    else:
        console.print("  Starting platform services...")
    proc = _start_services_background(base_url, data_dir=data_dir)

    from nemo_platform.cli.commands.services._process import compute_scope, log_path_for

    port = _resolve_services_port(base_url)
    log = log_path_for(compute_scope(port=port))

    if not _wait_for_platform(base_url, timeout=timeout, log_path=log):
        exit_code = proc.poll()
        if exit_code is not None:
            console.print(f"{CROSS} Service process exited early (exit code {exit_code})")
        else:
            proc.terminate()
            console.print(f"{CROSS} Platform did not become ready within {timeout}s")
        console.print(f"  Check {log} for details.")
        raise typer.Exit(1)

    console.print(f"{CHECK} Platform running at {base_url} (pid {proc.pid})\n")


# ---------------------------------------------------------------------------
# Skills installation
# ---------------------------------------------------------------------------


def _detect_coding_agents() -> list[tuple[str, str]]:
    """Detect coding agents from filesystem markers in the project root.

    Returns list of (marker, agent_name) for each detected agent.
    """
    project_root = _find_project_root()
    detected = []
    for marker, agent_name in _AGENT_MARKERS:
        if (project_root / marker).exists():
            detected.append((marker, agent_name))
    return detected


def _find_project_root() -> Path:
    """Find the project root by looking for a .git directory, falling back to cwd."""
    cwd = Path.cwd()
    current = cwd
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return cwd


def _load_skills_with_warnings() -> tuple[dict[str, Skill], list[str]]:
    """Load skills while capturing any plugin-discovery warnings.

    The registry emits ``logger.warning`` records when a plugin's skills directory
    is missing, malformed, or invalid. We capture those records so they can be
    surfaced in the preview before any install happens, rather than scrolling
    past mid-install.

    Defensive against (a) callers that raised the registry logger's level above
    WARNING (e.g. a future ``--quiet`` flag) and (b) the ``@lru_cache`` on the
    underlying loader, which would otherwise replay a cached dict with no
    warnings on repeat calls.
    """
    from nemo_platform.cli.commands.skills import registry as _registry

    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = _Capture(level=logging.WARNING)
    original_level = _registry.logger.level
    _registry.logger.addHandler(handler)
    if original_level > logging.WARNING or original_level == logging.NOTSET:
        _registry.logger.setLevel(logging.WARNING)
    _registry.clear_cache()
    try:
        skills = load_skills()
    finally:
        _registry.logger.removeHandler(handler)
        _registry.logger.setLevel(original_level)
    return skills, captured


def _print_plugin_warnings(plugin_warnings: list[str]) -> None:
    """Surface plugin-discovery warnings before the interactive skills prompt."""
    if not plugin_warnings:
        return
    console.print("  [yellow]Plugin warnings:[/yellow]")
    for msg in plugin_warnings:
        console.print(f"    {WARN} {msg}")
    console.print()


_BUILTIN_SOURCE_NAME = "nemo-platform"


def _skill_sources_of(skills: dict[str, Skill]) -> dict[str, list[Skill]]:
    """Group skills by their source (built-in vs each plugin).

    The built-in source is keyed by ``nemo-platform``; plugin skills are keyed
    by ``Skill.source_plugin``. Returned dict preserves insertion order so the
    built-in group appears first, then plugins in discovery order.
    """
    sources: dict[str, list[Skill]] = {}
    for skill in skills.values():
        key = skill.source_plugin or _BUILTIN_SOURCE_NAME
        sources.setdefault(key, []).append(skill)
    return sources


def _filter_agents_by_scope(agents: list[str], scope: Scope) -> tuple[list[str], list[tuple[str, str]]]:
    """Split agents into (installable, skipped) based on whether each supports the chosen scope.

    Returns:
        (kept, skipped) where ``skipped`` is a list of (agent_name, reason) tuples.
    """
    kept: list[str] = []
    skipped: list[tuple[str, str]] = []
    for agent in agents:
        installer = get_installer(agent)
        if scope in installer.supported_scopes:
            kept.append(agent)
        else:
            supported = ", ".join(s.value for s in installer.supported_scopes) or "none"
            skipped.append((agent, f"does not support '{scope.value}' scope (supports: {supported})"))
    return kept, skipped


def _print_final_skills_summary(agents: list[str], scope: Scope, skill_names: list[str]) -> None:
    """Print the planned action before final confirmation."""
    if not skill_names or not agents:
        return
    project_root = _find_project_root()
    agent_list = ", ".join(agents)
    console.print(
        f"  Installing [bold]{len(skill_names)}[/bold] skill(s) for "
        f"[bold]{agent_list}[/bold] at [bold]{scope.value}[/bold] scope:"
    )
    for agent in agents:
        installer = get_installer(agent)
        # Show the parent directory of one representative skill so the user
        # sees the destination root, not a single SKILL.md path.
        example = installer.get_install_path(scope, project_root, skill_names[0])
        console.print(f"    {agent} → {example.parent.parent}/")
    console.print()


def _run_skill_install(
    *,
    agents: list[str],
    scope: Scope,
    skill_names: list[str],
    all_skills: dict[str, Skill],
    project_root: Path,
) -> None:
    """Run the actual installer for each agent with the chosen skill subset.

    Skill names are expected to come from a validated source-selection path
    (interactive multiselect or ``--skills-from`` flag), so any name not in
    ``all_skills`` would be an internal bug. If every agent's install fails,
    raises ``typer.Exit(1)`` so callers in ``--auto`` see a non-zero exit.
    """
    chosen = {name: all_skills[name] for name in skill_names if name in all_skills}
    if not chosen:
        console.print(f"  {WARN} No skills selected to install.")
        return

    successes = 0
    failures = 0
    for agent in agents:
        try:
            installer = get_installer(agent)
            installer.install(scope, project_root, chosen)
            console.print(f"  {CHECK} Installed {len(chosen)} skill(s) for {agent}")
            successes += 1
        except Exception as exc:
            console.print(f"  {WARN} Failed to install skills for {agent}: {exc}")
            failures += 1

    if failures and not successes:
        raise typer.Exit(1)


def _parse_csv_flag(value: str | None) -> list[str] | None:
    """Parse a comma-separated CLI flag into a list, dropping empty entries."""
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",")]
    cleaned = [p for p in parts if p]
    return cleaned or None


def _maybe_install_skills(
    auto: bool,
    install_skills: bool | None,
    *,
    skills_agents: list[str] | None = None,
    skills_scope: Scope | None = None,
    skills_from: list[str] | None = None,
) -> None:
    """Install coding agent skills if requested.

    ``--install-skills`` is the master opt-in. ``--skills-agents``,
    ``--skills-scope``, and ``--skills-from`` are filters that narrow what
    gets installed when the master is set; on their own they do nothing in
    non-interactive mode. This mirrors ``_maybe_deploy_agent`` and
    ``_maybe_start_services``, which also require their boolean master flag
    to be explicitly True under ``--auto``.

    ``--skills-from`` selects by *source* (the built-in ``nemo-platform`` set
    or a plugin name) rather than by individual skill name. Picking one source
    installs every skill that source provides.

    Interactive mode walks the user through a source multi-select (each source
    expanded to show its skills as read-only sub-labels, with ``s`` to skip the
    whole step), an agent multi-select, a scope choice, and a final
    confirmation; filter flags pre-populate the defaults.
    """
    if install_skills is False:
        return

    # Validate --skills-agents up-front: a typo like `--skills-agents copex` should
    # fail loudly before any platform work, regardless of detection state.
    if skills_agents:
        for agent in skills_agents:
            get_installer(agent)

    detected = _detect_coding_agents()
    # --skills-agents overrides detection: an explicit instruction to install for
    # an agent wins over "we didn't find a marker file for it." Detection is still
    # load-bearing as the default when the flag is absent.
    if not detected and not skills_agents:
        if not auto:
            console.print(f"  {WARN} No coding agents detected in project (no .cursor/, AGENTS.md, etc.)")
        return

    all_skills, plugin_warnings = _load_skills_with_warnings()
    if not all_skills:
        console.print(f"  {WARN} No NeMo skills available to install.")
        return

    sources = _skill_sources_of(all_skills)
    source_names = list(sources.keys())

    # Validate --skills-from up-front, same shape as --skills-agents.
    if skills_from:
        unknown = [s for s in skills_from if s not in sources]
        if unknown:
            known = ", ".join(source_names)
            raise typer.BadParameter(
                f"Unknown skill source(s): {', '.join(unknown)}. Known sources: {known}",
                param_hint="--skills-from",
            )

    detected_names = [name for _, name in detected]
    # Interactive menu options: detected agents plus any extras the user explicitly
    # asked for. dict.fromkeys preserves order and deduplicates.
    menu_agent_names = list(dict.fromkeys(detected_names + (skills_agents or [])))
    project_root = _find_project_root()
    non_interactive = auto or not is_interactive()

    def _skills_for_sources(chosen_sources: list[str]) -> list[str]:
        return [skill.name for source in chosen_sources for skill in sources[source]]

    if non_interactive:
        # Non-interactive path requires the master switch to be explicitly True.
        # Filter flags alone don't opt in (matches --start-services / --deploy-agent).
        if install_skills is not True:
            return
        chosen_agents = skills_agents or detected_names
        chosen_scope = skills_scope or Scope.PROJECT
        chosen_sources = skills_from or source_names
        chosen_skills = _skills_for_sources(chosen_sources)
        chosen_agents, skipped = _filter_agents_by_scope(chosen_agents, chosen_scope)
        for agent, reason in skipped:
            console.print(f"  {WARN} Skipping {agent}: {reason}")
        if not chosen_agents:
            console.print(f"  {WARN} No installable agents for scope '{chosen_scope.value}'.")
            return
        _run_skill_install(
            agents=chosen_agents,
            scope=chosen_scope,
            skill_names=chosen_skills,
            all_skills=all_skills,
            project_root=project_root,
        )
        return

    # Interactive path: sources → agents → scope → confirm.
    _print_plugin_warnings(plugin_warnings)

    source_defaults = skills_from if skills_from else source_names
    source_options = [(name, f"{name} (built-in)" if name == _BUILTIN_SOURCE_NAME else name) for name in source_names]
    source_sub_labels = {name: [skill.name for skill in sources[name]] for name in source_names}
    chosen_sources = prompt_multiselect(
        message="Install skills:",
        options=source_options,
        defaults=source_defaults,
        sub_labels=source_sub_labels,
        min_choices=1,
        allow_skip=True,
        indent=2,
    )
    if chosen_sources is None:
        console.print(f"  {WARN} Skipping skill installation.")
        return
    chosen_skills = _skills_for_sources(chosen_sources)

    agent_defaults = skills_agents if skills_agents else detected_names
    chosen_agents = prompt_multiselect(
        message="Install skills for which agents?",
        options=[(name, get_installer(name).display_name) for name in menu_agent_names],
        defaults=agent_defaults,
        min_choices=1,
        indent=2,
    )

    scope_default = (skills_scope or Scope.PROJECT).value
    chosen_scope = Scope(
        prompt_choice(
            message="Install scope:",
            options=[
                (Scope.PROJECT.value, "Local (this repo: .agents/, .cursor/, .claude/, ...)"),
                (Scope.USER.value, "Global (user home: ~/.agents/, ~/.claude/, ...)"),
            ],
            default=scope_default,
            indent=2,
        )
    )

    chosen_agents, skipped = _filter_agents_by_scope(chosen_agents, chosen_scope)
    for agent, reason in skipped:
        console.print(f"  {WARN} Skipping {agent}: {reason}")
    if not chosen_agents:
        console.print(f"  {WARN} No installable agents for scope '{chosen_scope.value}'.")
        return

    _print_final_skills_summary(chosen_agents, chosen_scope, chosen_skills)
    if not prompt_confirm("Proceed?", default=True, indent=2):
        return

    _run_skill_install(
        agents=chosen_agents,
        scope=chosen_scope,
        skill_names=chosen_skills,
        all_skills=all_skills,
        project_root=project_root,
    )


# ---------------------------------------------------------------------------
# Agent deployment
# ---------------------------------------------------------------------------


def _agents_plugin_available() -> bool:
    """Return True if the nemo-agents plugin is importable."""
    return importlib.util.find_spec("nemo_agents_plugin") is not None


def _agent_config_path() -> Traversable | None:
    """Return the path to the calculator-agent demo config YAML, or None."""
    try:
        candidate = files("calculator_agent").joinpath("calculator-agent.yml")
        if candidate.is_file():
            return candidate
    except (ImportError, ModuleNotFoundError):
        logger.debug("calculator_agent package not importable; demo agent config unavailable", exc_info=True)

    return None


def _agent_exists(base_url: str, workspace: str) -> bool:
    """Return True if the demo agent already exists on the platform."""
    try:
        resp = httpx.get(
            f"{base_url.rstrip('/')}/apis/agents/v2/workspaces/{workspace}/agents/{_DEMO_AGENT_NAME}",
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _agents_api_ready(base_url: str, workspace: str) -> bool:
    """Return True if the agents API is responding."""
    try:
        resp = httpx.get(
            f"{base_url.rstrip('/')}/apis/agents/v2/workspaces/{workspace}/agents",
            timeout=3.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _deploy_demo_agent(base_url: str, workspace: str, config_path: Traversable, default_model: str) -> bool:
    """Create and deploy the demo calculator agent. Returns True on success."""
    from nemo_agents_plugin.utils import expand_env_vars

    api_base = base_url.rstrip("/")

    if not _agent_exists(base_url, workspace):
        config_dict = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config_dict = expand_env_vars(config_dict, vars_dict={"NEMO_DEFAULT_MODEL": default_model})
        payload = {"name": _DEMO_AGENT_NAME, "description": "Demo calculator agent", "config": config_dict}
        resp = httpx.post(
            f"{api_base}/apis/agents/v2/workspaces/{workspace}/agents",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        console.print(f"  {CHECK} Created agent '{_DEMO_AGENT_NAME}'")
    else:
        console.print(f"  {CHECK} Agent '{_DEMO_AGENT_NAME}' already exists")

    resp = httpx.post(
        f"{api_base}/apis/agents/v2/workspaces/{workspace}/deployments",
        json={"agent": _DEMO_AGENT_NAME},
        timeout=30.0,
    )
    if resp.status_code == 409:
        console.print(f"  {CHECK} Agent '{_DEMO_AGENT_NAME}' already deployed")
        return True

    resp.raise_for_status()
    deployment_name = resp.json().get("name", "")
    console.print(f"  {CHECK} Deployed agent '{_DEMO_AGENT_NAME}'")

    # Poll the specific deployment we just created by name, not the full
    # list.  Previous runs may leave stale "failed" deployments that would
    # confuse a list-and-scan approach.
    start = time.monotonic()
    deadline = start + _AGENT_DEPLOY_TIMEOUT_SECONDS
    with console.status("[bold cyan]Waiting for agent deployment...") as spinner:
        while time.monotonic() < deadline:
            elapsed = int(time.monotonic() - start)
            spinner.update(f"[bold cyan]Waiting for agent deployment... ({elapsed}s)")
            try:
                dep_resp = httpx.get(
                    f"{api_base}/apis/agents/v2/workspaces/{workspace}/deployments/{deployment_name}",
                    timeout=3.0,
                )
                if dep_resp.status_code == 200:
                    dep_status = dep_resp.json().get("status", "")
                    if dep_status == "running":
                        return True
                    if dep_status == "failed":
                        console.print(f"  {CROSS} Agent deployment failed")
                        return False
            except Exception:
                logger.debug("Agent deployment status poll failed", exc_info=True)
            _pause(_AGENT_DEPLOY_POLL_INTERVAL)

    console.print(f"  {WARN} Agent deployment did not reach running state within {_AGENT_DEPLOY_TIMEOUT_SECONDS}s")
    return False


def _maybe_deploy_agent(
    base_url: str,
    workspace: str,
    auto: bool,
    deploy_agent: bool | None,
    default_model: str | None = None,
) -> bool:
    """Optionally deploy the demo calculator agent.

    In interactive mode (auto=False), prompts the user if deploy_agent is None.
    Default is **no** -- the demo is opt-in for users who don't have their own
    agent yet.  In auto mode, only deploys if deploy_agent is explicitly True.

    Returns True if the agent was deployed (used by CTA messaging).
    """
    if not _agents_plugin_available():
        console.print(f"  {WARN} nemo-agents plugin not installed, skipping agent deployment")
        console.print("  Run [cyan]make bootstrap[/cyan] from the repo root to install all plugins,")
        console.print("  then re-run: [cyan]nemo setup --deploy-agent[/cyan]")
        return False

    should_deploy = deploy_agent
    if should_deploy is None:
        if auto:
            return False
        console.print(
            "  NeMo Platform optimizes AI agents. If you don't have your own\n"
            "  agent yet, you can deploy a demo calculator agent to try things out.\n"
        )
        should_deploy = (
            prompt_choice(
                message="Deploy the demo agent?",
                options=[("no", "No, skip"), ("yes", "Yes, deploy it")],
                default="no",
            )
            == "yes"
        )

    if not should_deploy:
        return False

    if not default_model:
        console.print(
            f"  {WARN} No default model selected, skipping agent deployment "
            "(the demo agent template needs a resolved model)"
        )
        return False

    config_path = _agent_config_path()
    if config_path is None:
        console.print(f"  {WARN} Could not find calculator-agent config YAML, skipping agent deployment")
        return False

    start = time.monotonic()
    deadline = start + _AGENT_API_READINESS_TIMEOUT
    api_ready = False
    with console.status("[bold cyan]Waiting for agents API...") as spinner:
        while time.monotonic() < deadline:
            elapsed = int(time.monotonic() - start)
            spinner.update(f"[bold cyan]Waiting for agents API... ({elapsed}s)")
            if _agents_api_ready(base_url, workspace):
                api_ready = True
                break
            _pause(_AGENT_API_READINESS_POLL_INTERVAL)
    if not api_ready:
        console.print(f"  {WARN} Agents API not ready at {base_url}, skipping agent deployment")
        console.print("  Ensure the agents service is running (e.g. [cyan]nemo services run --services agents[/cyan])")
        return False

    try:
        return _deploy_demo_agent(base_url, workspace, config_path, default_model=default_model)
    except Exception as exc:
        console.print(f"  {WARN} Agent deployment failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Interactive flow helpers
# ---------------------------------------------------------------------------


def _select_provider() -> KnownProvider | None:
    """Prompt user to pick one provider. Returns None for 'custom'."""
    options = [(p.name, f"{p.label:<20s} {p.description}") for p in KNOWN_PROVIDERS]
    options.append(("custom", "Custom provider      Enter URL and key manually"))

    result = prompt_choice(
        message="",
        options=options,
        default=KNOWN_PROVIDERS[0].name,
    )

    if result == "custom":
        return None
    return _KNOWN_PROVIDERS_BY_NAME[result]


def _prompt_custom_provider() -> tuple[str, str, str | None]:
    """Prompt for custom provider details. Returns (name, host_url, api_key_or_none)."""
    name = prompt_text(
        "Provider name: ",
        validator=provider_name_validator(),
        hint="Start with a lowercase letter, then lowercase letters, digits, or hyphens; 2-63 chars (e.g. my-vllm-provider)",
    ).strip()

    host_url = prompt_text("Provider base URL: ").strip()
    if not host_url:
        raise typer.Exit(1)

    api_key = prompt_password("API key (leave empty if none): ").strip() or None

    return name, host_url, api_key


def _collect_credential(provider: KnownProvider) -> str:
    """Prompt for the API key, checking the env var first."""
    if not provider.requires_api_key:
        return ""

    env_val = os.environ.get(provider.env_var or "") if provider.env_var else None
    if env_val:
        masked = f"***{env_val[-4:]}" if len(env_val) > 4 else "****"
        console.print(f"  Found {provider.env_var} in environment ({masked})")
        key = prompt_password(f"{provider.label} API key [{masked}]: ")
        return key.strip() if key.strip() else env_val

    key = prompt_password(
        f"{provider.label} API key: ",
        validator=non_empty_validator("API key"),
    )
    return key.strip()


def _register_provider_interactive(
    client: NeMoPlatform,
    *,
    provider_name: str,
    host_url: str,
    api_key: str | None,
    workspace: str,
    auth_header_format: str | None = None,
    default_extra_headers: dict[str, str] | None = None,
) -> None:
    """Create or update secret + provider for idempotent re-runs."""
    secret_name = f"{provider_name}-api-key" if api_key else None

    if secret_name:
        if _secret_exists(client, secret_name, workspace):
            _update_secret(client, secret_name, api_key, workspace)
            console.print(f"  {CHECK} Updated secret '{secret_name}'")
        else:
            _create_secret(client, secret_name, api_key, workspace)
            console.print(f"  {CHECK} Created secret '{secret_name}'")

    if _provider_exists(client, provider_name, workspace):
        _update_provider(
            client,
            name=provider_name,
            host_url=host_url,
            secret_name=secret_name,
            workspace=workspace,
            default_extra_headers=default_extra_headers,
        )
        console.print(f"  {CHECK} Updated provider '{provider_name}' ({host_url})")
    else:
        _create_provider(
            client,
            name=provider_name,
            host_url=host_url,
            secret_name=secret_name,
            workspace=workspace,
            auth_header_format=auth_header_format,
            default_extra_headers=default_extra_headers,
        )
        console.print(f"  {CHECK} Registered provider '{provider_name}' ({host_url})")


def _validate_api_key(
    provider_name: str,
    host_url: str,
    api_key: str | None,
    *,
    auth_header_format: str | None = None,
    default_extra_headers: dict[str, str] | None = None,
    timeout: float = _KEY_VALIDATION_TIMEOUT,
) -> KeyValidationResult:
    """Probe the provider with the API key to detect auth failures early.

    Makes a single lightweight request to an auth-required endpoint.
    Returns ``passed=False`` only on a definitive 401/403 rejection.
    Network errors and unknown providers are treated as *passed* to avoid
    blocking setup when the provider is unreachable.
    """
    if not api_key:
        return KeyValidationResult(passed=True, message="")

    probe = _PROBE_CONFIGS.get(provider_name)
    if probe is None:
        return KeyValidationResult(
            passed=True,
            message=f"No validation probe configured for provider '{provider_name}'; skipping key check.",
        )

    headers: dict[str, str] = {}
    if auth_header_format:
        header_name, _, template = auth_header_format.partition(":")
        headers[header_name.strip()] = template.strip().replace("{{ auth_secret }}", api_key)
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    if default_extra_headers:
        headers.update(default_extra_headers)

    url = f"{host_url.rstrip('/')}/{probe.path}"

    try:
        resp = httpx.request(
            probe.method,
            url,
            headers=headers,
            json=probe.body,
            timeout=timeout,
        )
        if resp.status_code in _KEY_REJECTED_STATUS_CODES:
            return KeyValidationResult(passed=False, message=_KEY_REJECTED_MESSAGE)
        if 200 <= resp.status_code < 300:
            return KeyValidationResult(passed=True, message="")
        return KeyValidationResult(
            passed=True,
            message=f"Could not validate API key (received HTTP {resp.status_code}).",
        )
    except httpx.TimeoutException:
        logger.debug("API key validation timed out for '%s'", provider_name)
        return KeyValidationResult(passed=True, message="Could not validate API key (request timed out).")
    except Exception as exc:
        logger.debug("API key validation failed for '%s': %s", provider_name, exc)
        return KeyValidationResult(passed=True, message=f"Could not validate API key ({exc}).")


def _select_default_model(client: NeMoPlatform, workspace: str) -> str | None:
    """Let the user pick a default model from discovered models."""
    display_models = _get_all_model_choices(client, workspace)
    if not display_models:
        console.print(f"  {WARN} No models discovered yet. You can set a default later.")
        return None

    result = prompt_select(
        "Choose your default model:",
        choices=display_models,
    )
    return result


def _save_default_model(cli_context: CLIContext, model_entity_id: str) -> None:
    """Persist the default model to the CLI config file."""
    context = cli_context.get_sdk_context()
    Config.write({"default_model": model_entity_id}, context_name=context.context_name)


def _check_ollama_running(host_url: str) -> bool:
    """Probe Ollama endpoint to check if it's running."""
    try:
        resp = httpx.get(f"{host_url.rstrip('/')}/models", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Auto (non-interactive) mode
# ---------------------------------------------------------------------------


def _auto_setup(client: NeMoPlatform, workspace: str) -> bool:
    """Register a provider from environment variables. Returns True on success."""
    for key_var, url_var in _AUTO_ENV_VARS:
        api_key = os.environ.get(key_var)
        if not api_key:
            continue

        base_url = os.environ.get(url_var, "").strip() if url_var else ""
        if base_url:
            known = _resolve_provider_for_url(base_url)
            if known:
                provider_name = known.name
            else:
                hostname = urlparse(base_url).hostname or "custom"
                provider_name = hostname.replace(".", "-")
            host_url = base_url
            auth_header_format = known.auth_header_format if known else None
            default_extra_headers = known.default_extra_headers if known else None
        else:
            for p in KNOWN_PROVIDERS:
                if p.env_var == key_var and p.requires_api_key:
                    provider_name = p.name
                    host_url = p.host_url
                    auth_header_format = p.auth_header_format
                    default_extra_headers = p.default_extra_headers
                    break
            else:
                continue

        key_result = _validate_api_key(
            provider_name,
            host_url,
            api_key,
            auth_header_format=auth_header_format,
            default_extra_headers=default_extra_headers,
        )
        if not key_result.passed:
            console.print(f"  {CROSS} {key_result.message}")
            console.print(f"  Check the value of ${key_var} and try again.")
            raise typer.Exit(1)
        if key_result.message:
            console.print(f"  {WARN} {key_result.message}")

        secret_name = f"{provider_name}-api-key"
        if _secret_exists(client, secret_name, workspace):
            _update_secret(client, secret_name, api_key, workspace)
            console.print(f"  {CHECK} Updated secret '{secret_name}' (from ${key_var})")
        else:
            _create_secret(client, secret_name, api_key, workspace)
            console.print(f"  {CHECK} Created secret '{secret_name}' (from ${key_var})")

        if _provider_exists(client, provider_name, workspace):
            _update_provider(
                client,
                name=provider_name,
                host_url=host_url,
                secret_name=secret_name,
                workspace=workspace,
                default_extra_headers=default_extra_headers,
            )
            console.print(f"  {CHECK} Updated provider '{provider_name}' ({host_url})")
        else:
            _create_provider(
                client,
                name=provider_name,
                host_url=host_url,
                secret_name=secret_name,
                workspace=workspace,
                auth_header_format=auth_header_format,
                default_extra_headers=default_extra_headers,
            )
            console.print(f"  {CHECK} Registered provider '{provider_name}' ({host_url})")

        return True

    return False


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------


@handle_errors
def setup_command(
    ctx: typer.Context,
    auto: Annotated[
        bool,
        typer.Option("--auto", help="Non-interactive mode: register provider from environment variables"),
    ] = False,
    workspace: Annotated[
        str,
        typer.Option("--workspace", "-w", help="Target workspace"),
    ] = "default",
    start_services: Annotated[
        bool | None,
        typer.Option("--start-services/--no-start-services", help="Start local platform services"),
    ] = None,
    install_skills: Annotated[
        bool | None,
        typer.Option("--install-skills/--no-install-skills", help="Install NeMo skills for coding agents"),
    ] = None,
    skills_agents: Annotated[
        str | None,
        typer.Option(
            "--skills-agents",
            help=(
                "Comma-separated list of agents to install skills for (e.g. 'codex,cursor'). "
                "Default: all detected. Only applied when --install-skills is set."
            ),
        ),
    ] = None,
    skills_scope: Annotated[
        Scope | None,
        typer.Option(
            "--skills-scope",
            help=(
                "Install scope for skills: 'project' (this repo) or 'user' (home). "
                "Default: project. Only applied when --install-skills is set."
            ),
            case_sensitive=False,
        ),
    ] = None,
    skills_from: Annotated[
        str | None,
        typer.Option(
            "--skills-from",
            help=(
                "Comma-separated list of skill sources to install from "
                "(e.g. 'nemo-platform,nemo-evaluator-plugin'). Use 'nemo-platform' "
                "for the built-in set. Default: all sources. "
                "Only applied when --install-skills is set."
            ),
        ),
    ] = None,
    deploy_agent: Annotated[
        bool | None,
        typer.Option("--deploy-agent/--no-deploy-agent", help="Deploy the demo calculator agent"),
    ] = None,
    ready_timeout: Annotated[
        int | None,
        typer.Option(
            "--ready-timeout",
            help=f"Seconds to wait for platform readiness (default: {_SERVICE_STARTUP_TIMEOUT_SECONDS})",
        ),
    ] = None,
) -> None:
    """Set up NeMo Platform: start services, configure a provider, install skills.

    Walks through starting local services, selecting a provider, entering
    credentials, registering the provider with the platform, picking a
    default model, installing coding agent skills, and optionally deploying
    a demo agent.

    Requires an interactive terminal (TTY). In non-interactive contexts
    (CI, piped input), pass --auto to use environment variables instead.

    Use --auto for non-interactive setup from environment variables
    (NEMO_DEFAULT_INFERENCE_KEY, NVIDIA_API_KEY, OPENAI_API_KEY,
    ANTHROPIC_API_KEY, GEMINI_API_KEY).
    Override the default model with NEMO_DEFAULT_MODEL.

    Examples:
      nemo setup
      nemo setup --auto
      nemo setup --auto --start-services --install-skills --deploy-agent
      nemo setup --auto --start-services --ready-timeout 360
      nemo setup --workspace my-workspace
      nemo setup --no-install-skills --no-deploy-agent
    """
    cli_context: CLIContext = ctx.obj
    base_url = cli_context.get_base_url()

    console.print("\n[bold cyan]NeMo Platform Setup[/bold cyan]\n")

    if not auto and not is_interactive():
        console.print(f"\n{CROSS} Detected non-interactive shell. Pass [bold]--auto[/bold] or run in a TTY.\n")
        raise typer.Exit(1)

    effective_timeout = _SERVICE_STARTUP_TIMEOUT_SECONDS if ready_timeout is None else ready_timeout
    if effective_timeout <= 0:
        raise typer.BadParameter("--ready-timeout must be greater than 0", param_hint="--ready-timeout")
    _maybe_start_services(base_url, auto, start_services, timeout=effective_timeout)

    if not _check_platform_reachable_with_retries(base_url):
        console.print(f"\n{CROSS} Cannot reach platform at {base_url}")
        raise typer.Exit(1)

    console.print(f"{CHECK} Platform reachable at {base_url}\n")

    # Ensure the config file exists on disk so later Config.write() calls
    # (e.g. saving the default model) can find the cluster and context.
    # Without this, a fresh install (no config.yaml) hits "Cluster
    # 'default-cluster' does not exist" when _save_default_model runs.
    _bootstrap_config_if_missing(base_url, workspace)
    cli_context.reset_sdk_context()

    client = cli_context.get_client()

    try:
        client.workspaces.retrieve(workspace)
    except Exception:
        try:
            client.workspaces.create(name=workspace)
            console.print(f"  {CHECK} Created workspace '{workspace}'")
        except Exception as create_err:
            # Distinguish a race (workspace appeared between retrieve and create)
            # from a real failure (permissions, server error).
            try:
                client.workspaces.retrieve(workspace)
            except Exception:
                raise create_err from None

    skills_agents_list = _parse_csv_flag(skills_agents)
    skills_from_list = _parse_csv_flag(skills_from)

    if auto:
        _run_auto_mode(
            cli_context,
            client,
            workspace,
            base_url,
            install_skills,
            deploy_agent,
            skills_agents=skills_agents_list,
            skills_scope=skills_scope,
            skills_from=skills_from_list,
        )
    else:
        _run_interactive_mode(
            cli_context,
            client,
            workspace,
            base_url,
            install_skills,
            deploy_agent,
            skills_agents=skills_agents_list,
            skills_scope=skills_scope,
            skills_from=skills_from_list,
        )


def _run_auto_mode(
    cli_context: CLIContext,
    client: NeMoPlatform,
    workspace: str,
    base_url: str,
    install_skills: bool | None,
    deploy_agent: bool | None,
    *,
    skills_agents: list[str] | None = None,
    skills_scope: Scope | None = None,
    skills_from: list[str] | None = None,
) -> None:
    """Non-interactive provider registration from environment variables."""
    console.print("[bold]Auto-detecting provider from environment...[/bold]\n")
    if not _auto_setup(client, workspace):
        console.print(f"{CROSS} No provider credentials found in environment.")
        env_var_names = ", ".join(key for key, _ in _AUTO_ENV_VARS)
        console.print(f"  Set one of: {env_var_names}")
        raise typer.Exit(1)

    console.print("\n  Waiting for model discovery...")
    entity_ids: list[str] = []
    for attempt in range(_MODEL_DISCOVERY_MAX_ROUNDS):
        deadline = time.time() + _MODEL_DISCOVERY_ROUND_SECONDS
        while time.time() < deadline:
            entity_ids = _get_all_model_entity_ids(client, workspace)
            if entity_ids:
                break
            _pause(_MODEL_DISCOVERY_POLL_INTERVAL)
        if entity_ids:
            break
        if attempt < _MODEL_DISCOVERY_MAX_ROUNDS - 1:
            console.print(f"  {WARN} Models not available yet, retrying...")

    default_model = os.environ.get("NEMO_DEFAULT_MODEL", "").strip()
    if not default_model and entity_ids:
        default_model = entity_ids[0]

    if default_model:
        _save_default_model(cli_context, default_model)
        console.print(f"  {CHECK} Default model: {default_model}")
    else:
        console.print(f"  {WARN} No default model set (no models discovered yet)")
        console.print("  Run [cyan]nemo setup[/cyan] again after models sync, or set via env var:")
        console.print("    [cyan]export NEMO_DEFAULT_MODEL=<model>[/cyan]")

    _maybe_install_skills(
        auto=True,
        install_skills=install_skills,
        skills_agents=skills_agents,
        skills_scope=skills_scope,
        skills_from=skills_from,
    )
    _maybe_deploy_agent(base_url, workspace, auto=True, deploy_agent=deploy_agent, default_model=default_model)

    if _verify_platform_health(base_url):
        console.print(f"\n{CHECK} [green]Setup complete![/green]")
    else:
        raise typer.Exit(1)


def _run_interactive_mode(
    cli_context: CLIContext,
    client: NeMoPlatform,
    workspace: str,
    base_url: str,
    install_skills: bool | None,
    deploy_agent: bool | None,
    *,
    skills_agents: list[str] | None = None,
    skills_scope: Scope | None = None,
    skills_from: list[str] | None = None,
) -> None:
    """Walk the user through provider selection, credential entry, and model choice."""
    try:
        provider_name, host_url, api_key, auth_header_format, default_extra_headers = _interactive_collect_provider()

        if api_key:
            console.print("\n  Validating API key...")
            key_result = _validate_api_key(
                provider_name,
                host_url,
                api_key,
                auth_header_format=auth_header_format,
                default_extra_headers=default_extra_headers,
            )
            if not key_result.passed:
                console.print(f"  {CROSS} {key_result.message}")
                console.print("  Please check your API key and run [cyan]nemo setup[/cyan] again.")
                raise typer.Exit(1)
            if key_result.message:
                console.print(f"  {WARN} {key_result.message}")
            else:
                console.print(f"  {CHECK} API key validated")

        console.print("\n[bold]Step 3: Register model provider[/bold]\n")
        _register_provider_interactive(
            client,
            provider_name=provider_name,
            host_url=host_url,
            api_key=api_key,
            workspace=workspace,
            auth_header_format=auth_header_format,
            default_extra_headers=default_extra_headers,
        )

        console.print("\n[bold]Step 4: Discover models[/bold]\n")
        console.print("  Waiting for model discovery...")
        models = _wait_for_models(client, provider_name, workspace, host_url=host_url)
        if models:
            console.print(f"  {CHECK} Found {len(models)} model(s)")
        else:
            console.print(f"  {WARN} No models discovered yet (provider may still be syncing)")

        console.print("\n[bold]Step 5: Choose default model[/bold]\n")
        fallback_model_choices = _get_all_model_choices(client, workspace) if not models else []
        if not models and fallback_model_choices:
            console.print(f"  {WARN} Models from existing providers are available, but not from '{provider_name}' yet.")

        default_model = _select_default_model(client, workspace) if models else None
        if default_model:
            _save_default_model(cli_context, default_model)
            console.print(f"  {CHECK} Default model set to {_display_model_name(default_model)}")
        else:
            console.print(f"  {WARN} No default model set for this provider yet.")
            console.print("  Run [cyan]nemo setup[/cyan] again after models sync")

        console.print("\n[bold]Step 6: Install skills[/bold]\n")
        _maybe_install_skills(
            auto=False,
            install_skills=install_skills,
            skills_agents=skills_agents,
            skills_scope=skills_scope,
            skills_from=skills_from,
        )

        console.print("\n[bold]Step 7: Demo agent (optional)[/bold]\n")
        demo_deployed = _maybe_deploy_agent(
            base_url, workspace, auto=False, deploy_agent=deploy_agent, default_model=default_model
        )

        _print_onboarding(base_url, provider_name, default_model, demo_deployed=demo_deployed)

    except UserCancelled:
        console.print(f"\n{WARN} Setup cancelled.")
        raise typer.Exit(0) from None


def _interactive_collect_provider() -> tuple[str, str, str | None, str | None, dict[str, str] | None]:
    """Steps 1-2: select provider and collect credentials.

    Returns (provider_name, host_url, api_key, auth_header_format, default_extra_headers).
    """
    console.print("[bold]Step 1: Choose a model provider[/bold]\n")
    selected = _select_provider()

    if selected is None:
        name, host_url, api_key = _prompt_custom_provider()
        return name, host_url, api_key, None, None

    if selected.name == "ollama":
        if not _check_ollama_running(selected.host_url):
            console.print(f"\n  {WARN} Ollama does not appear to be running at {selected.host_url}")
            console.print("  Make sure Ollama is started before using it for inference.")
        else:
            console.print(f"\n  {CHECK} Ollama detected at {selected.host_url}")

    if selected.requires_api_key:
        console.print("\n[bold]Step 2: Enter API key[/bold]\n")
        api_key: str | None = _collect_credential(selected)
    else:
        api_key = None

    return selected.name, selected.host_url, api_key, selected.auth_header_format, selected.default_extra_headers


def _render_onboarding_card(value: str) -> None:
    """Print a Rich Panel card for the selected onboarding path."""
    path = _ONBOARDING_PATHS_BY_VALUE.get(value)
    if path is None:
        return

    lines: list[str] = []
    if path.note:
        lines.append(f"  [bold]{path.note}[/bold]")
        lines.append("")
    lines.append("  [bold]Ask your coding agent:[/bold]")
    lines.append(f'  [cyan]"{path.skill_prompt}"[/cyan]')
    lines.append("")
    lines.append(f"  [bold]Docs:[/bold]  [link={path.docs_url}]{path.docs_url}[/link]")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold]{path.label}[/bold]",
            title_align="left",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 1),
        )
    )


def _print_onboarding(
    base_url: str,
    provider_name: str,
    default_model: str | None,
    *,
    demo_deployed: bool = False,
) -> None:
    """Print setup summary, then present goal-oriented onboarding paths."""
    if not _verify_platform_health(base_url):
        raise typer.Exit(1)

    console.print(f"\n{CHECK} [green bold]Setup complete![/green bold]")
    console.print(f"  Provider: {provider_name}")
    if default_model:
        console.print(f"  Default model: {_display_model_name(default_model)}")
    if demo_deployed:
        console.print(f"  Demo agent: {_DEMO_AGENT_NAME}")

    console.print("\n[bold cyan]Getting started[/bold cyan]")

    options = [(p.value, p.label) for p in ONBOARDING_PATHS]
    selected = prompt_choice(
        "Select how you would like to get started",
        options,
        default="optimize",
        indent=2,
    )

    console.print()
    _render_onboarding_card(selected)
