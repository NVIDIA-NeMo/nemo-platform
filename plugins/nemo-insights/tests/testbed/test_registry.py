# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from testbed.registry import load_registry


def test_loads_subject_with_shared_default(tmp_path: Path):
    toml = tmp_path / "t.toml"
    toml.write_text(
        'base_url = "https://shared"\n\n[nvq]\ntype = "intake"\nagent = "content-dedup"\nworkspace = "nvq"\n'
    )
    subjects = load_registry(toml)
    assert set(subjects) == {"nvq"}
    nvq = subjects["nvq"]
    assert nvq.type == "intake"
    assert nvq.config["agent"] == "content-dedup"
    assert nvq.config["base_url"] == "https://shared"  # shared default merged in


def test_per_subject_override_wins(tmp_path: Path):
    toml = tmp_path / "t.toml"
    toml.write_text('base_url = "https://shared"\n\n[local]\ntype = "intake"\nbase_url = "http://localhost:8000"\n')
    assert load_registry(toml)["local"].config["base_url"] == "http://localhost:8000"
