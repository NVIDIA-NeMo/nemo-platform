# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for metric_results parser selection."""

from nmp.evaluator.app.jobs.metric_results import _get_results_parser
from nmp.evaluator.app.jobs.result_parsers.custom import CustomResultsParser


def test_uses_custom_parser():
    parser = _get_results_parser()
    assert isinstance(parser, CustomResultsParser)
