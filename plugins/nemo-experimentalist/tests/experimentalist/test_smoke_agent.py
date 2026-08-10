# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-weakness unit tests for the smoke agent. No Docker, no network.

Each test pins one documented behaviour of the baseline agent. A failure here
usually means someone "fixed" the agent; see
plugins/nemo-experimentalist/docs/smoke-agent-weaknesses.md first.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import _AGENT_COPY_EXCLUDE_NAMES

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
    """The control path: plain ASCII names resolve, so controls pass at baseline."""
    agent = agent_module.ReportAgent()
    assert agent.solve("What is the department of Ada Lovelace?") == "dept=research"


def test_g1_no_aggregation_capability(agent_module: Any) -> None:
    agent = agent_module.ReportAgent()
    answer = agent.solve("What is the total hours for the research department?")
    assert answer == agent_module.FALLBACK


def test_g2_punctuated_names_fall_through(agent_module: Any) -> None:
    agent = agent_module.ReportAgent()
    for name in ("O'Brien", "Zoë Washington", "Ann-Marie Cruz"):
        assert agent.solve(f"What is the department of {name}?") == agent_module.FALLBACK


def test_g3_long_instruction_is_clipped(agent_module: Any) -> None:
    agent = agent_module.ReportAgent()
    preamble = "Reporting policy applies to this request. " * 10
    assert len(preamble) > agent_module.MAX_INSTRUCTION_CHARS
    question = "What is the department of Grace Hopper?"
    assert agent.solve(question) == "dept=research"
    assert agent.solve(preamble + question) == agent_module.FALLBACK


def test_g4_list_handler_shadows_count(agent_module: Any) -> None:
    agent = agent_module.ReportAgent()
    answer = agent.solve("How many people are in the research department?")
    assert answer.startswith("names="), "expected the greedy list handler to win"
    assert answer != "count=3"


def test_g5_missing_record_does_not_degrade(agent_module: Any) -> None:
    agent = agent_module.ReportAgent()
    assert agent.solve("What is the department of Alan Turing?") == agent_module.FALLBACK


def test_g5_empty_field_does_not_degrade(agent_module: Any) -> None:
    agent = agent_module.ReportAgent()
    assert agent.solve("What is the role of Karl Jung?") == "role="


def test_agent_is_deterministic(agent_module: Any) -> None:
    """Repeated identical input must give byte-identical output."""
    agent = agent_module.ReportAgent()
    question = "What is the department of Ada Lovelace?"
    assert len({agent.solve(question) for _ in range(20)}) == 1


def test_agent_declares_no_strategy_methods() -> None:
    """A @strategy method would make the agent LLM-driven and nondeterministic."""
    source = (_EXAMPLE_DIR / "agent" / "agent.py").read_text(encoding="utf-8")
    assert "@strategy" not in source
    assert "CodeActStrategy" not in source


def test_spec_forbids_llm_backed_changes() -> None:
    """The Coder reads AGENT-SPEC.md first; the determinism rule has to be in it."""
    spec = (_EXAMPLE_DIR / "AGENT-SPEC.md").read_text(encoding="utf-8").lower()
    for phrase in ("@strategy", "deterministic", "no llm", "offline"):
        assert phrase in spec, f"AGENT-SPEC.md must mention {phrase!r}"


# Names for what the fixture measures.
_LEAK_TERMS = ("weakness", "known gap", "deliberate", "on purpose", "do not fix")

# Only what `agent_source` points at is copied into a candidate workspace, minus
# whatever the copier drops on the way. Imported rather than restated: a
# hand-written skip list drifts, and it drifted before -- an earlier version
# skipped `traces`, which the copier does *not* exclude, so a description left
# there would have reached the Coder without failing this guard.
_AGENT_SOURCE_DIRNAME = "agent"
_LEAK_SCAN_SKIP_DIRS = _AGENT_COPY_EXCLUDE_NAMES


def test_agent_source_points_at_the_agent_subdirectory() -> None:
    """The leak scan below only covers `agent/`, which is only sound while this holds.

    Widening `agent_source` back to `.` would put README, configs, and scripts
    back in front of the Coder while the scan still checked one subdirectory --
    the failure would be silent, which is exactly the shape of bug that put a
    live `.env` into every candidate workspace.
    """
    profile = (_EXAMPLE_DIR / "optimizer.yaml").read_text(encoding="utf-8")
    found = re.search(r"^agent_source:\s*(\S+)", profile, re.MULTILINE)
    assert found is not None, "optimizer.yaml must declare agent_source"
    assert found.group(1) == f"./{_AGENT_SOURCE_DIRNAME}", (
        f"agent_source is {found.group(1)!r}; the leak scan assumes ./{_AGENT_SOURCE_DIRNAME}"
    )


def test_agent_source_does_not_leak_the_weaknesses() -> None:
    """Nothing the Coder can read may describe what the fixture measures.

    A description there hands the Coder the diagnosis this fixture exists to
    test, and a run could pass with a broken Analyzer. The boundary is structural
    rather than a list of exclusions: material that explains the fixture lives
    outside `agent/`, so README, configs, and scripts are free to be candid.

    AGENT-SPEC.md reaches the LLM components by a separate path and is covered by
    test_spec_does_not_leak_the_weaknesses.
    """
    agent_dir = _EXAMPLE_DIR / _AGENT_SOURCE_DIRNAME
    offenders: list[str] = []
    for path in sorted(agent_dir.rglob("*")):
        if not path.is_file() or set(path.relative_to(agent_dir).parts) & _LEAK_SCAN_SKIP_DIRS:
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            continue
        offenders.extend(f"{path.relative_to(agent_dir)}: {term!r}" for term in _LEAK_TERMS if term in text)
    assert not offenders, "agent source leaks what the fixture measures:\n  " + "\n  ".join(offenders)


def test_spec_does_not_leak_the_weaknesses() -> None:
    """The spec is copied into source-agent/ and read before any source file.

    Naming the gaps there hands the Coder the diagnosis the fixture exists to
    test, and lets a run pass with a broken Analyzer.
    """
    spec = (_EXAMPLE_DIR / "AGENT-SPEC.md").read_text(encoding="utf-8").lower()
    for leak in ("weakness", "known gap", "deliberate", "aggregat", "on purpose"):
        assert leak not in spec, f"AGENT-SPEC.md must not mention {leak!r}"
