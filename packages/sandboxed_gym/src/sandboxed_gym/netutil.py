# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Port binding and node-IP helpers (Ray-free)."""

from __future__ import annotations

import random
import socket

DEFAULT_BROKER_PORT_RANGE_LOW = 5000
DEFAULT_BROKER_PORT_RANGE_HIGH = 5999


def get_node_ip() -> str:
    """Best-effort routable IP of this host (not loopback)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def bind_socket_in_range(
    sock: socket.socket,
    port_range_low: int,
    port_range_high: int,
    max_retries: int = 50,
) -> int:
    """Bind ``sock`` to a random free port in ``[low, high)``."""
    for _ in range(max_retries):
        port = random.randint(port_range_low, port_range_high - 1)
        try:
            sock.bind(("", port))
            return port
        except OSError:
            continue
    raise RuntimeError(
        f"Could not find a free port in range [{port_range_low}, {port_range_high}) after {max_retries} attempts."
    )
