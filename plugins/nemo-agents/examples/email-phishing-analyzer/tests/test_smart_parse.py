# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nat_email_phishing_analyzer.utils import smart_parse


def test_valid_non_object_json_falls_through_to_dict():
    # Valid JSON but not an object — must not be returned as-is (would break .get).
    assert smart_parse("true") == {"message": "true"}
    assert smart_parse("42") == {"message": "42"}
    assert smart_parse("[1, 2, 3]") == {"message": "[1, 2, 3]"}
    assert smart_parse('"just a string"') == {"message": '"just a string"'}
    assert smart_parse("null") == {"message": "null"}


def test_object_json_is_parsed():
    assert smart_parse('{"is_likely_phishing": true}') == {"is_likely_phishing": True}


def test_embedded_object_json_is_extracted():
    assert smart_parse('Here is the result: {"is_likely_phishing": false}')["is_likely_phishing"] is False


def test_always_returns_dict():
    for text in ["true", "42", "[1,2]", '"s"', "null", "plain text", '{"k": "v"}', "key: value"]:
        assert isinstance(smart_parse(text), dict), text
