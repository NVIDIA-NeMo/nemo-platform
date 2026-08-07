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
    DEFAULT_ENVIRONMENT_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_MODEL_PATH,
    DEFAULT_VALIDATION_DATASET_PATH,
    NMP_FILES_URL_ENVVAR,
    NMP_JOBS_URL_ENVVAR,
    SANDBOX_DATASET_PATH,
    SANDBOX_ENVIRONMENT_PATH,
    SANDBOX_WORK_PATH,
)

__all__ = [
    "BASE_LOG_DIR_ENVVAR",
    "DEFAULT_DATASET_PATH",
    "DEFAULT_ENVIRONMENT_PATH",
    "DEFAULT_MODEL_PATH",
    "DEFAULT_OUTPUT_MODEL_PATH",
    "DEFAULT_SEED",
    "DEFAULT_TRAINING_OUTPUT_PATH",
    "DEFAULT_TRAINING_RESULT_FILE_NAME",
    "DEFAULT_VALIDATION_DATASET_PATH",
    "NMP_BROKER_HOST_ENVVAR",
    "NMP_BROKER_PORT_ENVVAR",
    "NMP_FILES_URL_ENVVAR",
    "NMP_JOBS_URL_ENVVAR",
    "NMP_VLLM_HOST_ENVVAR",
    "NMP_VLLM_PORT_ENVVAR",
    "SANDBOX_DATASET_PATH",
    "SANDBOX_ENVIRONMENT_PATH",
    "SANDBOX_WORK_PATH",
    "SERVICE_NAME",
]

SERVICE_NAME = "rl"

DEFAULT_SEED = 42

# Env vars the compiler injects so the training master can build sandbox egress allowlists.
NMP_VLLM_HOST_ENVVAR = "NMP_VLLM_SERVICE_HOST"
NMP_VLLM_PORT_ENVVAR = "NMP_VLLM_SERVICE_PORT"
NMP_BROKER_HOST_ENVVAR = "NMP_BROKER_SERVICE_HOST"
NMP_BROKER_PORT_ENVVAR = "NMP_BROKER_SERVICE_PORT"

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
