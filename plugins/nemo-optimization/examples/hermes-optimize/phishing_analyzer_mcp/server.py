# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A deterministic email phishing analyzer exposed as an MCP stdio server.

Stands in for a real analyzer so the ``optimize-mcp.yaml`` study is self-contained: the study
tunes the Hermes coordinator that calls this tool, not the tool itself, so a fixed, rule-based
classifier gives the same signal a fixed LLM analyzer would while needing no credentials or
external checkout. The rules are tuned to ``dataset-mcp.json``.
"""

from __future__ import annotations

import re

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("email-phishing-analyzer")

_LINK = re.compile(r"https?://", re.IGNORECASE)
_SIGNALS: dict[str, re.Pattern[str]] = {
    "prize_or_free_offer": re.compile(r"\b(free|prize|congratulations|selected to receive|winner)\b", re.IGNORECASE),
    "urgency": re.compile(r"\b(urgent|act fast|within 24 hours|immediately|limited)\b", re.IGNORECASE),
    "credential_request": re.compile(r"\b(verify your identity|enter(ing)? your credentials|password|log ?in)\b", re.I),
    "account_threat": re.compile(r"\b(suspend(ed|sion)?|disabled|unusual activity)\b", re.IGNORECASE),
    "click_lure": re.compile(r"\bclick (here|the link)\b", re.IGNORECASE),
}


def analyze(text: str) -> dict[str, object]:
    """Classify an email body as phishing or benign from lexical signals.

    A link combined with any lure is phishing; two or more lures without a link are phishing too.
    Everything else is benign.
    """
    signals = sorted(name for name, pattern in _SIGNALS.items() if pattern.search(text))
    has_link = bool(_LINK.search(text))
    if has_link:
        signals.append("external_link")
    is_phishing = (has_link and len(signals) > 1) or len(signals) >= 2
    confidence = min(0.5 + 0.15 * len(signals), 0.99) if is_phishing else max(0.95 - 0.2 * len(signals), 0.5)
    return {
        "is_likely_phishing": is_phishing,
        "label": "phishing" if is_phishing else "benign",
        "confidence": round(confidence, 2),
        "signals": signals,
    }


@mcp.tool()
def email_phishing_analyzer(text: str) -> dict[str, object]:
    """Analyze an email (subject and body, verbatim) and report whether it is likely phishing."""
    return analyze(text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
