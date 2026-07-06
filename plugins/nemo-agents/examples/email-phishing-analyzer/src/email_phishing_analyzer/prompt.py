# SPDX-FileCopyrightText: Copyright (c) 2024-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Vendored from NeMo-Agent-Toolkit:
# examples/evaluation_and_profiling/email_phishing_analyzer/src/nat_email_phishing_analyzer/prompt.py

phishing_prompt = """

Examine the following email content and determine if it exhibits signs of malicious intent. Look for any
suspicious signals that may indicate phishing, such as requests for personal information or suspicious tone.

Email content:
{body}

Return your findings as a JSON object with these fields:

- is_likely_phishing: (boolean) true if phishing is suspected
- explanation: (string) detailed explanation of your reasoning

"""
