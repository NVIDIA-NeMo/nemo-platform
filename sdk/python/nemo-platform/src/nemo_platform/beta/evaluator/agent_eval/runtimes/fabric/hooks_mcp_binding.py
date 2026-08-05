# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Platform Fabric task hook for per-task MCP bindings (path-first).

**Static MCP (no hook):** declare ``mcp.servers`` (transport, url, exposure, env, args) in the
optimize / Fabric YAML. That is the hero path for fixed stdio MCP servers.

**Bound MCP (this hook):** use when the agent needs run-scoped MCP state (private input
binding, audit/verify, optional credential handoff). Configure via::

    eval:
      run_hook:
        type: mcp_run_binding
        agent_src: ${AGENT_SRC}          # path-first: checkout .../src on sys.path
        bindings:
          - server: my-mcp               # must match mcp.servers key
            binding: my_pkg.audit:RunBinding
            executable: ${AGENT_MCP_BIN} # MCP process from agent's own venv
            config_paths: [settings.yaml]
            handoff:                     # optional; at most one per binding
              env: NVIDIA_API_KEY
              ref: my_pkg.handoff:CredentialHandoff

``mcp.servers`` still owns transport / placeholder url / exposure / env / args. This hook
only rebinds ``url`` to ``binding.mcp_command`` after ``Binding.create``, preserving
top-level ``env`` and ``args``.

**Agent protocol (duck-typed, in the agent checkout):**

* ``Binding.create(prompt, parent, **kwargs) -> binding``
* ``binding.mcp_command`` — path/URL for this task
* ``binding.verify()`` or ``verify_exactly_once()`` — fail the trial on audit breach
* ``binding.cleanup()``
* Optional handoff: ``Handoff.start(credential, timeout_seconds=...)`` with
  ``.socket_path`` / ``.token`` / ``.close()``

Path isolation: do **not** pip-install the agent into the platform venv. Point
``agent_src`` at the checkout and ``executable`` at the agent-owned MCP binary.
Binding/handoff modules load into the platform process — keep them lightly dependent;
heavy runtime stays behind the MCP stdio boundary.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class McpRunBindingHookError(RuntimeError):
    """Raised when MCP run-binding configuration or lifecycle fails."""


def _load_ref(ref: str) -> Any:
    """Load ``module.path:Attr`` or ``/abs/or/rel/file.py:Attr``."""
    module_name, _, attr = ref.partition(":")
    if not module_name or not attr:
        raise McpRunBindingHookError(f"ref must look like 'module.path:Attr' or 'file.py:Attr', got {ref!r}")

    path = Path(module_name).expanduser()
    if path.suffix == ".py" or path.is_file():
        resolved = path.resolve()
        if not resolved.is_file():
            raise McpRunBindingHookError(f"ref file does not exist: {resolved}")
        mod_name = f"_mcp_run_binding_{resolved.stem}_{abs(hash(str(resolved)))}"
        spec = importlib.util.spec_from_file_location(mod_name, resolved)
        if spec is None or spec.loader is None:
            raise McpRunBindingHookError(f"could not load ref file: {resolved}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_name)

    current: Any = module
    for part in attr.split("."):
        current = getattr(current, part)
    return current


def _resolve_target(value: Any) -> Any:
    """Resolve a string ref or pass through an already-imported class/callable."""
    if isinstance(value, str):
        return _load_ref(value.strip())
    if value is None:
        raise McpRunBindingHookError("binding/handoff ref is required")
    return value


def _prepend_sys_path(path: str | Path) -> None:
    resolved = str(Path(path).expanduser().resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def _as_path_list(value: Any) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, (str, Path)):
        items: Sequence[Any] = [value]
    elif isinstance(value, Sequence):
        items = value
    else:
        raise McpRunBindingHookError(f"config_paths must be a path or list of paths, got {type(value)!r}")
    paths: list[Path] = []
    for item in items:
        path = Path(item).expanduser()
        if not path.is_file():
            raise McpRunBindingHookError(f"config path does not exist: {path}")
        paths.append(path.resolve())
    return paths


def _filter_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in params}


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raise McpRunBindingHookError("MCP server args must be a list of strings, not a string")
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise McpRunBindingHookError(f"MCP server args must be a sequence of strings, got {type(value)!r}")


