# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Deterministic IOC extraction exposed as an MCP stdio server.

Pure standard-library regex (ported from the email-security-analyst example);
no NAT, no LLM, no network. The phishing subagent's judgement stays visible
while the mechanical URL/domain harvesting is a traced tool call.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP

# Stop at whitespace and at the characters that usually wrap a URL in prose.
_URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+")
# A dotted label sequence ending in an alphabetic TLD: example.com, mail.example.co.uk.
_DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}\b", re.IGNORECASE)
# Trailing punctuation that belongs to the sentence, not the URL.
_TRAILING_PUNCT = ".,;:!?'\""


def extract_iocs(text: str) -> dict[str, list[str]]:
    """Pull indicators of compromise out of free text.

    Finds absolute http(s) URLs and every domain mentioned, including the hosts
    of those URLs and bare domains appearing in prose or in a ``From:`` line.

    Args:
        text: Email headers, body, or any free text to scan.

    Returns:
        Dict with sorted, de-duplicated ``urls`` and ``domains`` lists.
    """
    urls = {url.rstrip(_TRAILING_PUNCT) for url in _URL_RE.findall(text)}

    domains: set[str] = set()
    for url in urls:
        try:
            host = urlsplit(url).hostname
        except ValueError:
            # A malformed match (e.g. an unparseable netloc) is not a usable IOC.
            continue
        if host:
            domains.add(host.lower())
    # ponytail: a dotted word pair at a sentence boundary ("Thanks.Best") can look
    # like a domain. Add a public-suffix check if false positives ever matter.
    domains.update(match.lower() for match in _DOMAIN_RE.findall(text))

    return {"urls": sorted(urls), "domains": sorted(domains)}


mcp = FastMCP("email-security-triage-iocs")


@mcp.tool(name="extract_iocs")
def _extract_iocs_tool(text: str) -> dict[str, list[str]]:
    """Extract URLs and domains (IOCs) from email text, including the From: line."""
    return extract_iocs(text)


def main() -> None:
    """Run the IOC-extraction MCP server over stdio."""
    mcp.run(transport="stdio")
