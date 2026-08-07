# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load :class:`FabricTaskRunHook` implementations from string references.

Authors register hooks without baking agent-specific code into the platform.
YAML may point at:

* ``ref`` — ``module.path:Attr`` (importable object)
* ``path`` + ``attr`` — Python file on disk (no package install required)
* ``entry_point`` / ``type`` — name under ``nemo.fabric.task_hooks``

Remaining mapping keys are forwarded as constructor kwargs.
"""

import importlib
import importlib.metadata
import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nemo_platform.beta.evaluator.agent_eval.runtimes.fabric.hooks import FabricTaskRunHook

FABRIC_TASK_HOOKS_GROUP = "nemo.fabric.task_hooks"

_RESERVED = frozenset({"ref", "path", "attr", "entry_point", "type"})


class FabricTaskHookLoadError(RuntimeError):
    """Raised when a Fabric task-hook reference cannot be resolved or constructed."""


def load_fabric_task_hook(spec: Mapping[str, Any] | None) -> FabricTaskRunHook | None:
    """Construct a task hook from a mapping, or return ``None`` when ``spec`` is unset."""
    if spec is None:
        return None
    if not isinstance(spec, Mapping):
        raise FabricTaskHookLoadError("run_hook spec must be a mapping when set.")

    ref = _optional_str(spec.get("ref"))
    path = _optional_str(spec.get("path"))
    attr = _optional_str(spec.get("attr"))
    entry_point = _optional_str(spec.get("entry_point")) or _optional_str(spec.get("type"))

    modes = [bool(ref), bool(path), bool(entry_point)]
    if sum(modes) == 0:
        raise FabricTaskHookLoadError(
            "run_hook requires one of: ref (module:attr), path+attr (file), or entry_point/type (nemo.fabric.task_hooks)."
        )
    if sum(modes) > 1:
        raise FabricTaskHookLoadError("run_hook accepts only one of: ref, path, or entry_point/type.")

    if path and not attr:
        raise FabricTaskHookLoadError("run_hook.path requires run_hook.attr (class or factory name).")

    if ref:
        target = _load_from_ref(ref)
    elif path:
        target = _load_from_path(Path(path).expanduser(), attr=attr or "")
    else:
        target = _load_from_entry_point(entry_point or "")

    kwargs = {key: value for key, value in spec.items() if key not in _RESERVED}
    return _construct_hook(target, kwargs)


def _construct_hook(target: Any, kwargs: dict[str, Any]) -> FabricTaskRunHook:
    if callable(target) and not isinstance(target, type):
        # Module-level factory function.
        hook = target(**kwargs) if kwargs else target()
    elif isinstance(target, type):
        hook = target(**kwargs) if kwargs else target()
    else:
        if kwargs:
            raise FabricTaskHookLoadError("run_hook target is already an instance; constructor kwargs are not allowed.")
        hook = target

    for method in ("prepare", "after_success", "cleanup"):
        if not callable(getattr(hook, method, None)):
            raise FabricTaskHookLoadError(f"run_hook object missing required method {method!r}.")
    return hook  # type: ignore[return-value]


def _load_from_ref(ref: str) -> Any:
    module_name, _, attr_path = ref.partition(":")
    if not module_name or not attr_path:
        raise FabricTaskHookLoadError(f"run_hook.ref must look like 'module.path:Attr', got {ref!r}.")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise FabricTaskHookLoadError(f"Could not import run_hook.ref module {module_name!r}.") from exc
    return _resolve_attr(module, attr_path, label=f"run_hook.ref {ref!r}")


def _load_from_path(path: Path, attr: str) -> Any:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FabricTaskHookLoadError(f"run_hook.path does not exist: {resolved}")
    module_name = f"_nemo_fabric_task_hook_{resolved.stem}_{abs(hash(str(resolved)))}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise FabricTaskHookLoadError(f"Could not load run_hook.path: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise FabricTaskHookLoadError(f"Failed executing run_hook.path {resolved}: {exc}") from exc
    return _resolve_attr(module, attr, label=f"run_hook.path attr {attr!r}")


def _load_from_entry_point(name: str) -> Any:
    matches = [ep for ep in importlib.metadata.entry_points(group=FABRIC_TASK_HOOKS_GROUP) if ep.name == name]
    if not matches:
        raise FabricTaskHookLoadError(
            f"No entry point {name!r} in group {FABRIC_TASK_HOOKS_GROUP!r}. "
            "Authors register hooks via packaging entry points, or use run_hook.ref / run_hook.path."
        )
    try:
        return matches[0].load()
    except Exception as exc:
        raise FabricTaskHookLoadError(f"Failed to load entry point {name!r} from {FABRIC_TASK_HOOKS_GROUP!r}.") from exc


def _resolve_attr(module: Any, attr_path: str, label: str) -> Any:
    current = module
    for part in attr_path.split("."):
        if not hasattr(current, part):
            raise FabricTaskHookLoadError(f"{label} not found.")
        current = getattr(current, part)
    return current


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
