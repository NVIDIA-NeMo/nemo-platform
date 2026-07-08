# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Span storage helper tests."""

from nemo_intake_plugin.spans.storage import json_loads_or_none, stable_id


def test_stable_id_uses_unambiguous_part_boundaries():
    assert stable_id("a", "b\x1fc") != stable_id("a\x1fb", "c")


def test_json_loads_or_none_returns_none_for_malformed_json():
    assert json_loads_or_none('{"unterminated"') is None


def test_json_loads_or_none_passes_through_non_string_values():
    value = {"already": "decoded"}

    assert json_loads_or_none(value) == value
