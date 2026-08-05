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

"""Deterministic IOC extraction, ported from the email-security-analyst example.

Pure standard-library regex; no NAT, no LLM, no network. Exposed to the agent as
an MCP tool so the phishing subagent's judgement stays visible while the
mechanical URL/domain harvesting is a traced tool call.
"""

import re
from urllib.parse import urlsplit

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

    domains = {host.lower() for url in urls if (host := urlsplit(url).hostname)}
    # ponytail: a dotted word pair at a sentence boundary ("Thanks.Best") can look
    # like a domain. Add a public-suffix check if false positives ever matter.
    domains.update(match.lower() for match in _DOMAIN_RE.findall(text))

    return {"urls": sorted(urls), "domains": sorted(domains)}
