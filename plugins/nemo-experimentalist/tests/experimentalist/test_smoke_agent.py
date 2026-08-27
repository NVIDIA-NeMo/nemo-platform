# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-weakness unit tests for the smoke agent. No Docker, no network.

Each test pins one documented behaviour of the baseline agent. A failure here
usually means someone "fixed" the agent; see
plugins/nemo-experimentalist/examples/smoke-agent/README.md first.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import _ignore_agent_copy
from nemo_experimentalist_plugin.profile import load_profile

_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "smoke-agent"
_RECORDS = _EXAMPLE_DIR / "dataset" / "_shared" / "records.json"


@pytest.fixture(scope="module")
def agent_module(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Import agent.py by path; it is not an installed package."""
    os.environ["RECORDS_PATH"] = str(_RECORDS)
    os.environ["TRACE_DIR"] = str(tmp_path_factory.mktemp("traces"))
    spec = importlib.util.spec_from_file_location("_smoke_agent", _EXAMPLE_DIR / "agent" / "agent.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_working_lookup_succeeds(agent_module: Any) -> None:
    """Check that a normal lookup works at baseline."""
    agent = agent_module.ReportAgent()
    assert agent.solve("What is the department of Ada Lovelace?") == "dept=research"


def test_g1_no_aggregation_capability(agent_module: Any) -> None:
    """Check that the baseline cannot add up hours."""
    agent = agent_module.ReportAgent()
    answer = agent.solve("What is the total hours for the research department?")
    assert answer == agent_module.FALLBACK


def test_g2_punctuated_names_fall_through(agent_module: Any) -> None:
    """Check that the baseline cannot look up names with punctuation or accents."""
    agent = agent_module.ReportAgent()
    for name in ("O'Brien", "Zoë Washington", "Ann-Marie Cruz"):
        assert agent.solve(f"What is the department of {name}?") == agent_module.FALLBACK


def test_g3_long_instruction_is_clipped(agent_module: Any) -> None:
    """Check that a long preamble hides an otherwise valid question."""
    agent = agent_module.ReportAgent()
    preamble = "Reporting policy applies to this request. " * 10
    assert len(preamble) > agent_module.MAX_INSTRUCTION_CHARS
    question = "What is the department of Grace Hopper?"
    assert agent.solve(question) == "dept=research"
    assert agent.solve(preamble + question) == agent_module.FALLBACK


def test_g4_list_handler_shadows_count(agent_module: Any) -> None:
    """Check that a count question wrongly returns a list."""
    agent = agent_module.ReportAgent()
    answer = agent.solve("How many people are in the research department?")
    assert answer.startswith("names="), "expected the greedy list handler to win"
    assert answer != "count=3"


def test_g5_missing_record_does_not_degrade(agent_module: Any) -> None:
    """Check that an unknown person falls back instead of giving the requested answer."""
    agent = agent_module.ReportAgent()
    assert agent.solve("What is the department of Alan Turing?") == agent_module.FALLBACK


def test_g5_empty_field_does_not_degrade(agent_module: Any) -> None:
    """Check that an empty record field is returned as an empty answer."""
    agent = agent_module.ReportAgent()
    assert agent.solve("What is the role of Karl Jung?") == "role="


def test_agent_is_deterministic(agent_module: Any) -> None:
    """Check that repeated identical input gives identical output."""
    agent = agent_module.ReportAgent()
    question = "What is the department of Ada Lovelace?"
    assert len({agent.solve(question) for _ in range(20)}) == 1


def test_agent_declares_no_strategy_methods() -> None:
    """Check that the agent does not declare LLM-backed strategy methods."""
    source = (_EXAMPLE_DIR / "agent" / "agent.py").read_text(encoding="utf-8")
    assert "@strategy" not in source
    assert "CodeActStrategy" not in source


def test_ethos_forbids_llm_backed_changes() -> None:
    """Check that the Ethos forbids LLM-backed changes."""
    ethos = (_EXAMPLE_DIR / "ETHOS.md").read_text(encoding="utf-8").lower()
    for phrase in ("@strategy", "deterministic", "no llm", "offline"):
        assert phrase in ethos, f"ETHOS.md must mention {phrase!r}"


# The candidate must receive only these implementation files. Keeping this exact
# list makes an added README, config, dataset, or helper visible in review rather
# than silently giving the Coder more context.
_AGENT_SOURCE_DIRNAME = "agent"
_CANDIDATE_SOURCE_FILES = ("agent.py", "harbor_wrapper.py", "main.py")


def test_candidate_copy_contains_only_the_declared_agent_source(tmp_path: Path) -> None:
    """Check that the Coder receives only the declared agent source files.

    A profile spelling check cannot prove the effective path or the copied file
    set. This guards the boundary that previously leaked a live `.env` into
    candidate workspaces: only the three implementation files may arrive.
    """
    profile = load_profile(_EXAMPLE_DIR / "optimizer.yaml")
    source = (profile.profile_dir / profile.agent_source).resolve()
    expected_source = (_EXAMPLE_DIR / _AGENT_SOURCE_DIRNAME).resolve()
    assert source == expected_source, f"agent_source resolves to {source}, expected {expected_source}"

    copied = tmp_path / "candidate-source"
    shutil.copytree(source, copied, ignore=_ignore_agent_copy)
    files = tuple(sorted(path.relative_to(copied).as_posix() for path in copied.rglob("*") if path.is_file()))
    assert files == _CANDIDATE_SOURCE_FILES, (
        f"candidate source must contain only the declared implementation files; found {files}"
    )
