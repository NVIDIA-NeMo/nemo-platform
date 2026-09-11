# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib
import sys


def test_typed_client_import_does_not_load_analysis_runtime() -> None:
    for module_name in [
        "nemo_insights_plugin.client",
        "nemo_insights_plugin.endpoints",
        "nemo_insights_plugin.types",
        "nemo_insights_plugin.jobs.analyze",
        "nemo_insights_plugin.analyst.run",
    ]:
        sys.modules.pop(module_name, None)

    importlib.import_module("nemo_insights_plugin.client")

    assert "nemo_insights_plugin.jobs.analyze" not in sys.modules
    assert "nemo_insights_plugin.analyst.run" not in sys.modules
