# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Parse a garak ``.hitlog.jsonl`` artifact into structured hits.

Auditor returns the hitlog only as an opaque file artifact; this module is the
structured-hit surface the hardening loop needs. garak hitlog field names vary
by version, so read defensively and keep the raw record.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from nemo_agents_plugin.hardening.models import AttackHit

logger = logging.getLogger(__name__)


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # garak sometimes nests {"text": ...} or a turns structure.
        if isinstance(value.get("text"), str):
            return value["text"]
    return "" if value is None else str(value)


def parse_hitlog(path: Path) -> list[AttackHit]:
    """Return the ordered list of hits from a garak hitlog file.

    Blank and malformed lines are skipped (logged at debug), so a partially
    written hitlog still yields the hits that did parse.
    """
    hits: list[AttackHit] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("skipping malformed hitlog line: %r", line[:120])
                continue
            if not isinstance(record, dict):
                continue
            probe = record.get("probe_classname") or record.get("probe") or ""
            hits.append(
                AttackHit(
                    probe=str(probe),
                    prompt=_text(record.get("prompt")),
                    output=_text(record.get("output")),
                    detector=str(record.get("detector") or ""),
                    index=len(hits),
                    tool=record.get("tool") if isinstance(record.get("tool"), str) else None,
                    raw=record,
                )
            )
    return hits
