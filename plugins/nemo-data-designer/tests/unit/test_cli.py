# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import nemo_data_designer_plugin.testing.utils as u
import pytest


@pytest.mark.parametrize("verb", ["run", "submit"])
def test_preview_exposes_save_results_flags(verb: str) -> None:
    result = u.invoke_cli(["preview", verb, "--help"])

    assert result.exit_code == 0, result.output
    assert "--save-results" in result.output
    assert "--artifact-path" in result.output
    assert "--non-interactive" in result.output
