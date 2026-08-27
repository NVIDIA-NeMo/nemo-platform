# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed HTTP clients for the Evaluator service.

Wraps the endpoint functions from ``evaluator.endpoints`` as direct methods
using the ``method()`` descriptor, following the files/models pattern.

The evaluator's high-level ``submit()`` convenience method (overloaded for row
vs. taskset evaluation) stays in the SDK layer — it packages parameters into a
job spec and calls ``submit_evaluate_job`` / ``submit_agent_eval_job`` here.
"""

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method
from nemo_platform_plugin.evaluator import endpoints


class _EvaluatorMethods:
    submit_evaluate_job = method(endpoints.submit_evaluate_job)
    submit_agent_eval_job = method(endpoints.submit_agent_eval_job)
    get_eval_result = method(endpoints.get_eval_result)
    list_eval_results = method(endpoints.list_eval_results)
    get_agent_eval_result = method(endpoints.get_agent_eval_result)
    list_agent_eval_results = method(endpoints.list_agent_eval_results)
    delete_agent_eval_result = method(endpoints.delete_agent_eval_result)
    get_metric = method(endpoints.get_metric)
    list_metrics = method(endpoints.list_metrics)
    create_metric = method(endpoints.create_metric)
    delete_metric = method(endpoints.delete_metric)


class EvaluatorClient(_EvaluatorMethods, NemoClient):
    """Sync client for the Evaluator service API."""


class AsyncEvaluatorClient(_EvaluatorMethods, AsyncNemoClient):
    """Async client for the Evaluator service API."""
