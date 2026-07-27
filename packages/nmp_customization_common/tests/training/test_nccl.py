# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

import pytest
from nmp.customization_common.training import nccl as nccl_mod
from nmp.customization_common.training.nccl import maybe_set_nccl_ib_hca


def _make_hca(ib_root: Path, name: str, with_netdev: bool = False) -> None:
    device = ib_root / name / "device"
    net = device / "net"
    net.mkdir(parents=True)
    if with_netdev:
        (net / "eth0").mkdir()


@pytest.fixture
def ib_sysfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ib = tmp_path / "infiniband"
    ib.mkdir()
    monkeypatch.setattr(nccl_mod, "_IB_SYSFS", ib)
    monkeypatch.delenv("NCCL_IB_HCA", raising=False)
    return ib


def test_sets_nccl_ib_hca_when_phantoms_exist(ib_sysfs: Path) -> None:
    _make_hca(ib_sysfs, "mlx5_0", with_netdev=True)
    _make_hca(ib_sysfs, "mlx5_1", with_netdev=False)

    maybe_set_nccl_ib_hca()
    assert os.environ["NCCL_IB_HCA"] == "mlx5_0"


def test_noop_without_phantoms(ib_sysfs: Path) -> None:
    _make_hca(ib_sysfs, "mlx5_0", with_netdev=True)

    maybe_set_nccl_ib_hca()
    assert "NCCL_IB_HCA" not in os.environ


def test_noop_without_ib(ib_sysfs: Path) -> None:
    ib_sysfs.rmdir()

    maybe_set_nccl_ib_hca()
    assert "NCCL_IB_HCA" not in os.environ


def test_respects_existing_value(ib_sysfs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_hca(ib_sysfs, "mlx5_0", with_netdev=True)
    _make_hca(ib_sysfs, "mlx5_1", with_netdev=False)
    monkeypatch.setenv("NCCL_IB_HCA", "mlx5_custom")

    maybe_set_nccl_ib_hca()
    assert os.environ["NCCL_IB_HCA"] == "mlx5_custom"
