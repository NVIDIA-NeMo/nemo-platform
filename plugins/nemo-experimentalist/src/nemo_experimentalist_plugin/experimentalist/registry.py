# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Components are found by ``(role, name)``, and our own register like anyone else's.

This is the whole plugin mechanism. A developer writes a component in *their* package,
ships one entry point, ``pip install``s it beside this one, and selects it by name in
config — without ever checking out this repository:

    [project.entry-points."nemo.experimentalist.components"]
    "strategy.bandit" = "acme_strategies.bandit"

The entry point's only job is to import the module, so the ``__init_subclass__`` below
fires and the class registers itself. First-party components need no entry point: they
register by being imported, which :func:`load_plugins` also arranges.

Two behaviours are deliberately different:

* **Resolving** a named component raises on an unknown name. Never skip, never fall back
  to a default: a run configured for ``strategy: bandit`` that quietly runs the
  evolutionary loop instead has produced a result for a question nobody asked.
* **Enumerating** degrades. One third-party package that fails to import must not take
  down a run that does not use it — the failure is logged, and asking for that component
  by name still raises with the reason attached.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from importlib.metadata import entry_points
from typing import Any, ClassVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

#: Entry-point group third parties ship their components in.
ENTRY_POINT_GROUP = "nemo.experimentalist.components"

#: Import failures from :func:`load_plugins`, keyed by entry-point name, so a later
#: resolution failure can say *why* the component is missing rather than only that it is.
_LOAD_FAILURES: dict[str, str] = {}

_loaded = False


def _identity(component: type["Component"]) -> tuple[str, str]:
    """Where a component class is defined, which is what makes two of them the same one."""
    return (component.__module__, component.__qualname__)


class Component:
    """Base of every resolvable component. Subclassing with a name registers it.

    ``role`` says what slot this fills (``"strategy"``, ``"builder"``, …) and ``name``
    which implementation it is. A class that sets ``role`` but no ``name`` is a role base
    class — ``Strategy``, ``Builder`` — and stays unregistered, which is what lets the
    roles be declared here without pretending to be implementations.
    """

    role: ClassVar[str] = ""
    name: ClassVar[str] = ""

    #: Pydantic model this component's ``<role>_config`` slice is validated against.
    #: Declared by the component because the component owns its settings: the run config
    #: carries that slice as a plain mapping, so a component from another package is
    #: configurable without this repo knowing its fields. ``None`` means it takes none.
    config_type: ClassVar[type[BaseModel] | None] = None

    #: Every registered component, keyed by ``(role, name)``. Private: mutating it
    #: from outside ``__init_subclass__`` is how a name silently stops meaning what
    #: it resolved to a moment ago.
    _registry: ClassVar[dict[tuple[str, str], type["Component"]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # Cooperative: nooa's Agent also defines __init_subclass__ and consumes its own
        # keywords, so a component that is both an Agent and a Component registers only
        # because both links in the chain call up.
        super().__init_subclass__(**kwargs)
        # `role` is inherited on purpose — CodeEditBuilder gets "builder" from Builder. `name` is
        # read from this class alone: inheriting it would make `class MyCoder(CodeEditBuilder)`
        # look like a second claim on "code-edit" and raise at import, which is the most
        # obvious way someone customises a built-in Builder. A subclass registers by
        # naming itself, or not at all.
        role, name = cls.__dict__.get("role", cls.role), cls.__dict__.get("name", "")
        if not (role and name):
            return
        key = (role, name)
        existing = Component._registry.get(key)
        # By module and qualname, not object identity: a module executed twice — reloaded,
        # or reachable under two import paths — re-registers rather than clashing with
        # itself. Two *different* classes claiming one name still raises.
        if existing is not None and _identity(existing) != _identity(cls):
            raise RuntimeError(
                f"duplicate component {role}.{name}: {existing.__module__}.{existing.__qualname__} "
                f"and {cls.__module__}.{cls.__qualname__}"
            )
        Component._registry[key] = cls


def load_plugins(*, force: bool = False) -> None:
    """Import every installed component package so its classes self-register.

    Idempotent. A broken third-party entry point is logged and skipped rather than
    raised, so it only breaks runs that actually name it.
    """
    global _loaded
    if _loaded and not force:
        return
    # Marked loaded only after a full pass. Setting it up front means that if
    # ``entry_points()`` itself raises, discovery is recorded as done and never retried —
    # every later resolution then fails for a component that is installed and fine.
    _LOAD_FAILURES.clear()
    for entry_point in entry_points(group=ENTRY_POINT_GROUP):
        try:
            entry_point.load()
        except Exception as exc:  # noqa: BLE001 - one bad plugin must not kill unrelated runs
            _LOAD_FAILURES[entry_point.name] = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "[REGISTRY] component entry point %r (%s) failed to import; components it "
                "provides will not resolve: %s",
                entry_point.name,
                entry_point.value,
                exc,
            )
    _loaded = True


def registered(role: str) -> list[str]:
    """Names registered for *role*, sorted. What ``strategies list`` will read."""
    load_plugins()
    return sorted(name for registered_role, name in Component._registry if registered_role == role)


def resolve(role: str, name: str) -> type[Component]:
    """The class registered as *(role, name)*.

    Raises:
        LookupError: if nothing is registered under that name. The message lists what is,
            and names any plugin that failed to import — the usual cause of a name that
            the user is certain they installed.
    """
    load_plugins()
    component = Component._registry.get((role, name))
    if component is not None:
        return component
    known = registered(role) or ["(none)"]
    detail = f"; known {role}: {', '.join(known)}"
    if _LOAD_FAILURES:
        broken = "; ".join(f"{ep} ({why})" for ep, why in sorted(_LOAD_FAILURES.items()))
        detail += f". Note these component packages failed to import: {broken}"
    raise LookupError(f"no {role} registered as {name!r}{detail}")


def get_component(role: str, name: str, **kwargs: Any) -> Any:
    """Resolve *(role, name)* and construct it.

    Construction arguments are the consuming strategy's business, not the registry's, so
    *kwargs* pass through untouched — except ``config``, which is validated against the
    resolved component's own ``config_type``. That is what lets the run config keep each
    ``<role>_config`` as a plain mapping: a third-party component validates its settings
    with its own model, and a typo still fails while the run is starting rather than at
    round three, an hour of image builds later.
    """
    component = resolve(role, name)
    config = kwargs.get("config")
    if component.config_type is not None and isinstance(config, Mapping):
        kwargs["config"] = component.config_type.model_validate(dict(config))
    return component(**kwargs)
