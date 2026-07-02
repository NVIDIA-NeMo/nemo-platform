# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Constants for the nmp-rl container job pipeline.

Shared container-path/env constants come from
:mod:`nmp.customization_common.service.constants`; this module only adds the
nmp-rl ``SERVICE_NAME``, the training-output/workspace paths the runner uses,
and the ``BASE_LOG_DIR`` env name the Ray bootstrap reads for cross-node
coordination.
"""

from nmp.customization_common.service.constants import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_MODEL_PATH,
    DEFAULT_VALIDATION_DATASET_PATH,
    NMP_FILES_URL_ENVVAR,
    NMP_JOBS_URL_ENVVAR,
)

__all__ = [
    "BASE_LOG_DIR_ENVVAR",
    "DEFAULT_DATASET_PATH",
    "DEFAULT_MODEL_PATH",
    "DEFAULT_OUTPUT_MODEL_PATH",
    "DEFAULT_SEED",
    "DEFAULT_TRAINING_OUTPUT_PATH",
    "DEFAULT_TRAINING_RESULT_FILE_NAME",
    "DEFAULT_VALIDATION_DATASET_PATH",
    "NMP_FILES_URL_ENVVAR",
    "NMP_JOBS_URL_ENVVAR",
    "SERVICE_NAME",
]

SERVICE_NAME = "rl"

DEFAULT_SEED = 42

# File name the training runner writes the serialized TrainingResult to under
# the workspace path; downstream steps read it back.
DEFAULT_TRAINING_RESULT_FILE_NAME = "rl_training_result.json"

# Workspace scratch dir the runner writes the compiled YAML, checkpoints, and
# training_result.json into. Single-node uses local scratch; multi-node points
# BASE_LOG_DIR at shared storage (see RlConfig.multinode_shared_storage_path).
DEFAULT_TRAINING_OUTPUT_PATH = "/var/run/scratch/job/training"

# Env var the Ray bootstrap reads to locate the shared dir for the ENDED marker
# and barrier files across nodes.
BASE_LOG_DIR_ENVVAR = "BASE_LOG_DIR"
