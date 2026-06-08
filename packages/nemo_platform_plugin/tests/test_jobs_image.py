# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace

import nemo_platform_plugin.jobs.image as image
import pytest
from nemo_platform_plugin.jobs.image import get_qualified_image, image_builder


@pytest.fixture
def platform_config(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SimpleNamespace(image_registry="registry.example.com/nemo", image_tag="test-tag")
    monkeypatch.setattr(image, "get_platform_config", lambda: config)


def test_get_qualified_image_uses_platform_config(platform_config: None) -> None:
    assert get_qualified_image("nmp-cpu-tasks") == "registry.example.com/nemo/nmp-cpu-tasks:test-tag"


def test_get_qualified_image_accepts_overrides(platform_config: None) -> None:
    assert (
        get_qualified_image("nmp-cpu-tasks", registry="nvcr.io/example", tag="25.10")
        == "nvcr.io/example/nmp-cpu-tasks:25.10"
    )


def test_image_builder_uses_platform_config_once(platform_config: None) -> None:
    build_image = image_builder()

    assert build_image("nmp-api") == "registry.example.com/nemo/nmp-api:test-tag"
