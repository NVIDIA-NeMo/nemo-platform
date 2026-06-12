# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OPA WASM Policy Engine using wasmtime."""

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from wasmtime import Config, Engine, Func, FuncType, Instance, Limits, Memory, MemoryType, Module, Store, ValType

logger = logging.getLogger(__name__)

# Entrypoint IDs (order of -e flags in: opa build -e authz/allow -e authz/has_permissions -e authz/has_role)
ENTRYPOINT_MAP = {"allow": 0, "has_permissions": 1, "has_role": 2}

DATA_LOADING_FUEL = 10_000_000_000


class PolicyEngineError(Exception):
    """Error during policy evaluation."""


class OPAPolicy:
    """Wrapper for OPA WASM policy evaluation."""

    def __init__(self, wasm_path: str, *, fuel_limit: int = 200_000_000, memory_limit_mb: int = 32):
        config = Config()
        config.consume_fuel = True
        engine = Engine(config)

        self.fuel_limit = fuel_limit
        self.store = Store(engine)
        self.store.set_fuel(DATA_LOADING_FUEL)
        self.store.set_limits(memory_size=memory_limit_mb * 1024 * 1024)
        module = Module.from_file(engine, wasm_path)

        # OPA requires these imports (in order they appear in the module)
        # env::opa_builtin0..4, env::opa_abort, env::memory
        self.memory = Memory(self.store, MemoryType(Limits(16, memory_limit_mb * 16)))

        imports = [
            Func(self.store, FuncType([ValType.i32(), ValType.i32()], [ValType.i32()]), lambda a, b: 0),  # builtin0
            Func(
                self.store, FuncType([ValType.i32(), ValType.i32(), ValType.i32()], [ValType.i32()]), lambda a, b, c: 0
            ),  # builtin1
            Func(
                self.store,
                FuncType([ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32()], [ValType.i32()]),
                lambda a, b, c, d: 0,
            ),  # builtin2
            Func(
                self.store,
                FuncType([ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32()], [ValType.i32()]),
                lambda a, b, c, d, e: 0,
            ),  # builtin3
            Func(
                self.store,
                FuncType(
                    [ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32()],
                    [ValType.i32()],
                ),
                lambda a, b, c, d, e, f: 0,
            ),  # builtin4
            Func(self.store, FuncType([ValType.i32()], []), lambda addr: None),  # opa_abort
            self.memory,
        ]

        self.instance = Instance(self.store, module, imports)
        self.exports = self.instance.exports(self.store)
        self._base_heap = self._export_func("opa_heap_ptr_get")(self.store)
        self._data_heap = self._base_heap
        self._data_addr: Optional[int] = None
        self._lock = threading.Lock()

    def _export_func(self, name: str) -> Func:
        return cast(Func, self.exports[name])

    def _write_json(self, data: Any) -> int:
        """Write JSON to WASM memory, return OPA value address."""
        json_bytes = json.dumps(data).encode("utf-8")
        addr = self._export_func("opa_malloc")(self.store, len(json_bytes))
        self.memory.write(self.store, json_bytes, addr)
        return self._export_func("opa_json_parse")(self.store, addr, len(json_bytes))

    def _read_json(self, addr: int) -> Any:
        """Read OPA value as JSON from WASM memory."""
        json_addr = self._export_func("opa_json_dump")(self.store, addr)
        mem = self.memory.data_ptr(self.store)
        end = json_addr
        while mem[end] != 0:
            end += 1
        return json.loads(bytes(mem[json_addr:end]).decode("utf-8"))

    def set_data(self, data: Dict[str, Any]) -> None:
        """Set the base data document."""
        with self._lock:
            self.store.set_fuel(DATA_LOADING_FUEL)
            self._export_func("opa_heap_ptr_set")(self.store, self._base_heap)
            self._data_addr = self._write_json(data)
            self._data_heap = self._export_func("opa_heap_ptr_get")(self.store)

    def evaluate(self, input_data: Dict[str, Any], entrypoint: int = 0) -> Any:
        """Evaluate policy with given input."""
        if self._data_addr is None:
            raise PolicyEngineError("Policy data not loaded — refusing to evaluate (fail-closed)")

        with self._lock:
            self.store.set_fuel(self.fuel_limit)

            heap_base = getattr(self, "_data_heap", self._base_heap)
            self._export_func("opa_heap_ptr_set")(self.store, heap_base)

            ctx = self._export_func("opa_eval_ctx_new")(self.store)
            self._export_func("opa_eval_ctx_set_input")(self.store, ctx, self._write_json(input_data))
            self._export_func("opa_eval_ctx_set_data")(self.store, ctx, self._data_addr)
            self._export_func("opa_eval_ctx_set_entrypoint")(self.store, ctx, entrypoint)

            self._export_func("eval")(self.store, ctx)
            return self._read_json(self._export_func("opa_eval_ctx_get_result")(self.store, ctx))