def _as_str_map(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise McpRunBindingHookError(f"MCP server env must be a mapping, got {type(value)!r}")
    return {str(key): str(item) for key, item in value.items()}


def _server_snapshot(config: Any, name: str) -> dict[str, Any]:
    """Return preserved ``add_mcp_server`` kwargs for an existing MCP server.

    Fabric now owns ``env`` / ``args`` as top-level MCP server fields (not
    ``extra_fields``). Legacy snapshots that still stash them under
    ``extra_fields`` are lifted to top-level kwargs.
    """
    mcp = getattr(config, "mcp", None)
    servers = getattr(mcp, "servers", None) or {}
    server = servers.get(name) if isinstance(servers, Mapping) else None
    if server is None:
        return {"transport": "stdio", "exposure": "harness_native"}

    transport = str(getattr(server, "transport", None) or "stdio")
    exposure = str(getattr(server, "exposure", None) or "harness_native")

    extra: dict[str, Any] = {}
    extra_fields = getattr(server, "extra_fields", None)
    if isinstance(extra_fields, Mapping):
        extra = dict(extra_fields)
    elif callable(extra_fields):
        extra = dict(extra_fields())
    elif hasattr(server, "model_extra") and isinstance(server.model_extra, Mapping):
        extra = dict(server.model_extra)

    args = _as_str_list(getattr(server, "args", None))
    if not args and "args" in extra:
        args = _as_str_list(extra.pop("args"))

    env = _as_str_map(getattr(server, "env", None))
    if not env and "env" in extra:
        env = _as_str_map(extra.pop("env"))

    snapshot: dict[str, Any] = {"transport": transport, "exposure": exposure}
    if args:
        snapshot["args"] = args
    if env:
        snapshot["env"] = env
    if extra:
        snapshot["extra_fields"] = extra
    return snapshot


def _verify_binding(binding: Any) -> Any:
    verify = getattr(binding, "verify", None)
    if callable(verify):
        return verify()
    verify_once = getattr(binding, "verify_exactly_once", None)
    if callable(verify_once):
        return verify_once()
    raise McpRunBindingHookError("binding has neither verify() nor verify_exactly_once()")


def _audit_mapping(audit: Any) -> dict[str, Any] | None:
    public = getattr(audit, "public_mapping", None)
    if callable(public):
        mapping = public()
        return dict(mapping) if isinstance(mapping, Mapping) else {"value": mapping}
    if isinstance(audit, Mapping):
        return dict(audit)
    return None


def _result_payload(audit: Any) -> Any:
    for attr in ("analysis", "result"):
        value = getattr(audit, attr, None)
        if value is None:
            continue
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            return dump(mode="json")
        return value
    return None


class McpRunBindingHook:
    """Ordered per-task MCP binding lifecycle around ``Fabric.run``."""

    def __init__(
        self,
        bindings: Sequence[Mapping[str, Any]] | None = None,
        *,
        agent_src: str | Path | None = None,
        pythonpath: str | Path | None = None,
        binding_parent: str | Path | None = None,
    ) -> None:
        src = agent_src if agent_src is not None else pythonpath
        if src is not None:
            _prepend_sys_path(src)

        if not bindings:
            raise McpRunBindingHookError("mcp_run_binding requires a non-empty bindings list")

        self._binding_parent = Path(binding_parent).expanduser() if binding_parent else None
        self._entries: list[dict[str, Any]] = []
        for index, raw in enumerate(bindings):
            if not isinstance(raw, Mapping):
                raise McpRunBindingHookError(f"bindings[{index}] must be a mapping")
            server = str(raw.get("server") or "").strip()
            if not server or raw.get("binding") is None:
                raise McpRunBindingHookError(f"bindings[{index}] requires server and binding")

            handoff_raw = raw.get("handoff")
            handoff_env: str | None = None
            handoff_cls: Any | None = None
            if handoff_raw is not None:
                if not isinstance(handoff_raw, Mapping):
                    raise McpRunBindingHookError(f"bindings[{index}].handoff must be a mapping")
                handoff_env = str(handoff_raw.get("env") or "").strip() or None
                handoff_ref = handoff_raw.get("ref")
                if not handoff_env or handoff_ref is None:
                    raise McpRunBindingHookError(f"bindings[{index}].handoff requires env and ref")
                try:
                    handoff_cls = _resolve_target(handoff_ref)
                except Exception as exc:
                    raise McpRunBindingHookError(
                        f"Could not resolve bindings[{index}].handoff.ref={handoff_ref!r}"
                    ) from exc

            binding_raw = raw.get("binding")
            try:
                binding_cls = _resolve_target(binding_raw)
            except Exception as exc:
                raise McpRunBindingHookError(
                    f"Could not resolve bindings[{index}].binding={binding_raw!r}. "
                    "Set agent_src to the agent checkout .../src (path-first; do not install "
                    "the agent into the platform venv)."
                ) from exc

            executable_raw = raw.get("executable")
            executable = Path(executable_raw).expanduser() if executable_raw else None
            if executable is not None and not executable.is_file():
                raise McpRunBindingHookError(f"bindings[{index}].executable does not exist: {executable}")

            config_paths = _as_path_list(raw.get("config_paths") or raw.get("config_path"))

            self._entries.append(
                {
                    "server": server,
                    "binding_cls": binding_cls,
                    "handoff_cls": handoff_cls,
                    "handoff_env": handoff_env,
                    "executable": executable.resolve() if executable is not None else None,
                    "config_paths": config_paths,
                }
            )

    def prepare(self, config: Any, task: Any, evidence_dir: Path, workspace_dir: Path, session: Any) -> Any:
        del workspace_dir
        if not hasattr(config, "add_mcp_server"):
            raise McpRunBindingHookError("Fabric config does not expose add_mcp_server; cannot rebind MCP.")

        prompt = task.agent_prompt()
        parent = self._binding_parent or (evidence_dir / "mcp-bindings")
        parent.mkdir(parents=True, exist_ok=True)

        started: list[dict[str, Any]] = []
        session.state["mcp_bindings"] = started

        try:
            for entry in self._entries:
                handoff = None
                handoff_cls = entry["handoff_cls"]
                handoff_env = entry["handoff_env"]
                if handoff_cls is not None and handoff_env:
                    credential = os.environ.get(handoff_env)
                    if credential:
                        handoff = handoff_cls.start(credential, timeout_seconds=60.0)

                create_kwargs: dict[str, Any] = {
                    "credential_socket": handoff.socket_path if handoff is not None else None,
                    "credential_token": handoff.token if handoff is not None else None,
                }
                if entry["executable"] is not None:
                    create_kwargs["executable"] = entry["executable"]
                config_paths: list[Path] = entry["config_paths"]
                if config_paths:
                    create_kwargs["config_paths"] = config_paths
                    create_kwargs["config_path"] = config_paths[0]

                try:
                    binding = entry["binding_cls"].create(
                        prompt,
                        parent,
                        **_filter_kwargs(entry["binding_cls"].create, create_kwargs),
                    )
                except Exception:
                    if handoff is not None:
                        handoff.close()
                    raise

                # Register before rebinding so prepare failures can still cleanup.
                started.append({"server": entry["server"], "binding": binding, "handoff": handoff})
                preserved = _server_snapshot(config, entry["server"])
                config = config.add_mcp_server(
                    entry["server"],
                    url=str(binding.mcp_command),
                    **preserved,
                )
        except Exception:
            self.cleanup(session)
            raise

        return config

    def after_success(self, task: Any, result: Any, session: Any) -> dict[str, Any] | None:
        del task, result
        started = session.state.get("mcp_bindings") or []
        if not started:
            raise McpRunBindingHookError("mcp bindings missing after Fabric.run")

        mcp_bindings: dict[str, Any] = {}
        first_result: Any = None
        for item in started:
            server = item["server"]
            binding = item["binding"]
            audit = _verify_binding(binding)
            entry_extras: dict[str, Any] = {}
            mapping = _audit_mapping(audit)
            if mapping is not None:
                entry_extras["audit"] = mapping
            payload = _result_payload(audit)
            if payload is not None:
                entry_extras["result"] = payload
                if first_result is None:
                    first_result = payload
            mcp_bindings[server] = entry_extras

        extras: dict[str, Any] = {"mcp_bindings": mcp_bindings}
        # Deprecated alias for one release — FabricAgentRuntime historically read this key.
        if first_result is not None:
            extras["analyzer_analysis"] = first_result
        return extras

    def cleanup(self, session: Any) -> None:
        started: list[dict[str, Any]] = list(session.state.pop("mcp_bindings", []) or [])
        for item in reversed(started):
            binding = item.get("binding")
            handoff = item.get("handoff")
            server = item.get("server")
            try:
                if binding is not None:
                    binding.cleanup()
            except Exception:
                logger.exception("Failed to cleanup MCP binding for %s", server)
            try:
                if handoff is not None:
                    handoff.close()
            except Exception:
                logger.exception("Failed to close MCP handoff for %s", server)
