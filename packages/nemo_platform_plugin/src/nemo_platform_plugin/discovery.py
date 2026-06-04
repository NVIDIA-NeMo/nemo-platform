# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin discovery — locate installed NeMo Platform plugins via entry points.

All discovery goes through the single generic :func:`discover` function, which
provides consistent fault isolation for every surface.  Every surface has a
named wrapper so callers never hardcode group strings.

Entry-point groups and their wrappers
--------------------------------------

``nemo.services``              → :func:`discover_services`              — :class:`~nemo_platform_plugin.service.NemoService` subclass  (typed, platform instantiates)
``nemo.cli``                   → :func:`discover_cli`                   — :class:`~nemo_platform_plugin.cli.NemoCLI` subclass  (typed, platform instantiates)
``nemo.jobs``                  → :func:`discover_jobs`                  — :class:`~nemo_platform_plugin.job.NemoJob` subclass  (typed, platform instantiates)
``nemo.functions``             → :func:`discover_functions`             — :class:`~nemo_platform_plugin.function.NemoFunction` subclass  (typed, platform instantiates)
``nemo.controllers``           → :func:`discover_controllers`           — :class:`~nemo_platform_plugin.controller.NemoController` subclass  (typed, platform instantiates)
``nemo.sdk``                   → :func:`discover_sdk`                   — :class:`~nemo_platform_plugin.sdk.NemoPluginSDKResources` instance
``nemo.mcp``                   → :func:`discover_mcp`                   — ``() -> list[dict]`` callable
``nemo.studio``                → :func:`discover_studio`                — ``() -> StudioSpec`` callable
``nemo.skills``                → :func:`discover_skills`                — ``() -> Path`` callable
``nemo.docs``                  → :func:`discover_docs`                  — ``() -> Path | dict`` callable
``nemo.executors``             → :func:`discover_executors`             — ``Executor`` class
``nemo.inference_middleware``  → :func:`discover_inference_middleware`  — :class:`~nemo_platform_plugin.inference_middleware.NemoInferenceMiddleware` subclass  (typed, IGW instantiates)
``nemo.seed``                  → :func:`discover_seed_jobs`             — :class:`~nemo_platform_plugin.seed.NemoSeedJob` subclass  (typed, platform instantiates)
``nemo.authz``                 → :func:`~nemo_platform_plugin.authz_discovery.discover_authz_contributions` — policy endpoints/permissions (merged at runtime and via ``auth-tools sync-plugins``)

Wrappers for surfaces whose types are not yet defined in this package return
``dict[str, Any]`` — callers cast as needed.

There is no ``nemo.plugins`` entry-point group.  :func:`discover_manifests`
assembles a :class:`~nemo_platform_plugin.interface.PluginManifest` per plugin by
scanning all known surface groups without loading their values, reading
``version`` and ``description`` from the distribution's package metadata.

