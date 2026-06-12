# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LoRA adapter sidecar image and launch contract for model deployments."""

from nemo_platform_plugin.jobs.image import get_qualified_image

# Reuse the automodel tasks image (nmp-models + nemo-platform-sdk) instead of nmp-api.
ADAPTER_SIDECAR_IMAGE_NAME = "nmp-automodel-tasks"

# nmp-automodel-tasks ENTRYPOINT is python; invoke the adapters controller directly.
ADAPTER_SIDECAR_PYTHON = "/opt/venv/bin/python"
ADAPTER_SIDECAR_MODULE = "nmp.core.models.sidecars.adapters.main"

ADAPTER_SIDECAR_DOCKER_ENTRYPOINT = [ADAPTER_SIDECAR_PYTHON]
ADAPTER_SIDECAR_DOCKER_COMMAND = ["-m", ADAPTER_SIDECAR_MODULE]

# K8s container.command overrides the image entrypoint — pass the full argv.
ADAPTER_SIDECAR_K8S_COMMAND = [ADAPTER_SIDECAR_PYTHON, "-m", ADAPTER_SIDECAR_MODULE]


def get_adapter_sidecar_image() -> str:
    """Return the qualified Docker image ref for the LoRA adapter sidecar."""
    return get_qualified_image(ADAPTER_SIDECAR_IMAGE_NAME)
