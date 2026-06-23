# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Thread-safe GPU pool for Docker deployments (plugin-local; not shared with models).

During the 759 cutover both pools may coexist briefly — consolidate into
nemo_platform_plugin when models docker backend is removed.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class GPUAllocationError(Exception):
    """Raised when GPU allocation fails due to insufficient resources."""


@dataclass
class GPUPoolStatus:
    total: int
    available: int
    allocated: int
    allocations: dict[str, list[int]] = field(default_factory=dict)
    gpu_state: dict[int, str | None] = field(default_factory=dict)


class DockerGPUPool:
    """Thread-safe pool of GPU device IDs for Docker device_requests."""

    def __init__(self, reserved_gpu_device_ids: list[int]) -> None:
        self.num_reserved_gpus = len(reserved_gpu_device_ids)
        self.gpu_to_workload_id: dict[int, str | None] = {gpu_id: None for gpu_id in reserved_gpu_device_ids}
        self._mutex = threading.Lock()

    def allocate_gpu(self, workload_id: str, num_requested: int = 1) -> list[int]:
        with self._mutex:
            if num_requested <= 0:
                raise GPUAllocationError(f"Invalid GPU request: {num_requested}. Must be a positive integer.")
            available_gpus = {gpu for gpu, workload in self.gpu_to_workload_id.items() if workload is None}
            if len(available_gpus) < num_requested:
                raise GPUAllocationError(
                    f"Not enough GPUs available. Requested {num_requested}, "
                    f"available {len(available_gpus)} out of {self.num_reserved_gpus} total."
                )
            gpu_ids: list[int] = []
            for _ in range(num_requested):
                gpu_id = available_gpus.pop()
                gpu_ids.append(gpu_id)
                self.gpu_to_workload_id[gpu_id] = workload_id
            logger.info("DockerGPUPool: allocated gpu_ids %s to workload %s", gpu_ids, workload_id)
            return gpu_ids

    def release_gpu(self, workload_id: str) -> list[int]:
        with self._mutex:
            gpu_ids = [gpu for gpu, workload in self.gpu_to_workload_id.items() if workload == workload_id]
            if gpu_ids:
                logger.info("DockerGPUPool: releasing gpu_ids %s from workload %s", gpu_ids, workload_id)
            for gpu_id in gpu_ids:
                self.gpu_to_workload_id[gpu_id] = None
            return gpu_ids


_pool: DockerGPUPool | None = None
_pool_lock = threading.Lock()


def detect_gpu_device_ids() -> list[int]:
    """Return GPU indices from nvidia-smi when available."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return []
    ids: list[int] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            ids.append(int(stripped))
    return ids


def get_shared_gpu_pool() -> DockerGPUPool | None:
    """Lazy singleton GPU pool shared across docker executor instances in this process."""
    global _pool
    with _pool_lock:
        if _pool is None:
            device_ids = detect_gpu_device_ids()
            if not device_ids:
                return None
            _pool = DockerGPUPool(reserved_gpu_device_ids=device_ids)
        return _pool
