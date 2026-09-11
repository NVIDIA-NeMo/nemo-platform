# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Signature-based dependency helpers for ``NemoJob.run``.

Both local scheduler execution and platform-launched task containers use
these helpers to bind supported keyword-only parameters on job ``run``
methods. Keeping this surface separate avoids making lightweight task
entrypoints import scheduler submission machinery.
"""

from __future__ import annotations

import inspect
from types import UnionType
from typing import Annotated, Callable, Union, get_args, get_origin, get_type_hints

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext

_UNBOUND = object()
"""Sentinel meaning "leave the parameter unbound" — the kwarg is omitted so
Python applies the run signature's own default."""


class LocalRunError(RuntimeError):
    """Raised when a required ``sdk`` / ``async_sdk`` parameter on
    :meth:`NemoJob.run` has no handle to bind."""


def resolve_run_kwargs(
    job_cls: type[NemoJob],
    run: Callable[..., object],
    *,
    sdk: object | None,
    async_sdk: object | None,
    ctx: JobContext,
    is_local: bool,
) -> dict[str, object]:
    """Bind keyword-only parameters on *run* by name.

    Recognises ``ctx``, ``sdk``, ``async_sdk``, and ``is_local`` on the
    keyword-only portion of *run*'s signature; everything else is left
    unbound so Python's own default applies. ``is_local`` lets jobs adapt
    behaviour to the execution context — ``True`` from the local scheduler,
    ``False`` from the platform task dispatcher.

    Raises:
        LocalRunError: When *run* declares a required ``sdk`` /
            ``async_sdk`` parameter with no default and the corresponding
            handle is not supplied.
    """
    try:
        sig = inspect.signature(run)
    except (TypeError, ValueError):
        # Builtins / C-extension callables have no inspectable
        # signature; fall back to calling with just the config dict.
        return {}

    # Drop the first positional — the caller passes ``config`` by position.
    params = list(sig.parameters.values())
    if params and params[0].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        params = params[1:]

    type_hints = _get_run_type_hints(run)
    resolved: dict[str, object] = {}
    for param in params:
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        binding = _resolve_run_param(
            job_cls=job_cls,
            param=param,
            annotation=type_hints.get(param.name, param.annotation),
            sdk=sdk,
            async_sdk=async_sdk,
            ctx=ctx,
            is_local=is_local,
        )
        if binding is _UNBOUND:
            continue
        resolved[param.name] = binding
    return resolved


def _resolve_run_param(
    *,
    job_cls: type[NemoJob],
    param: inspect.Parameter,
    annotation: object,
    sdk: object | None,
    async_sdk: object | None,
    ctx: JobContext,
    is_local: bool,
) -> object:
    """Resolve a single ``run`` parameter or return :data:`_UNBOUND`."""
    required = param.default is inspect.Parameter.empty

    if param.name == "ctx":
        return ctx

    if param.name == "is_local":
        return is_local

    if param.name == "sdk":
        if sdk is not None:
            return _adapt_sync_sdk_for_annotation(sdk, annotation)
        if required:
            raise LocalRunError(
                f"{job_cls.__name__}.run requires a `sdk` argument; "
                f"pass it via NemoJobScheduler.run_local(sdk=...) or "
                f"nemo_platform_plugin.tasks.dispatcher.run_task(sdk=...)."
            )
        return _UNBOUND

    if param.name == "async_sdk":
        if async_sdk is not None:
            return _adapt_async_sdk_for_annotation(async_sdk, annotation)
        if required:
            raise LocalRunError(
                f"{job_cls.__name__}.run requires an `async_sdk` "
                f"argument; pass it via "
                f"NemoJobScheduler.run_local(async_sdk=...) or "
                f"nemo_platform_plugin.tasks.dispatcher.run_task(async_sdk=...)."
            )
        return _UNBOUND

    if required:
        # Surface as LocalRunError instead of a downstream TypeError.
        raise LocalRunError(
            f"{job_cls.__name__}.run declares unsupported required parameter "
            f"`{param.name}`; only `ctx`, `sdk`, `async_sdk`, and `is_local` "
            "are injected automatically."
        )

    return _UNBOUND


def _get_run_type_hints(run: Callable[..., object]) -> dict[str, object]:
    """Resolve postponed annotations for dependency adaptation.

    Dependency injection is a runtime boundary, but the adaptation decision is
    driven by the static ``run`` signature rather than each job branching on
    unrelated SDK types.
    """
    try:
        return get_type_hints(run)
    except (AttributeError, NameError, TypeError, ValueError):
        return {}


def _adapt_sync_sdk_for_annotation(sdk: object, annotation: object) -> object:
    client_cls = _sync_client_class_from_annotation(annotation)
    if client_cls is not None and isinstance(sdk, NeMoPlatform):
        return client_from_platform(sdk, client_cls)
    return sdk


def _adapt_async_sdk_for_annotation(async_sdk: object, annotation: object) -> object:
    client_cls = _async_client_class_from_annotation(annotation)
    if client_cls is not None and isinstance(async_sdk, AsyncNeMoPlatform):
        return client_from_platform(async_sdk, client_cls)
    return async_sdk


def _sync_client_class_from_annotation(annotation: object) -> type[NemoClient] | None:
    if isinstance(annotation, type) and issubclass(annotation, NemoClient):
        return annotation

    origin = get_origin(annotation)
    if origin is Annotated:
        return _sync_client_class_from_annotation(get_args(annotation)[0])
    if origin in (Union, UnionType):
        for arg in get_args(annotation):
            client_cls = _sync_client_class_from_annotation(arg)
            if client_cls is not None:
                return client_cls
    return None


def _async_client_class_from_annotation(annotation: object) -> type[AsyncNemoClient] | None:
    if isinstance(annotation, type) and issubclass(annotation, AsyncNemoClient):
        return annotation

    origin = get_origin(annotation)
    if origin is Annotated:
        return _async_client_class_from_annotation(get_args(annotation)[0])
    if origin in (Union, UnionType):
        for arg in get_args(annotation):
            client_cls = _async_client_class_from_annotation(arg)
            if client_cls is not None:
                return client_cls
    return None


__all__ = ["LocalRunError", "resolve_run_kwargs"]
