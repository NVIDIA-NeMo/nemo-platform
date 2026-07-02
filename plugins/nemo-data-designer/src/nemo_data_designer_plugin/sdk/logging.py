# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import inspect
import logging
from contextlib import contextmanager
from functools import wraps
from typing import Generator, TypeVar

from data_designer.logging import _make_stream_formatter

_DD_LOGGER_NAME = "nemo_data_designer_plugin"


@contextmanager
def _ensure_logging_handler() -> Generator[None, None, None]:
    """Attach a logging handler to the data_designer logger if none is configured.

    If the logger (or any of its ancestors) already has handlers, this is a no-op,
    preventing duplicate log output when the caller has configured logging themselves.
    The temporarily added handler is removed on exit.
    """
    dd_logger = logging.getLogger(_DD_LOGGER_NAME)
    handler: logging.Handler | None = None
    if not dd_logger.hasHandlers():
        handler = logging.StreamHandler()
        handler.setFormatter(_make_stream_formatter())
        dd_logger.addHandler(handler)
        dd_logger.setLevel("INFO")
    try:
        yield
    finally:
        if handler is not None:
            dd_logger.removeHandler(handler)


_ClsT = TypeVar("_ClsT", bound=type)


def with_logging(cls: _ClsT) -> _ClsT:
    """Wrap public methods so SDK logging is configured on demand.

    This ensures logging is configured for every public method call without
    requiring manual wrapping. Nesting is safe: if the handler is already active
    (e.g. one public method calls another), the inner entry is a no-op.
    """
    for name, method in vars(cls).items():
        if name.startswith("_") or isinstance(method, (staticmethod, classmethod)):
            continue
        if inspect.iscoroutinefunction(method):

            @wraps(method)
            async def async_wrapper(self, *args, _m=method, **kwargs):
                with _ensure_logging_handler():
                    return await _m(self, *args, **kwargs)

            setattr(cls, name, async_wrapper)
        elif inspect.isfunction(method):

            @wraps(method)
            def sync_wrapper(self, *args, _m=method, **kwargs):
                with _ensure_logging_handler():
                    return _m(self, *args, **kwargs)

            setattr(cls, name, sync_wrapper)
    return cls
