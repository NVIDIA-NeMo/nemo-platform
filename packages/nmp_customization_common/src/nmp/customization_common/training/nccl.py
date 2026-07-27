# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NCCL environment helpers shared by customization training backends."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_IB_SYSFS = Path("/sys/class/infiniband")


def maybe_set_nccl_ib_hca() -> None:
    """Set NCCL_IB_HCA to usable Mellanox HCAs when phantom devices are present.

    Some hosts expose mlx InfiniBand devices in sysfs that have no netdev. NCCL
    will try those and fail; filter them out when that happens.
    """
    if os.environ.get("NCCL_IB_HCA") or not _IB_SYSFS.is_dir():
        return

    usable: list[str] = []
    phantom: list[str] = []
    try:
        hcas = sorted(p for p in _IB_SYSFS.iterdir() if p.is_dir())
    except OSError:
        return

    for hca in hcas:
        if not hca.name.startswith("mlx"):
            continue
        try:
            has_netdev = any((hca / "device" / "net").iterdir())
        except OSError:
            has_netdev = False
        (usable if has_netdev else phantom).append(hca.name)

    if not usable or not phantom:
        return

    os.environ["NCCL_IB_HCA"] = ",".join(usable)
    logger.info("Setting NCCL_IB_HCA=%s (excluded phantom HCAs: %s)", os.environ["NCCL_IB_HCA"], ",".join(phantom))
