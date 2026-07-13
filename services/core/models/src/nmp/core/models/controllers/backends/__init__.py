# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backends package for Models Controller service."""

from .backends import ServiceBackend as ServiceBackend
from .docker import DockerServiceBackend as DockerServiceBackend
from .k8s_nim_operator import K8sNimOperatorServiceBackend as K8sNimOperatorServiceBackend
from .registry import BackendRegistry as BackendRegistry
