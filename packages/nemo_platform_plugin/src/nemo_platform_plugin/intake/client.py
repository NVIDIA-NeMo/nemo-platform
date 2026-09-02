# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the Intake APIs used by evaluator."""

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.intake import endpoints


class _IntakeMethods:
    create_atif = method(endpoints.create_atif)
    create_otlp_traces = method(endpoints.create_otlp_traces)
    list_traces = method(endpoints.list_traces)
    create_evaluator_result = method(endpoints.create_evaluator_result)
    get_evaluation = method(endpoints.get_evaluation)
    patch_evaluation = method(endpoints.patch_evaluation)
    list_evaluator_results = method(endpoints.list_evaluator_results)
    list_evaluator_results_for_span = method(endpoints.list_evaluator_results_for_span)


class IntakeClient(_IntakeMethods, NemoClient):
    """Sync client for the Intake API subset evaluator uses."""


class AsyncIntakeClient(_IntakeMethods, AsyncNemoClient):
    """Async client for the Intake API subset evaluator uses."""
