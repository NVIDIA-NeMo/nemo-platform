# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared client constants and env checks."""

import os

WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR = "NMP_WORKLOAD_IDENTITY_TOKEN_FILE"


def is_workload_identity_token_file_set() -> bool:
    return bool(os.environ.get(WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR))
