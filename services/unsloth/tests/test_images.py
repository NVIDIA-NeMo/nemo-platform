# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import nemo_platform_plugin.jobs.image as platform_image
import nmp.unsloth.images as unsloth_images
import pytest
from nmp.unsloth.config import UnslothConfig
from nmp.unsloth.images import (
    TASKS_IMAGE_NAME,
    TRAINING_IMAGE_NAME,
    get_tasks_image,
    get_training_image,
    get_unsloth_qualified_image,
)


@pytest.fixture
def platform_config(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    config = SimpleNamespace(image_registry="registry.example.com/nemo", image_tag="test-tag")
    monkeypatch.setattr(unsloth_images, "get_platform_config", lambda: config)
    monkeypatch.setattr(platform_image, "get_platform_config", lambda: config)
    return config


def test_default_unsloth_images_use_platform_registry(monkeypatch, platform_config):
    monkeypatch.setattr(unsloth_images, "config", UnslothConfig())

    training = get_training_image()
    tasks = get_tasks_image()

    expected_training = f"{platform_config.image_registry}/{TRAINING_IMAGE_NAME}:{platform_config.image_tag}"
    assert training == expected_training
    assert tasks == expected_training  # tasks falls back to training when tasks_image is unset
    assert TASKS_IMAGE_NAME.count("/") == 0  # single repo segment, no nested paths


def test_unsloth_image_registry_override(monkeypatch, platform_config):
    monkeypatch.setattr(
        unsloth_images,
        "config",
        UnslothConfig(image_registry="my-registry/other-registry"),
    )

    assert (
        get_unsloth_qualified_image(TRAINING_IMAGE_NAME)
        == f"my-registry/other-registry/{TRAINING_IMAGE_NAME}:{platform_config.image_tag}"
    )


def test_unsloth_full_image_override(monkeypatch, platform_config):
    monkeypatch.setattr(
        unsloth_images,
        "config",
        UnslothConfig(
            tasks_image="my-registry/nemo-platform-dev/nmp-unsloth-tasks:dev",
        ),
    )

    assert get_tasks_image() == "my-registry/nemo-platform-dev/nmp-unsloth-tasks:dev"
