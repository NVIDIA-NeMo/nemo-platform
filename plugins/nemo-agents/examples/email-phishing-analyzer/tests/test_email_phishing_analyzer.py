# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the email-phishing-analyzer config, packaging, and evaluator."""

import csv
import io
from collections import Counter
from importlib.metadata import entry_points
from importlib.resources import files

import pytest
import yaml
from email_phishing_analyzer.classification_evaluator import (
    EmailPhishingClassificationEvaluatorConfig,
    _metric_from_counts,
    make_evaluate_fn,
    predict_label,
)
from email_phishing_analyzer.register import EmailPhishingAnalyzerConfig
from nat.data_models.component_ref import LLMRef
from nat.data_models.evaluator import EvalInput, EvalInputItem


class TestToolConfig:
    def test_config_registers_tool_type(self):
        assert EmailPhishingAnalyzerConfig._typed_model_name == "email_phishing_analyzer"

    def test_prompt_default_has_body_placeholder(self):
        assert "{body}" in EmailPhishingAnalyzerConfig(llm=LLMRef("llm")).prompt


class TestEvaluatorConfig:
    def test_config_registers_evaluator_type(self):
        assert EmailPhishingClassificationEvaluatorConfig._typed_model_name == "email_phishing_classification"

    def test_default_metric_is_recall(self):
        assert EmailPhishingClassificationEvaluatorConfig().metric == "recall"


class TestPredictLabel:
    @pytest.mark.parametrize(
        "output,expected",
        [
            ('{"is_likely_phishing": true, "explanation": "asks for credentials"}', "phishing"),
            ('{"is_likely_phishing": false, "explanation": "routine note"}', "benign"),
            ("After analysis, this email is phishing.", "phishing"),
            ("This looks benign to me.", "benign"),
            ("The tool reasoned about phishing signals but concluded it is benign", "benign"),
            ("no verdict here", None),
        ],
    )
    def test_predict_label(self, output, expected):
        assert predict_label(output, "phishing", "benign") == expected

    def test_none_output(self):
        assert predict_label(None, "phishing", "benign") is None


class TestMetricMath:
    # tp=8, fp=2, fn=2, tn=8  -> precision=0.8, recall=0.8, accuracy=0.8, f1=0.8
    def test_balanced_counts(self):
        assert _metric_from_counts("precision", 8, 2, 2, 8) == pytest.approx(0.8)
        assert _metric_from_counts("recall", 8, 2, 2, 8) == pytest.approx(0.8)
        assert _metric_from_counts("accuracy", 8, 2, 2, 8) == pytest.approx(0.8)
        assert _metric_from_counts("f1", 8, 2, 2, 8) == pytest.approx(0.8)

    def test_missed_phishing_lowers_recall(self):
        # 10 real phishing, caught 5 -> recall 0.5; no false positives -> precision 1.0
        assert _metric_from_counts("recall", 5, 0, 5, 10) == pytest.approx(0.5)
        assert _metric_from_counts("precision", 5, 0, 5, 10) == pytest.approx(1.0)

    def test_zero_division_guards(self):
        assert _metric_from_counts("recall", 0, 0, 0, 0) == 0.0
        assert _metric_from_counts("precision", 0, 0, 0, 0) == 0.0
        assert _metric_from_counts("f1", 0, 0, 0, 0) == 0.0


def _item(item_id, gold, output):
    return EvalInputItem(
        id=item_id,
        input_obj="email body",
        expected_output_obj=gold,
        output_obj=output,
        full_dataset_entry={},
    )


class TestEvaluateFn:
    async def _run(self, metric, items):
        config = EmailPhishingClassificationEvaluatorConfig(metric=metric)
        return await make_evaluate_fn(config)(EvalInput(eval_input_items=items))

    @pytest.mark.asyncio
    async def test_perfect_recall(self):
        items = [
            _item(1, "phishing", '{"is_likely_phishing": true}'),
            _item(2, "phishing", "this is phishing"),
            _item(3, "benign", "benign"),
        ]
        out = await self._run("recall", items)
        assert out.average_score == 1.0
        assert len(out.eval_output_items) == 3

    @pytest.mark.asyncio
    async def test_missed_phishing_drops_recall(self):
        # A cheaper model that misclassifies phishing as benign must show it.
        items = [
            _item(1, "phishing", "benign"),  # missed -> FN
            _item(2, "phishing", "phishing"),  # caught -> TP
            _item(3, "benign", "benign"),  # TN
        ]
        out = await self._run("recall", items)
        assert out.average_score == 0.5

    @pytest.mark.asyncio
    async def test_unparseable_counts_as_miss(self):
        items = [_item(1, "phishing", "no clear verdict")]
        out = await self._run("recall", items)
        assert out.average_score == 0.0
        assert out.eval_output_items[0].score == 0.0


class TestPackageData:
    def test_agent_yml_bundled_and_valid(self):
        content = files("email_phishing_analyzer").joinpath("email-phishing-agent.yml").read_text(encoding="utf-8")
        config = yaml.safe_load(content)
        assert config["workflow"]["_type"] == "react_agent"
        assert "email_phishing_analyzer" in config["functions"]

    def test_eval_yml_bundled_and_valid(self):
        content = files("email_phishing_analyzer").joinpath("email-phishing-eval.yml").read_text(encoding="utf-8")
        config = yaml.safe_load(content)
        evaluators = config["eval"]["evaluators"]
        assert {"recall", "precision", "accuracy", "f1"} <= set(evaluators)
        assert all(e["_type"] == "email_phishing_classification" for e in evaluators.values())

    def test_optimize_yml_bundled_and_valid(self):
        content = files("email_phishing_analyzer").joinpath("email-phishing-optimize.yml").read_text(encoding="utf-8")
        config = yaml.safe_load(content)
        assert "optimizer" in config
        assert config["optimizer"]["eval_metrics"]["recall"]["direction"] == "maximize"

    def test_dataset_bundled_balanced_and_labeled(self):
        content = files("email_phishing_analyzer").joinpath("email-phishing-eval-data.csv").read_text(encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(content)))
        assert len(rows) >= 200
        counts = Counter(r["label"] for r in rows)
        assert set(counts) == {"phishing", "benign"}
        # Balanced within 10%.
        assert abs(counts["phishing"] - counts["benign"]) <= 0.1 * len(rows)
        assert all(r["subject"] and r["body"] for r in rows)


class TestEntryPoints:
    def test_nat_components_entry_point_registered(self):
        eps = entry_points(group="nat.components")
        assert "nemo_agents_example_email_phishing" in {ep.name for ep in eps}

    def test_entry_point_resolves_to_register_module(self):
        eps = entry_points(group="nat.components")
        ep = next(ep for ep in eps if ep.name == "nemo_agents_example_email_phishing")
        assert ep.value == "email_phishing_analyzer.register"
