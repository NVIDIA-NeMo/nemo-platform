# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Answer one question about a records file.

Deterministic by construction: no LLM call, no network, standard library plus
NOOA only. The same instruction always produces the same answer.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from nooa import Agent
from nooa.tracing import enable_tracing, exporters
from nooa.unifiedllm import CompletionClient

enable_tracing(exporters=[exporters.jsonl(trace_dir=os.environ.get("TRACE_DIR", "/app/traces/"))])

logger = logging.getLogger(__name__)

RECORDS_PATH = Path(os.environ.get("RECORDS_PATH", "/app/data/records.json"))
FALLBACK = "I do not know how to answer that."

# Bound how much of the instruction we scan, so an oversized input cannot make
# the regex pass expensive.
MAX_INSTRUCTION_CHARS = 240

# Maps the word a question uses to the key the records store it under, so the
# answer line is always keyed by the canonical field name.
FIELD_ALIASES = {
    "department": "dept",
    "dept": "dept",
    "role": "role",
    "hours": "hours",
}

# The question forms this agent recognizes.
LOOKUP_RE = re.compile(r"what is the (\w+) of ([A-Za-z ]+)\?", re.IGNORECASE)
LIST_RE = re.compile(r"(?:list|how many) .*? in the (\w+) department", re.IGNORECASE)
COUNT_RE = re.compile(r"how many people are in the (\w+) department", re.IGNORECASE)

# Never called. The address is unroutable so an accidental model call fails
# loudly rather than silently making the agent nondeterministic.
_DUMMY_LLM = CompletionClient(model="none", api_key="unused", api_base="http://127.0.0.1:1/v1")


class ReportAgent(Agent, llm=_DUMMY_LLM):
    """Answer one question about the records file."""

    _enable_tracing = True

    def __init__(self, **kwargs: object) -> None:
        """Load the records the task environment supplied."""
        super().__init__(**kwargs)
        self._records: list[dict] = json.loads(RECORDS_PATH.read_text(encoding="utf-8"))

    def solve(self, instruction: str) -> str:
        """Return the single answer line this instruction asks for."""
        instruction = instruction[:MAX_INSTRUCTION_CHARS]
        try:
            for handler in (self.handle_lookup, self.handle_list, self.handle_count):
                answer = handler(instruction)
                if answer is not None:
                    return answer
        except Exception:  # noqa: BLE001
            # A handler fault must not take the process down: the caller still
            # needs an answer line written, and a non-zero exit would be reported
            # as a harness error rather than a scored result.
            logger.exception("handler failed")
        return FALLBACK

    def handle_lookup(self, instruction: str) -> str | None:
        """Return `<field>=<value>` for the named record, or None if not a lookup."""
        match = LOOKUP_RE.search(instruction)
        if match is None:
            return None
        field = FIELD_ALIASES.get(match.group(1).lower())
        if field is None:
            return None
        name = match.group(2).strip()
        record = next(r for r in self._records if r["name"] == name)
        return f"{field}={record[field]}"

    def handle_list(self, instruction: str) -> str | None:
        """Return `names=<comma-separated>` for a department, or None."""
        match = LIST_RE.search(instruction)
        if match is None:
            return None
        dept = match.group(1).lower()
        return "names=" + ",".join(r["name"] for r in self._records if r["dept"] == dept)

    def handle_count(self, instruction: str) -> str | None:
        """Return `count=<n>` for a department, or None."""
        match = COUNT_RE.search(instruction)
        if match is None:
            return None
        dept = match.group(1).lower()
        return f"count={sum(1 for r in self._records if r['dept'] == dept)}"
