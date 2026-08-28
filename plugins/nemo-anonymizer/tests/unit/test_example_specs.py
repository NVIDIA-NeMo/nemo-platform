# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import yaml
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest, PreviewRequest
from nemo_anonymizer_plugin.config import DEFAULT_MAX_PREVIEW_NUM_RECORDS

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _PLUGIN_ROOT / "examples"


def _load_example(name: str) -> dict:
    loaded = yaml.safe_load((_EXAMPLES / name).read_text())
    assert isinstance(loaded, dict)
    return loaded


def test_redact_example_validates_for_preview_and_run() -> None:
    payload = _load_example("redact.yaml")
    request = AnonymizerRequest.model_validate(payload)
    preview_request = PreviewRequest.model_validate(payload)

    assert request.data.source == "plugins/nemo-anonymizer/examples/anonymizer-input.csv"
    assert request.data.text_column == "biography"
    assert preview_request.num_records == DEFAULT_MAX_PREVIEW_NUM_RECORDS
