# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared job environment constants for customization container tasks."""

from nmp.common.jobs.constants import DEFAULT_JOB_STORAGE_PATH

NMP_JOBS_URL_ENVVAR = "NMP_JOBS_URL"
NMP_FILES_URL_ENVVAR = "NMP_FILES_URL"

__all__ = [
    "DEFAULT_JOB_STORAGE_PATH",
    "NMP_FILES_URL_ENVVAR",
    "NMP_JOBS_URL_ENVVAR",
]
