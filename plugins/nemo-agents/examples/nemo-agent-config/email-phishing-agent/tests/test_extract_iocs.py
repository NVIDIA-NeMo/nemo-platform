# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from mcps.iocs import extract_iocs


def test_url_and_its_host_are_both_reported():
    result = extract_iocs("Click http://malicious-link.example.com/claim to continue.")
    assert result["urls"] == ["http://malicious-link.example.com/claim"]
    assert result["domains"] == ["malicious-link.example.com"]


def test_trailing_sentence_punctuation_is_not_part_of_the_url():
    # A URL at the end of a sentence must not swallow the period.
    assert extract_iocs("Go to https://example.com/verify.")["urls"] == ["https://example.com/verify"]
    assert extract_iocs("See https://example.com/a, then stop")["urls"] == ["https://example.com/a"]


def test_url_wrapped_in_brackets_or_parens_is_bounded():
    assert extract_iocs("(https://example.com/x)")["urls"] == ["https://example.com/x"]
    assert extract_iocs("<https://example.com/y>")["urls"] == ["https://example.com/y"]


def test_sender_domain_is_found_in_a_from_line():
    # The sender is a top phishing tell; extract_iocs must surface its domain.
    result = extract_iocs("From: security-alerts@bank-verify.example.net\nVisit corp.example.org")
    assert result["domains"] == ["bank-verify.example.net", "corp.example.org"]
    assert result["urls"] == []


def test_results_are_sorted_and_deduplicated():
    text = "https://b.example.com https://a.example.com https://b.example.com a.example.com"
    result = extract_iocs(text)
    assert result["urls"] == ["https://a.example.com", "https://b.example.com"]
    assert result["domains"] == ["a.example.com", "b.example.com"]


def test_domains_are_lowercased():
    assert extract_iocs("Mail from ACCOUNTS@Shop-Example.COM")["domains"] == ["shop-example.com"]


def test_clean_text_yields_empty_lists():
    assert extract_iocs("Reminder: project meeting Friday at 2pm") == {"urls": [], "domains": []}


def test_empty_input():
    assert extract_iocs("") == {"urls": [], "domains": []}
