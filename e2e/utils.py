# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared utilities for e2e tests."""

import json
from typing import Any


def collect_sse_chunks(response) -> list[dict[str, Any]]:
    """Collect JSON ``data:`` events from a text/event-stream response."""
    chunks: list[dict[str, Any]] = []
    for line in response.iter_lines():
        if line.startswith("data: ") and line != "data: [DONE]":
            chunks.append(json.loads(line[len("data: ") :]))

    return chunks
