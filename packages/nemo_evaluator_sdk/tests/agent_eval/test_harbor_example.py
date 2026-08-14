# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from packages.nemo_evaluator_sdk.examples.harbor.run_harbor_example import (
    HELLO_WORLD_TASK_NAME,
    INJECTED_ERROR_TASK_NAME,
    _task_names,
)


def test_task_names_default_to_healthy_hello_world_only():
    assert _task_names(inject_error_task=False) == [HELLO_WORLD_TASK_NAME]


def test_task_names_include_permanent_error_task_when_requested():
    assert _task_names(inject_error_task=True) == [HELLO_WORLD_TASK_NAME, INJECTED_ERROR_TASK_NAME]
