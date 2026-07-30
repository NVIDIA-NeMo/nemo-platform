# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repo-shape probes: context for authoring evals, never a reason a run cannot happen.

The invariant these defend is the meaning of ``runnable``. It answers exactly one question,
"can Harbor run this config", so a repo with no traces yet or no doctrine document must not
be reported as unrunnable. Only the validation ladder is allowed to fail a report.
"""

from pathlib import Path

from harbor_fixtures import StubClient
from nemo_eval_author_plugin.discovery import scan


def test_ethos_is_preferred_over_the_name_it_replaced(tmp_path):
    (tmp_path / "AGENT-SPEC.md").write_text("# Old\n")
    (tmp_path / "ETHOS.md").write_text("# New\n")
    (tmp_path / "README.md").write_text("# Readme\n")

    path, finding = scan.find_doctrine(tmp_path)

    assert path == tmp_path / "ETHOS.md"
    assert finding.status == "pass"
    assert finding.hint is None


def test_the_old_name_still_works_and_says_so(tmp_path):
    """Both names are honored while the rename is in flight, so the report is the signal."""
    (tmp_path / "AGENT-SPEC.md").write_text("# Old\n")
    (tmp_path / "README.md").write_text("# Readme\n")

    path, finding = scan.find_doctrine(tmp_path)

    assert path == tmp_path / "AGENT-SPEC.md"
    assert finding.hint is not None and "predates the rename" in finding.hint


def test_readme_is_the_last_resort(tmp_path):
    (tmp_path / "README.md").write_text("# Readme\n")

    path, finding = scan.find_doctrine(tmp_path)

    assert path == tmp_path / "README.md"
    assert finding.status == "pass"


def test_no_doctrine_is_a_warning_not_a_failure(tmp_path):
    path, finding = scan.find_doctrine(tmp_path)

    assert path is None
    assert finding.status == "warn"


def test_skill_bundles_are_found_by_their_marker_file(tmp_path):
    for name in ("triage", "escalate"):
        (tmp_path / "skills" / name).mkdir(parents=True)
        (tmp_path / "skills" / name / "SKILL.md").write_text(f"# {name}\n")

    skills, finding = scan.find_skills(tmp_path)

    assert len(skills) == 2
    assert finding.status == "pass"
    assert finding.hint is not None and "AgentConfig.skills" in finding.hint


def test_vendored_trees_are_not_searched(tmp_path):
    """A dependency's skills are not the repo's, and .venv dwarfs everything else."""
    vendored = tmp_path / ".venv" / "lib" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "SKILL.md").write_text("# not ours\n")

    skills, finding = scan.find_skills(tmp_path)

    assert skills == []
    assert finding.status == "warn"


async def test_available_traces_are_counted():
    finding = await scan.probe_traces(StubClient(trace_total=7), agent="ticket-triage", workspace="default")

    assert finding.status == "pass"
    assert "7 trace session(s)" in finding.message


async def test_no_traces_is_a_warning_with_a_next_step():
    finding = await scan.probe_traces(StubClient(trace_total=0), agent="ticket-triage", workspace="default")

    assert finding.status == "warn"
    assert finding.hint is not None and "telemetry" in finding.hint


async def test_an_unreachable_platform_never_blocks_a_run():
    finding = await scan.probe_traces(StubClient(trace_total=None), agent="ticket-triage", workspace="default")

    assert finding.status == "warn"
    assert finding.hint is not None and "Harbor runs fine without them" in finding.hint


def test_a_path_above_the_repo_is_rendered_absolute_rather_than_crashing(tmp_path):
    """``discover_profile`` walks upward, so this is a real case and not a defensive guess."""
    outside = tmp_path.parent / "optimizer.yaml"

    assert scan.display_path(outside, tmp_path) == str(outside)
    assert scan.display_path(tmp_path / "evals" / "task", tmp_path) == "evals/task"
    # The sentinel used for values declared inline rather than in a file.
    assert scan.display_path(Path("<job config>"), tmp_path) == "<job config>"
