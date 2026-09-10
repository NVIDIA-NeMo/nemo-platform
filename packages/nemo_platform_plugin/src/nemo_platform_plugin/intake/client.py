# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the Intake APIs."""

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.intake import endpoints


class _IntakeMethods:
    # Ingest
    create_atif = method(endpoints.create_atif)
    create_otlp_traces = method(endpoints.create_otlp_traces)
    create_chat_completion = method(endpoints.create_chat_completion)
    create_spans = method(endpoints.create_spans)
    # Traces
    list_traces = method(endpoints.list_traces)
    get_trace = method(endpoints.get_trace)
    get_trace_metrics = method(endpoints.get_trace_metrics)
    # Spans
    list_spans = method(endpoints.list_spans)
    list_span_groups = method(endpoints.list_span_groups)
    get_span = method(endpoints.get_span)
    # Sessions
    get_session = method(endpoints.get_session)
    # Annotations
    create_annotation = method(endpoints.create_annotation)
    list_annotations = method(endpoints.list_annotations)
    get_annotation = method(endpoints.get_annotation)
    delete_annotation = method(endpoints.delete_annotation)
    # Evaluator results
    create_evaluator_result = method(endpoints.create_evaluator_result)
    list_evaluator_results = method(endpoints.list_evaluator_results)
    get_evaluator_result = method(endpoints.get_evaluator_result)
    list_evaluator_results_for_span = method(endpoints.list_evaluator_results_for_span)
    # Evaluations
    get_evaluation = method(endpoints.get_evaluation)
    patch_evaluation = method(endpoints.patch_evaluation)
    # Experiments
    create_experiment = method(endpoints.create_experiment)
    list_experiments = method(endpoints.list_experiments)
    get_experiment = method(endpoints.get_experiment)
    update_experiment = method(endpoints.update_experiment)
    delete_experiment = method(endpoints.delete_experiment)


class IntakeClient(_IntakeMethods, NemoClient):
    """Sync client for the Intake API."""


class AsyncIntakeClient(_IntakeMethods, AsyncNemoClient):
    """Async client for the Intake API."""
