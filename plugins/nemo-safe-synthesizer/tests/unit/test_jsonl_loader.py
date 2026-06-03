# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from nemo_safe_synthesizer_plugin.tasks.safe_synthesizer.jsonl_loader import load_jsonl_file, try_repair_json_line


def test_try_repair_json_line_repairs_escaped_quote_before_object_end():
    assert try_repair_json_line('{"content": "The Lumi\\u00e8res\\"}') == '{"content": "The Lumi\\u00e8res"}'


def test_load_jsonl_file_repairs_common_escaping_issue(tmp_path):
    filepath = tmp_path / "test.jsonl"
    filepath.write_text(
        '{"messages": [{"role": "user", "content": "The Lumi\\u00e8res\\"}, '
        '{"role": "system", "content": "response"}]}\n',
        encoding="utf-8",
    )

    df = load_jsonl_file(str(filepath))

    assert len(df) == 1
    assert df.iloc[0]["messages"][0]["content"] == "The Lumi\u00e8res"
