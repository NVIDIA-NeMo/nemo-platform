# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke_gpu_tasks: Import smoke tests for the nmp-gpu-tasks image")
    config.addinivalue_line(
        "markers", "smoke_nmp_customizer_tasks: Import smoke tests for the nmp-customizer-tasks image"
    )
    config.addinivalue_line(
        "markers", "smoke_nmp_automodel_training: Import smoke tests for the nmp/automodel-training image"
    )