Any installed plugin is discovered automatically by default. Discovery can be
scoped per surface with ``NEMO_PLUGIN_<SURFACE>_ALLOWLIST`` or globally with
``NEMO_PLUGIN_ALLOWLIST``.
"""

from __future__ import annotations

import logging
import os
from functools import cache
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING, Any, cast

from nemo_platform_plugin.interface import PluginManifest

if TYPE_CHECKING:
    from nemo_platform_plugin.cli import NemoCLI
    from nemo_platform_plugin.controller import NemoController
    from nemo_platform_plugin.function import NemoFunction
    from nemo_platform_plugin.inference_middleware import NemoInferenceMiddleware
    from nemo_platform_plugin.job import NemoJob
    from nemo_platform_plugin.seed import NemoSeedJob
    from nemo_platform_plugin.service import NemoService

logger = logging.getLogger(__name__)

# All surface groups the platform recognises.  Scanning these is sufficient to
# know whether a plugin is installed — no separate ``nemo.plugins`` group needed.
_ALL_SURFACE_GROUPS = (
    "nemo.services",
    "nemo.cli",
    "nemo.jobs",
    "nemo.functions",
    "nemo.controllers",
    "nemo.sdk",
    "nemo.mcp",
    "nemo.studio",
    "nemo.skills",
    "nemo.docs",
    "nemo.executors",
    "nemo.inference_middleware",
    "nemo.seed",
    "nemo.authz",
)

# Surface groups whose entry-point keys are dot-separated as
# ``<plugin>.<item>`` rather than the bare plugin name. Used by the
# manifest builder to map a key like ``example.greet`` back to the
# plugin name ``example``.
_DOT_SCOPED_GROUPS: frozenset[str] = frozenset({"nemo.jobs", "nemo.functions"})

_SURFACE_ALLOWLIST_ENV_VARS: dict[str, str] = {
    "nemo.services": "NEMO_PLUGIN_SERVICES_ALLOWLIST",
    "nemo.cli": "NEMO_PLUGIN_CLI_ALLOWLIST",
    "nemo.jobs": "NEMO_PLUGIN_JOBS_ALLOWLIST",
    "nemo.functions": "NEMO_PLUGIN_FUNCTIONS_ALLOWLIST",
    "nemo.controllers": "NEMO_PLUGIN_CONTROLLERS_ALLOWLIST",
    "nemo.sdk": "NEMO_PLUGIN_SDK_ALLOWLIST",
    "nemo.mcp": "NEMO_PLUGIN_MCP_ALLOWLIST",
    "nemo.studio": "NEMO_PLUGIN_STUDIO_ALLOWLIST",
    "nemo.skills": "NEMO_PLUGIN_SKILLS_ALLOWLIST",
    "nemo.docs": "NEMO_PLUGIN_DOCS_ALLOWLIST",
    "nemo.executors": "NEMO_PLUGIN_EXECUTORS_ALLOWLIST",
    "nemo.inference_middleware": "NEMO_PLUGIN_INFERENCE_MIDDLEWARE_ALLOWLIST",
    "nemo.seed": "NEMO_PLUGIN_SEED_ALLOWLIST",
    "nemo.authz": "NEMO_PLUGIN_AUTHZ_ALLOWLIST",
}


def _manifest_plugin_name(group: str, entry_point_name: str) -> str:
    if group in _DOT_SCOPED_GROUPS:
        return entry_point_name.split(".", 1)[0]
    return entry_point_name


def _plugin_allowlist(group: str) -> set[str] | None:
    # Set NEMO_PLUGIN_<SURFACE>_ALLOWLIST="" to disable plugin discovery for a surface,
    # or NEMO_PLUGIN_ALLOWLIST="" to disable all plugin discovery.
    env_var = _SURFACE_ALLOWLIST_ENV_VARS.get(group)
    if env_var is not None and env_var in os.environ:
        value = os.environ[env_var]
    else:
        value = os.environ.get("NEMO_PLUGIN_ALLOWLIST")
    if value is None or value == "*":
        return None
    return {name.strip() for name in value.split(",") if name.strip()}


@cache
def discover_entry_points(group: str) -> dict[str, EntryPoint]:
    """Discover installed entry points for *group* without loading values.

    Results are cached per *group* for the lifetime of the process. Call
    ``discover_entry_points.cache_clear()`` in tests (or wherever dynamic plugin
    changes are needed) to reset the cache.

    This is the metadata-only discovery path intended for callers that only
    need to know which plugins or commands exist. It avoids importing plugin
    code and therefore avoids import-time side effects.

    Args:
        group: The entry-point group to scan (e.g. ``"nemo.cli"``).

    Returns:
        Mapping of entry-point name → entry-point metadata object.
    """
    allowlist = _plugin_allowlist(group)
    return {
        ep.name: ep
        for ep in entry_points(group=group)
        if allowlist is None or _manifest_plugin_name(group, ep.name) in allowlist
    }


@cache
def discover(group: str) -> dict[str, Any]:
    """Discover installed entry points for *group* with fault isolation.

    Results are cached per *group* for the lifetime of the process.  Call
    ``discover.cache_clear()`` in tests (or wherever dynamic plugin changes
    are needed) to reset the cache.

    This is the single implementation shared by every surface.  Callers that
    need typed results use the typed wrappers or cast the return value.

    Args:
        group: The entry-point group to scan (e.g. ``"nemo.cli"``).

    Returns:
        Mapping of entry-point name → loaded value for every entry that
        loaded successfully.  Entries that raise on load are logged as a
        warning and excluded.
    """
    result: dict[str, Any] = {}

    for ep in discover_entry_points(group).values():
        try:
            result[ep.name] = ep.load()
            logger.debug("Loaded %r from %r (%s)", ep.name, group, ep.value)
        except Exception:
            logger.warning(
                "Failed to load %r from %r (%s) — skipping",
                ep.name,
                group,
                ep.value,
            )
            logger.debug(
                "Traceback for failed load of %r from %r:",
                ep.name,
                group,
                exc_info=True,
            )

    return result


@cache
def discover_manifests() -> dict[str, PluginManifest]:
    """Derive plugin manifests by scanning all known surface entry-point groups.

    Results are cached for the lifetime of the process.  Call
    ``discover_manifests.cache_clear()`` in tests to reset.

    No ``nemo.plugins`` entry point is required.  Each unique name found across
    any surface group becomes one :class:`~nemo_platform_plugin.interface.PluginManifest`.
    ``version`` and ``description`` are read from the installing distribution's
    package metadata (``Version`` / ``Summary`` fields).

    Entry-point values are **not loaded** — this function is cheap and has no
    import side-effects.
    """
    manifests: dict[str, PluginManifest] = {}

    for group in _ALL_SURFACE_GROUPS:
        for ep in discover_entry_points(group).values():
            plugin_name = _manifest_plugin_name(group, ep.name)
            if plugin_name in manifests:
                continue
            try:
                dist = ep.dist
                # ``dist.metadata`` is ``email.message.Message``-compatible
                # and supports ``.get`` at runtime; ty's stub for
                # ``importlib.metadata.PackageMetadata`` doesn't expose it.
                version = dist.metadata.get("Version", "") if dist is not None else ""  # ty: ignore[unresolved-attribute]
                description = dist.metadata.get("Summary", "") if dist is not None else ""  # ty: ignore[unresolved-attribute]
            except Exception:
                version = ""
                description = ""
            manifests[plugin_name] = PluginManifest(
                name=plugin_name,
                version=version,
                description=description,
            )
            logger.debug("Discovered plugin %r (v%s) via %r", plugin_name, version, group)

    return manifests


def discover_services() -> dict[str, type[NemoService]]:
    """Typed wrapper: discover ``nemo.services`` → :class:`~nemo_platform_plugin.service.NemoService` subclass.

    The platform instantiates each class and wraps it in a ``NemoServiceAdapter``
    before mounting it.  Plugin authors never interact with the adapter.

    Validates that each class's ``name`` attribute matches its entry-point key.
    A mismatch is logged as a warning — the entry-point key always wins for
    routing purposes.
    """
    from nemo_platform_plugin.service import NemoService

    raw = discover("nemo.services")
    result: dict[str, type[NemoService]] = {}
    for key, cls in raw.items():
        cls_name = getattr(cls, "name", None)
        if cls_name != key:
            logger.warning(
                "nemo.services entry %r: class %s declares name=%r — "
                "name must match the pyproject.toml entry-point key",
                key,
                getattr(cls, "__qualname__", cls),
                cls_name,
            )
        result[key] = cast(type[NemoService], cls)
    return result


def discover_cli() -> dict[str, type[NemoCLI]]:
    """Typed wrapper: discover ``nemo.cli`` → :class:`~nemo_platform_plugin.cli.NemoCLI` subclass.

    The platform instantiates each class and calls :meth:`~nemo_platform_plugin.cli.NemoCLI.get_cli`
    to obtain the :class:`typer.Typer` app.

    Validates that each class's ``name`` attribute matches its entry-point key.
    """
    from nemo_platform_plugin.cli import NemoCLI

    raw = discover("nemo.cli")
    result: dict[str, type[NemoCLI]] = {}
    for key, cls in raw.items():
        cls_name = getattr(cls, "name", None)
        if cls_name != key:
            logger.warning(
                "nemo.cli entry %r: class %s declares name=%r — name must match the pyproject.toml entry-point key",
                key,
                getattr(cls, "__qualname__", cls),
                cls_name,
            )
        result[key] = cast(type[NemoCLI], cls)
    return result


def discover_jobs() -> dict[str, type[NemoJob]]:
    """Typed wrapper: discover ``nemo.jobs`` → :class:`~nemo_platform_plugin.job.NemoJob` subclass.

    Entry-point key convention: ``<plugin-name>.<job-name>`` (e.g.
    ``"example.say-hello"``).  The platform instantiates each class and calls
    :meth:`~nemo_platform_plugin.job.NemoJob.run` with the job config dict — programmatic
    callers drive that through
    :meth:`nemo_platform_plugin.scheduler.NemoJobScheduler.run_local`.

    Validates that each class's ``name`` attribute matches the job-name suffix
    of its entry-point key (the part after the first ``"."``).
    """
    from nemo_platform_plugin.job import NemoJob

    raw = discover("nemo.jobs")
    result: dict[str, type[NemoJob]] = {}
    for key, cls in raw.items():
        expected_suffix = key.split(".", 1)[-1] if "." in key else key
        cls_name = getattr(cls, "name", None)
        if cls_name != expected_suffix:
            logger.warning(
                "nemo.jobs entry %r: class %s declares name=%r but key suffix is %r — "
                "NemoJob.name must match the job-name part of the pyproject.toml entry-point key",
                key,
                getattr(cls, "__qualname__", cls),
                cls_name,
                expected_suffix,
            )
        result[key] = cast(type[NemoJob], cls)
    return result


def discover_functions() -> dict[str, type[NemoFunction]]:
    """Typed wrapper: discover ``nemo.functions`` → :class:`~nemo_platform_plugin.function.NemoFunction` subclass.

    Entry-point key convention: ``<plugin-name>.<function-name>`` (e.g.
    ``"example.greet"``). The platform instantiates each class and
    invokes :meth:`~nemo_platform_plugin.function.NemoFunction.run` per request
    (HTTP) or per CLI invocation (``nemo <plugin> <fn> run``); the
    function adapter wires signature-based DI for ``ctx`` / ``sdk`` /
    ``async_sdk``.

    Validates that each class's ``name`` attribute matches the
    function-name suffix of its entry-point key (the part after the
    first ``"."``). A mismatch is logged as a warning — the entry-point
    key always wins for routing purposes.
    """
    from nemo_platform_plugin.function import NemoFunction

    raw = discover("nemo.functions")
    result: dict[str, type[NemoFunction]] = {}
    for key, cls in raw.items():
        expected_suffix = key.split(".", 1)[-1] if "." in key else key
        cls_name = getattr(cls, "name", None)
        if cls_name != expected_suffix:
            logger.warning(
                "nemo.functions entry %r: class %s declares name=%r but key suffix is %r — "
                "NemoFunction.name must match the function-name part of the pyproject.toml entry-point key",
                key,
                getattr(cls, "__qualname__", cls),
                cls_name,
                expected_suffix,
            )
        result[key] = cast(type[NemoFunction], cls)
    return result


def discover_controllers() -> dict[str, type[NemoController]]:
    """Typed wrapper: discover ``nemo.controllers`` → :class:`~nemo_platform_plugin.controller.NemoController` subclass.

    The platform instantiates each class and wraps it in a
    ``NemoControllerAdapter`` that bridges the async :meth:`~nemo_platform_plugin.controller.NemoController.reconcile`
    method into the platform's thread-based ``Loop`` / ``Controller`` framework.

    Validates that each class's ``name`` attribute matches its entry-point key.
    A mismatch is logged as a warning — the entry-point key always wins for
    identification purposes.
    """
    from nemo_platform_plugin.controller import NemoController

    raw = discover("nemo.controllers")
    result: dict[str, type[NemoController]] = {}
    for key, cls in raw.items():
        cls_name = getattr(cls, "name", None)
        if cls_name != key:
            logger.warning(
                "nemo.controllers entry %r: class %s declares name=%r — "
                "name must match the pyproject.toml entry-point key",
                key,
                getattr(cls, "__qualname__", cls),
                cls_name,
            )
        result[key] = cast(type[NemoController], cls)
    return result


def discover_seed_jobs() -> dict[str, type[NemoSeedJob]]:
    """Typed wrapper: discover ``nemo.seed`` → :class:`~nemo_platform_plugin.seed.NemoSeedJob` subclass.

    The platform's seed task instantiates each class and calls
    :meth:`~nemo_platform_plugin.seed.NemoSeedJob.run` after injecting the SDK and
    entity client.

    Validates that each class's ``name`` attribute matches its entry-point key.
    """
    from nemo_platform_plugin.seed import NemoSeedJob

    raw = discover("nemo.seed")
    result: dict[str, type[NemoSeedJob]] = {}
    for key, cls in raw.items():
        cls_name = getattr(cls, "name", None)
        if cls_name != key:
            logger.warning(
                "nemo.seed entry %r: class %s declares name=%r — name must match the pyproject.toml entry-point key",
                key,
                getattr(cls, "__qualname__", cls),
                cls_name,
            )
        result[key] = cast(type[NemoSeedJob], cls)
    return result


def discover_sdk() -> dict[str, Any]:
    """Wrapper: discover ``nemo.sdk`` → SDK plugin resource container.

    Each entry-point value should be a :class:`~nemo_platform_plugin.sdk.NemoPluginSDKResources`
    instance with one or both of these attributes:

    - ``sync_resource``: resource class for ``NeMoPlatform``.
    - ``async_resource``: resource class for ``AsyncNeMoPlatform``.

    If one side is omitted, accessing that plugin namespace on the corresponding
    client raises ``AttributeError``.

    The platform lazily instantiates these through ``__getattr__`` so plugin
    SDK namespaces appear as client attributes (for example ``client.example``).
    """
    return discover("nemo.sdk")


def discover_mcp() -> dict[str, Any]:
    """Wrapper: discover ``nemo.mcp`` → ``() -> list[dict]`` callable.

    Each entry-point value should be a zero-argument callable that returns a
    list of MCP tool definition dicts.
    """
    return discover("nemo.mcp")


def discover_studio() -> dict[str, Any]:
    """Wrapper: discover ``nemo.studio`` → ``() -> StudioSpec`` callable.

    Each entry-point value should be a zero-argument callable that returns a
    ``StudioSpec`` describing the plugin's Studio web-UI page.
    """
    return discover("nemo.studio")


def discover_skills() -> dict[str, Any]:
    """Wrapper: discover ``nemo.skills`` → ``() -> Path`` callable.

    Each entry-point value should be a zero-argument callable that returns a
    :class:`pathlib.Path` to a directory of agent skill markdown files.
    """
    return discover("nemo.skills")


def discover_docs() -> dict[str, Any]:
    """Wrapper: discover ``nemo.docs`` → ``() -> Path | dict`` callable.

    Each entry-point value should be a zero-argument callable that returns
    either a :class:`pathlib.Path` (plain markdown) or a dict with keys
    ``path``, ``format``, and optionally ``exclude``.
    """
    return discover("nemo.docs")


def discover_executors() -> dict[str, Any]:
    """Wrapper: discover ``nemo.executors`` → ``Executor`` class.

    Each entry-point value should be a class implementing the ``Executor``
    protocol.  The entry-point name is the cluster ``kind`` (e.g. ``"slurm"``,
    ``"k8s"``), used by the platform's job scheduler to resolve the right backend.
    """
    return discover("nemo.executors")


def discover_inference_middleware() -> dict[str, type[NemoInferenceMiddleware]]:
    """Typed wrapper: discover ``nemo.inference_middleware`` entry-points.

    Returns a dict keyed by entry-point key (e.g. ``"nemo-switchyard"``) mapping
    to the :class:`~nemo_platform_plugin.inference_middleware.NemoInferenceMiddleware`
    subclass registered under that key.

    The entry-point key is the plugin identity — it is what
    :attr:`~nemo_platform_plugin.inference_middleware.MiddlewareCall.name` references in
    VirtualModel configs, and what IGW uses to key its plugin registry.
    """
    from nemo_platform_plugin.inference_middleware import NemoInferenceMiddleware

    return {key: cast(type[NemoInferenceMiddleware], cls) for key, cls in discover("nemo.inference_middleware").items()}
