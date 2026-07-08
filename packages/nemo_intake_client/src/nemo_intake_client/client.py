# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed sync and async clients for the supported Intake operations."""

from nemo_intake_client import endpoints
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method


class _IntakeMethods:
    create_atif = method(endpoints.create_atif)
    create_evaluator_result = method(endpoints.create_evaluator_result)
    list_traces = method(endpoints.list_traces)
    list_span_evaluator_results = method(endpoints.list_span_evaluator_results)
    create_experiment_group = method(endpoints.create_experiment_group)
    get_experiment_group = method(endpoints.get_experiment_group)
    create_experiment = method(endpoints.create_experiment)
    get_experiment = method(endpoints.get_experiment)


class IntakeClient(_IntakeMethods, NemoClient):
    """Synchronous client for Evaluator's supported Intake workflow."""


class AsyncIntakeClient(_IntakeMethods, AsyncNemoClient):
    """Asynchronous client for Evaluator's supported Intake workflow."""
