# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared constants for the unsloth service.

These mirror the ``services/automodel`` constants so the unsloth service
exposes the same path layout to a future container submit pipeline (and to
the plugin's local ``run`` orchestration today).
"""

from nmp.common.jobs.constants import DEFAULT_JOB_STORAGE_PATH

SERVICE_NAME = "unsloth"

# Subdirectory names under the job's persistent storage root.
DEFAULT_MODEL_OUTPUT_DIR_NAME = "model"
DEFAULT_DATASET_OUTPUT_DIR_NAME = "dataset"
DEFAULT_OUTPUT_MODEL_DIR_NAME = "output_model"

# Absolute paths used by the compiler when wiring step-to-step file sharing.
# The plugin's local ``run`` re-derives equivalents under
# ``ctx.storage.persistent`` so it does not depend on these values.
DEFAULT_MODEL_PATH = f"{DEFAULT_JOB_STORAGE_PATH}/{DEFAULT_MODEL_OUTPUT_DIR_NAME}"
DEFAULT_DATASET_PATH = f"{DEFAULT_JOB_STORAGE_PATH}/{DEFAULT_DATASET_OUTPUT_DIR_NAME}"
DEFAULT_OUTPUT_MODEL_PATH = f"{DEFAULT_JOB_STORAGE_PATH}/{DEFAULT_OUTPUT_MODEL_DIR_NAME}"

NMP_JOBS_URL_ENVVAR = "NMP_JOBS_URL"
NMP_FILES_URL_ENVVAR = "NMP_FILES_URL"
