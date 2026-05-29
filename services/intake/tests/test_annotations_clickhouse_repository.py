# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Annotation repository tests."""

import pytest
from nmp.intake.spans.annotations_repository import _annotation_order_by


def test_annotation_order_by_whitelists_supported_sort_keys():
    assert _annotation_order_by("created_at") == "created_at ASC, annotation_id ASC"
    assert _annotation_order_by("-created_at") == "created_at DESC, annotation_id ASC"


def test_annotation_order_by_rejects_unsupported_sort_keys():
    with pytest.raises(ValueError, match="Unsupported annotation sort field"):
        _annotation_order_by("created_at DESC; DROP TABLE annotations")
