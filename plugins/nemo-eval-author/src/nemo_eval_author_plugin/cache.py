# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# TODO(shared-module): exact copy of experimentalist components/cache.py; unify into a shared package.
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

_logger = logging.getLogger(__name__)

# PEP 695 syntax would read better, but the workspace lints against Python 3.11.
T = TypeVar("T", bound=BaseModel)


def task_hash(task_name: str) -> str:
    """Return a namespaced sha256 hex digest for a task key.

    Args:
        task_name: the task identifier to hash.

    Returns:
        str: a ``task-<hex>`` prefixed digest string.

    """
    digest = hashlib.sha256(task_name.encode()).hexdigest()
    return f"task-{digest}"


def agent_hash(agent_id: str) -> str:
    """Return a namespaced sha256 hex digest for an agent key.

    Args:
        agent_id: the agent identifier to hash.

    Returns:
        str: an ``agent-<hex>`` prefixed digest string.

    """
    digest = hashlib.sha256(agent_id.encode()).hexdigest()
    return f"agent-{digest}"


def trace_hash(trace_path: str | Path) -> str:
    """Return a namespaced sha256 hex digest of a trace file's contents.

    Args:
        trace_path: path to the trace file to hash.

    Returns:
        str: a ``trace-<hex>`` prefixed digest string.

    """
    h = hashlib.sha256()
    with open(trace_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    return f"trace-{digest}"


def _cache_path(workspace: Path, key: str) -> Path:
    return workspace / "eval-and-optimize" / "cache" / f"{key}.json"


def load(workspace: Path, key: str, model: type[T]) -> T | None:
    """Return a previously-stored model instance for this key, or None.

    Args:
        workspace: root workspace directory containing the cache.
        key: cache key returned by one of the ``*_hash`` functions.
        model: Pydantic model class used to deserialise the stored payload.

    Returns:
        T | None: the deserialised model instance, or None if the entry is
            missing, unreadable, or fails validation.

    """
    path = _cache_path(workspace, key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        _logger.warning(f"Cache read failed at {path}: {exc} -- ignoring")
        return None
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        _logger.warning(f"Cache payload at {path} does not validate against {model.__name__}: {exc} -- ignoring")
        return None


def store(workspace: Path, key: str, value: BaseModel) -> None:
    """Persist a model instance under the given key, overwriting any prior entry.

    Args:
        workspace: root workspace directory containing the cache.
        key: cache key returned by one of the ``*_hash`` functions.
        value: Pydantic model instance to serialise and store.

    """
    path = _cache_path(workspace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json")
    tmp = path.parent / f"{path.name}.{uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(path)
    except OSError as exc:
        _logger.warning(f"Cache write failed for key {key}: {exc} -- skipping")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
