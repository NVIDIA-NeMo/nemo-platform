# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nmp.automodel.config import AutomodelConfig
from nmp.automodel.images import (
    DEFAULT_AUTOMODEL_IMAGE_REGISTRY,
    TASKS_IMAGE_NAME,
    TRAINING_IMAGE_NAME,
    get_automodel_qualified_image,
    get_tasks_image,
    get_training_image,
)


def test_default_automodel_images_use_nvcr_dev_registry(monkeypatch):
    monkeypatch.setattr("nmp.automodel.images.config", AutomodelConfig())

    tasks = get_tasks_image()
    training = get_training_image()

    assert tasks == f"{DEFAULT_AUTOMODEL_IMAGE_REGISTRY}/{TASKS_IMAGE_NAME}:local"
    assert training == f"{DEFAULT_AUTOMODEL_IMAGE_REGISTRY}/{TRAINING_IMAGE_NAME}:local"
    assert TASKS_IMAGE_NAME.count("/") == 0  # NVCR: single repo segment, no nested paths


def test_automodel_image_registry_override(monkeypatch):
    monkeypatch.setattr(
        "nmp.automodel.images.config",
        AutomodelConfig(image_registry="nvcr.io/0921617854601259/other-registry"),
    )

    assert (
        get_automodel_qualified_image(TASKS_IMAGE_NAME)
        == "nvcr.io/0921617854601259/other-registry/nmp-automodel-tasks:local"
    )


def test_automodel_full_image_override(monkeypatch):
    monkeypatch.setattr(
        "nmp.automodel.images.config",
        AutomodelConfig(
            tasks_image="nvcr.io/0921617854601259/nemo-platform-dev/nmp-automodel-tasks:dev",
        ),
    )

    assert get_tasks_image() == "nvcr.io/0921617854601259/nemo-platform-dev/nmp-automodel-tasks:dev"
