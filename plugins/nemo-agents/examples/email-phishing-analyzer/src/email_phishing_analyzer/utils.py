# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from NeMo-Agent-Toolkit:
# examples/evaluation_and_profiling/email_phishing_analyzer/src/nat_email_phishing_analyzer/utils.py

import json
import re


def smart_parse(text: str) -> dict:
    """Extract structured data from a string using multiple fallback strategies.

    Handles, in order:
      1. Pure JSON objects.
      2. JSON embedded in surrounding text.
      3. ``key="value"`` / ``key=value`` / ``Key: "value"`` / ``key: value`` pairs.
      4. Plain text (returned under a ``message`` key).

    Args:
        text: Input text to parse.

    Returns:
        Parsed data, or ``{"message": text}`` when no structure is found.
    """
    # First try: parse as pure JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Second try: look for a JSON object embedded in the text.
        json_match = re.search(r"{.*}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Third try: parse key-value pairs.
        pattern = re.findall(
            r'(\w+)=["\']([^"\']+)["\']|'  # key="value"
            r"(\w+)=([\w.]+)|"  # key=value
            r'(\w+):\s*["\']([^"\']+)["\']|'  # Key: "value"
            r"(\w+):\s*([\w.]+)",  # key: value
            text,
        )

        if pattern:
            parsed_data = {}
            remaining_str = text

            for match in pattern:
                key = next(m for m in [match[0], match[2], match[4], match[6]] if m)
                value = next(m for m in [match[1], match[3], match[5], match[7]] if m)
                parsed_data[key.lower()] = value
                for possible_format in [
                    f"{key}={value}",
                    f"{key}: {value}",
                    f'{key}="{value}"',
                    f'{key}: "{value}"',
                ]:
                    remaining_str = remaining_str.replace(possible_format, "")

            remaining_str = remaining_str.strip().strip(",").strip()
            if remaining_str:
                parsed_data["message"] = remaining_str

            return parsed_data

        # Fallback: return the plain text as a message.
        return {"message": text}