# Module-level singleton
_policy: Optional[OPAPolicy] = None
_policy_lock = threading.Lock()
_policy_data: Dict[str, Any] = {}


def get_policy() -> OPAPolicy:
    """Get or create the singleton policy instance (thread-safe, double-checked locking)."""
    global _policy
    if _policy is None:
        with _policy_lock:
            if _policy is None:
                path = Path(__file__).parent.parent.parent / "assets" / "policy.wasm"
                if not path.exists():
                    raise PolicyEngineError(f"policy.wasm not found at {path}. Run 'make build-policy'.")

                from nmp.common.config import get_service_config
                from nmp.core.auth.config import AuthServiceConfig

                cfg = get_service_config(AuthServiceConfig)
                _policy = OPAPolicy(
                    str(path),
                    fuel_limit=cfg.embedded_pdp_cpu_limit * 1_000_000,
                    memory_limit_mb=cfg.embedded_pdp_memory_limit_mb,
                )
                if _policy_data:
                    _policy.set_data(_policy_data)
    return _policy


def set_policy_data(data: Dict[str, Any]) -> None:
    """Set policy data (principals, roles, etc.)."""
    global _policy_data
    with _policy_lock:
        _policy_data = data
        if _policy is not None:
            _policy.set_data(data)


def reload_policy() -> None:
    """Force reload the policy."""
    global _policy
    with _policy_lock:
        _policy = None
    get_policy()


def evaluate(entrypoint: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a policy entrypoint."""
    if entrypoint not in ENTRYPOINT_MAP:
        raise PolicyEngineError(f"Invalid entrypoint: {entrypoint}. Valid: {list(ENTRYPOINT_MAP.keys())}")

    try:
        result = get_policy().evaluate(input_data, ENTRYPOINT_MAP[entrypoint])
    except Exception as exc:
        msg = str(exc)
        if "all fuel consumed" in msg:
            raise PolicyEngineError(f"Policy evaluation exceeded fuel limit for entrypoint '{entrypoint}'") from exc
        if "memory" in msg.lower():
            raise PolicyEngineError(f"Policy evaluation exceeded memory limit for entrypoint '{entrypoint}'") from exc
        raise PolicyEngineError(f"WASM execution error: {msg}") from exc

    # OPA returns [[{result: ...}]] - unwrap it
    if isinstance(result, list) and result:
        result = result[0]
    if isinstance(result, dict) and "result" in result:
        result = result["result"]

    if not result:
        return {
            "allow": {"allowed": False, "headers": {"X-NMP-Authorized": "false"}},
            "has_permissions": {"allowed": False},
            "has_role": {"has_role": False},
        }.get(entrypoint, {})

    return result


def validate_entrypoint(entrypoint: str) -> bool:
    return entrypoint in ENTRYPOINT_MAP


def get_valid_entrypoints() -> List[str]:
    return list(ENTRYPOINT_MAP.keys())
