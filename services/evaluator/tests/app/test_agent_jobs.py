# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Agent integration with metric and benchmark online jobs.

Covers:
- MetricOnlineJob accepts model or agent (mutually exclusive)
- MetricOnlineAgentJob accepts agent only (dedicated agent job type)
- BenchmarkOnlineJob accepts model or agent (mutually exclusive)
- BenchmarkOnlineAgentJob accepts agent only (dedicated agent job type)
- Discriminator routing to the correct job type
"""

import pytest
from nemo_evaluator_sdk.enums import AgentFormat
from nmp.evaluator.app.values import (
    BenchmarkJobAdapter,
    BenchmarkOfflineJob,
    BenchmarkOnlineAgentJob,
    BenchmarkOnlineJob,
    MetricJobAdapter,
    MetricOfflineJob,
    MetricOnlineAgentJob,
    MetricOnlineJob,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers: minimal valid dicts for reuse
# ---------------------------------------------------------------------------

_GENERIC_AGENT = {
    "url": "http://agent.test/invoke",
    "name": "test-agent",
    "format": "generic",
    "body": {"query": "{{ prompt }}"},
    "response_path": "$.result",
}

_NAT_AGENT = {
    "url": "http://nat.test",
    "name": "nat-agent",
    "format": "nemo_agent_toolkit",
}

_MODEL = {"url": "http://nim.test/v1", "name": "my/model"}

_METRIC = {"type": "exact-match", "reference": "{{item.ref}}", "candidate": "{{item.pred}}"}

_DATASET = {"path": "ds", "storage": {"type": "huggingface", "repo_id": "test/ds"}}

_PROMPT = "Question: {{input}}\nAnswer: "


# ============================================================================
# MetricOnlineJob (model or agent, mutually exclusive)
# ============================================================================


class TestMetricOnlineJob:
    def test_accepts_model(self):
        job = MetricOnlineJob.model_validate(
            {"metric": _METRIC, "model": _MODEL, "dataset": _DATASET, "prompt_template": _PROMPT}
        )
        assert job.model is not None

    def test_rejects_agent(self):
        with pytest.raises(ValidationError):
            MetricOnlineJob.model_validate(
                {"metric": _METRIC, "agent": _NAT_AGENT, "dataset": _DATASET, "prompt_template": _PROMPT}
            )

    def test_rejects_both_model_and_agent(self):
        with pytest.raises(ValidationError):
            MetricOnlineJob.model_validate(
                {
                    "metric": _METRIC,
                    "model": _MODEL,
                    "agent": _NAT_AGENT,
                    "dataset": _DATASET,
                    "prompt_template": _PROMPT,
                }
            )

    def test_rejects_missing_model(self):
        with pytest.raises(ValidationError, match="model"):
            MetricOnlineJob.model_validate({"metric": _METRIC, "dataset": _DATASET, "prompt_template": _PROMPT})

    def test_rejects_empty_optional_field(self):
        with pytest.raises(ValidationError):
            MetricOnlineJob.model_validate(
                {
                    "metric": _METRIC,
                    "model": _MODEL,
                    "dataset": _DATASET,
                    "prompt_template": _PROMPT,
                    "optional_fields": [""],
                }
            )


# ============================================================================
# MetricOnlineAgentJob (dedicated agent-only type)
# ============================================================================


class TestMetricOnlineAgentJob:
    def test_accepts_generic_agent(self):
        job = MetricOnlineAgentJob.model_validate(
            {"metric": _METRIC, "agent": _GENERIC_AGENT, "dataset": _DATASET, "prompt_template": _PROMPT}
        )
        assert job.agent is not None
        assert job.agent.format == AgentFormat.GENERIC

    def test_accepts_nat_agent(self):
        job = MetricOnlineAgentJob.model_validate(
            {"metric": _METRIC, "agent": _NAT_AGENT, "dataset": _DATASET, "prompt_template": _PROMPT}
        )
        assert job.agent is not None
        assert job.agent.format == AgentFormat.NEMO_AGENT_TOOLKIT

    def test_rejects_model_field(self):
        """MetricOnlineAgentJob does not accept a model field."""
        with pytest.raises(ValidationError):
            MetricOnlineAgentJob.model_validate(
                {"metric": _METRIC, "model": _MODEL, "dataset": _DATASET, "prompt_template": _PROMPT}
            )


# ============================================================================
# MetricJob discriminator (via TypeAdapter)
# ============================================================================


class TestMetricJobDiscriminator:
    def test_agent_only_routes_to_online_agent(self):
        data = {"metric": _METRIC, "agent": _NAT_AGENT, "dataset": _DATASET, "prompt_template": _PROMPT}
        job = MetricJobAdapter.validate_python(data)
        assert isinstance(job, MetricOnlineAgentJob)

    def test_model_routes_to_online(self):
        data = {"metric": _METRIC, "model": _MODEL, "dataset": _DATASET, "prompt_template": _PROMPT}
        job = MetricJobAdapter.validate_python(data)
        assert isinstance(job, MetricOnlineJob)

    def test_no_model_no_agent_routes_to_offline(self):
        data = {"metric": _METRIC, "dataset": _DATASET}
        job = MetricJobAdapter.validate_python(data)
        assert isinstance(job, MetricOfflineJob)


# ============================================================================
# BenchmarkOnlineJob (model or agent, mutually exclusive)
# ============================================================================


class TestBenchmarkOnlineJob:
    _BENCH = {
        "name": "bench",
        "dataset": "ws/dataset",
        "metrics": [{"metric_ref": "ws/m1", "metric": _METRIC}],
    }

    def test_accepts_model(self):
        job = BenchmarkOnlineJob.model_validate({"benchmark": self._BENCH, "model": _MODEL, "prompt_template": _PROMPT})
        assert job.model is not None

    def test_rejects_agent(self):
        with pytest.raises(ValidationError):
            BenchmarkOnlineJob.model_validate(
                {"benchmark": self._BENCH, "agent": _NAT_AGENT, "prompt_template": _PROMPT}
            )

    def test_rejects_both_model_and_agent(self):
        with pytest.raises(ValidationError):
            BenchmarkOnlineJob.model_validate(
                {"benchmark": self._BENCH, "model": _MODEL, "agent": _NAT_AGENT, "prompt_template": _PROMPT}
            )

    def test_rejects_missing_model(self):
        with pytest.raises(ValidationError, match="model"):
            BenchmarkOnlineJob.model_validate({"benchmark": self._BENCH, "prompt_template": _PROMPT})


# ============================================================================
# BenchmarkOnlineAgentJob (dedicated agent-only type)
# ============================================================================


class TestBenchmarkOnlineAgentJob:
    _BENCH = {
        "name": "bench",
        "dataset": "ws/dataset",
        "metrics": [{"metric_ref": "ws/m1", "metric": _METRIC}],
    }

    def test_accepts_agent(self):
        job = BenchmarkOnlineAgentJob.model_validate(
            {"benchmark": self._BENCH, "agent": _NAT_AGENT, "prompt_template": _PROMPT}
        )
        assert job.agent is not None

    def test_accepts_generic_agent(self):
        job = BenchmarkOnlineAgentJob.model_validate(
            {"benchmark": self._BENCH, "agent": _GENERIC_AGENT, "prompt_template": _PROMPT}
        )
        assert job.agent is not None
        assert job.agent.format == AgentFormat.GENERIC

    def test_rejects_model_field(self):
        """BenchmarkOnlineAgentJob does not accept a model field."""
        with pytest.raises(ValidationError):
            BenchmarkOnlineAgentJob.model_validate(
                {"benchmark": self._BENCH, "model": _MODEL, "prompt_template": _PROMPT}
            )

    def test_accepts_optional_fields(self):
        job = BenchmarkOnlineAgentJob.model_validate(
            {
                "benchmark": self._BENCH,
                "agent": _GENERIC_AGENT,
                "prompt_template": _PROMPT,
                "optional_fields": ["reference"],
            }
        )
        assert job.optional_fields == ["reference"]

    def test_rejects_empty_optional_field(self):
        with pytest.raises(ValidationError):
            BenchmarkOnlineAgentJob.model_validate(
                {
                    "benchmark": self._BENCH,
                    "agent": _GENERIC_AGENT,
                    "prompt_template": _PROMPT,
                    "optional_fields": [""],
                }
            )


# ============================================================================
# BenchmarkJob discriminator
# ============================================================================


class TestBenchmarkJobDiscriminator:
    _CUSTOM_BENCH = {
        "name": "bench",
        "dataset": "ws/ds",
        "metrics": [{"metric_ref": "ws/m1", "metric": _METRIC}],
    }

    _SYSTEM_BENCH = {"name": "aegis-v2"}

    def test_agent_only_routes_to_online_agent(self):
        data = {"benchmark": self._CUSTOM_BENCH, "agent": _GENERIC_AGENT, "prompt_template": _PROMPT}
        job = BenchmarkJobAdapter.validate_python(data)
        assert isinstance(job, BenchmarkOnlineAgentJob)

    def test_model_routes_to_online(self):
        data = {"benchmark": self._CUSTOM_BENCH, "model": _MODEL, "prompt_template": _PROMPT}
        job = BenchmarkJobAdapter.validate_python(data)
        assert isinstance(job, BenchmarkOnlineJob)

    def test_no_model_no_agent_routes_to_offline(self):
        data = {"benchmark": self._CUSTOM_BENCH}
        job = BenchmarkJobAdapter.validate_python(data)
        assert isinstance(job, BenchmarkOfflineJob)
