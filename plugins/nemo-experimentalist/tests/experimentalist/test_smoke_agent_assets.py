# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep the smoke agent's task image, its NOOA pin, and its verifier honest.

No Docker here on purpose: the image tag is a content hash, so a forgotten
rebuild is a string comparison rather than something only a container run can
reveal.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import re
import shutil
import sys
import tomllib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "smoke-agent"
_SHARED = _EXAMPLE_DIR / "dataset" / "_shared"
_HASHED = ("Dockerfile", "records.json")
_RENDERED_TASK_TREE_SHA256 = "3fabb557da0cd6f4cda6c713b261e591bf52ed5ad936f2d3ee7bd6b12431099a"


def _root_nooa_rev() -> str:
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["uv"]["sources"]["nooa"]["rev"]


def _expected_tag() -> str:
    digest = hashlib.sha256()
    for name in _HASHED:
        digest.update((_SHARED / name).read_bytes())
    return f"smoke-agent-env:sha-{digest.hexdigest()[:12]}"


def _template_toml() -> Path:
    """Return the canonical task shape."""
    return _EXAMPLE_DIR / "dataset" / "task-template" / "task.toml"


@functools.cache
def _renderer() -> Any:
    """Import the renderer by path; scripts is not a package."""
    path = _EXAMPLE_DIR / "scripts" / "render_tasks.py"
    spec = importlib.util.spec_from_file_location("_smoke_render_tasks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _tree_sha256(root: Path) -> str:
    """Hash a task tree's paths and bytes."""
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != ".gitignore"):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


_EXPECTED_METRIC_KEYS = ("reward", "shape_ok")


def test_verifier_emits_exactly_the_two_metric_keys() -> None:
    """Check that the verifier emits exactly the two expected metric keys.

    Asserting only that both names appear somewhere would also accept a third
    key, or a second write, either of which changes the metric set every trial
    reports. Parse what is actually emitted instead.
    """
    code = _verifier_code()
    writes = [line.strip() for line in code.splitlines() if "reward.json" in line and "printf" in line]
    assert len(writes) == 1, f"expected exactly one line writing reward.json, found {len(writes)}: {writes}"
    keys = tuple(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', writes[0]))
    assert keys == _EXPECTED_METRIC_KEYS, f"verifier emits {keys}, expected exactly {_EXPECTED_METRIC_KEYS}"


def _verifier_code() -> str:
    """Return test.sh with comment lines dropped.

    Every guard below is a substring check, and the script documents each choice
    in a comment that names the rejected alternative. Checking raw text would
    match those comments rather than the code.
    """
    lines = (_SHARED / "test.sh").read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def _shell_options(code: str) -> tuple[set[str], set[str]]:
    """Return (short flags, `-o` long options) enabled across every `set` line.

    Parsed rather than string-matched so the contract holds however it is spelled:
    ``set -uo pipefail``, ``set -u -o pipefail`` and ``set -euo pipefail`` all
    resolve to the same options.
    """
    short: set[str] = set()
    long: set[str] = set()
    for raw in code.splitlines():
        line = raw.strip()
        if not line.startswith("set "):
            continue
        tokens = line.split()[1:]
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if not token.startswith("-") or token.startswith("--"):
                continue
            for flag in token[1:]:
                if flag == "o" and index < len(tokens):
                    long.add(tokens[index])
                    index += 1
                else:
                    short.add(flag)
    return short, long


def test_verifier_sets_exactly_the_intended_shell_options() -> None:
    """Check that the verifier enables only the intended shell options.

    Checking only that errexit is absent would also pass a verifier with no
    `set` options at all. Both of the others earn their place: without nounset an
    unset variable expands to empty and a comparison can succeed against nothing,
    and without pipefail a failing stage of a pipeline is invisible.
    """
    short, long = _shell_options(_verifier_code())
    assert "u" in short, "nounset is off; an unset variable expands to empty and can score a wrong answer"
    assert "pipefail" in long, "pipefail is off; a failing stage of a pipeline would go unnoticed"
    assert "e" not in short, (
        "errexit is on; aborting before reward.json is written turns a legitimate 0 into a missing metric"
    )


def test_verifier_keeps_its_reward_hacking_guards() -> None:
    """Check that the verifier keeps its safeguards against reward hacking."""
    code = _verifier_code()

    assert "tr -d" not in code, "tr -d '\\r' deletes every CR, collapsing sum=4<CR>2 into a passing sum=42"
    assert "cmp -s" in code, "whole-file compare; command substitution strips trailing newlines"
    assert "refusing to score" in code, "must fail closed when the expected fixture is unreadable"
    assert '[ -L "$OUTPUT" ]' in code, (
        "the agent owns /app/artifacts, so without a -L check it can point output.txt at "
        "the expected fixture and have the answer key compared against itself"
    )


def test_verifier_rejects_a_symlinked_output_before_reading_it() -> None:
    """Check that the verifier rejects a symlink before reading the output.

    A `-L` test placed after `-f` never runs: `-f` follows the link, finds a regular
    file at the other end, and scores it.
    """
    code = _verifier_code()
    branches = [line for line in code.splitlines() if line.lstrip().startswith(("if ", "elif "))]
    symlink_at = next((i for i, line in enumerate(branches) if '-L "$OUTPUT"' in line), None)
    regular_at = next((i for i, line in enumerate(branches) if '-f "$OUTPUT"' in line), None)
    assert symlink_at is not None, "verifier must test for a symlinked output"
    assert regular_at is not None, "verifier must still test for a regular output file"
    assert symlink_at < regular_at, (
        "the -L branch must precede the -f branch, or it is dead code and the symlink-to-answer-key hack scores 1.0"
    )


def test_verifier_does_not_echo_answers() -> None:
    """Check that the verifier does not print answer values in its log."""
    code = _verifier_code()
    for forbidden in ('cat "$EXPECTED_NORM"', 'cat "$ACTUAL_NORM"'):
        assert forbidden not in code, f"{forbidden} publishes ground truth to the trial log"


def test_dockerfile_nooa_rev_matches_workspace() -> None:
    """Check that the task image uses the workspace's NOOA revision."""
    dockerfile_path = _SHARED / "Dockerfile"
    if not dockerfile_path.is_file():
        return  # Task 4 creates it.
    found = re.search(r"labs-OO-Agents\.git@([0-9a-f]{40})", dockerfile_path.read_text(encoding="utf-8"))
    assert found is not None, "Dockerfile must pin NOOA to an explicit revision"
    assert found.group(1) == _root_nooa_rev()


def test_task_image_runs_as_a_non_root_user() -> None:
    """Check that model-written task code does not run as root."""
    dockerfile = (_SHARED / "Dockerfile").read_text(encoding="utf-8")
    assert "USER smoke-agent" in dockerfile
    assert "useradd --uid 10001" in dockerfile
    assert "COPY --chown=smoke-agent:smoke-agent records.json" in dockerfile


def test_task_template_references_the_current_image() -> None:
    """Check that the template uses the current task image."""
    expected = _expected_tag()
    actual = tomllib.loads(_template_toml().read_text(encoding="utf-8"))["environment"]["docker_image"]
    assert actual == expected, (
        f"task template references {actual}, current content is {expected}. "
        "Run scripts/build_image.py after changing the Dockerfile or records.json."
    )


def test_task_template_carries_the_current_verifier() -> None:
    """Check that the template uses the canonical verifier."""
    canonical = (_SHARED / "test.sh").read_bytes()
    actual = (_template_toml().parent / "tests" / "test.sh").read_bytes()
    assert actual == canonical, "task template verifier is stale; copy dataset/_shared/test.sh into the template"


def test_the_task_template_carries_the_current_records() -> None:
    """Check that the task template uses the current records file.

    A trace holds the question and the agent's wrong answer, never the right one, so
    Eval Author cannot infer `<EXPECTED>` from it -- and an unfilled expectation scores
    0 for every agent, making a healthy run read as a failed repair. The records make
    the answer derivable.

    A second copy, so it needs a second guard: a drifted one would have Eval Author
    compute answers from records the container does not have.
    """
    template_records = _EXAMPLE_DIR / "dataset" / "task-template" / "records.json"
    if not template_records.is_file():
        return  # optional; only insight mode needs it
    assert template_records.read_bytes() == (_SHARED / "records.json").read_bytes(), (
        f"{template_records} has drifted from the canonical records; copy dataset/_shared/records.json into the template"
    )


def test_task_template_has_an_empty_environment_dir() -> None:
    """Check that the template has the Harbor-required environment directory.

    ``TaskModel.is_valid_dir`` returns False when environment/ is absent, and a
    dataset whose tasks all fail that check loads with *zero tasks* rather than
    raising -- so a missing directory looks like an empty dataset, not an error.
    ``[environment].docker_image`` only makes the Dockerfile inside it optional.

    A Dockerfile there would shadow the prebuilt image and reintroduce the
    per-task build the content-hash tag exists to avoid.
    """
    environment = _template_toml().parent / "environment"
    assert environment.is_dir(), "task template has no environment/; Harbor will not see rendered tasks"
    contents = {p.name for p in environment.iterdir()} - {".gitkeep"}
    assert not contents, f"task template environment must stay empty, found {sorted(contents)}"


def test_renderer_reproduces_the_curated_task_tree(tmp_path: Path) -> None:
    """Check that the compact manifest renders the exact checked-in fixture.

    The hash covers every rendered path and its bytes, so it moves whenever
    ``tasks.json`` or ``task-template/`` changes. That is intended -- an edit to
    either should be a deliberate, reviewed act -- but it means the digest has to
    be updated by hand, and a stale digest says nothing about *what* differs.
    """
    dataset = tmp_path / "dataset"
    shutil.copytree(_EXAMPLE_DIR / "dataset", dataset)
    rendered = _renderer().render(dataset)
    assert len(rendered) == 50
    actual = _tree_sha256(dataset / "groups")
    assert actual == _RENDERED_TASK_TREE_SHA256, (
        f"rendered task tree changed: expected {_RENDERED_TASK_TREE_SHA256}, got {actual}. "
        "If the manifest or template edit was intended, set _RENDERED_TASK_TREE_SHA256 to the "
        "value above after confirming the rendered tasks are correct."
    )


@functools.cache
def _builder() -> Any:
    """Import scripts/build_all_group.py by path; scripts/ is not a package.

    The exclusion list lives there, so the test reads it rather than repeating
    it -- a second copy would drift the moment a group is added or removed.
    """
    path = _EXAMPLE_DIR / "scripts" / "build_all_group.py"
    spec = importlib.util.spec_from_file_location("_smoke_build_all_group", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_excluded_groups_stay_out_of_the_combined_set(tmp_path: Path) -> None:
    """Check that excluded groups are not part of the combined scenario.

    Combining them leaves the full scenario with no reachable pass criterion, so
    an accidental re-inclusion has to fail loudly rather than just lower the score.
    """
    dataset = tmp_path / "dataset"
    shutil.copytree(_EXAMPLE_DIR / "dataset", dataset)
    _renderer().render(dataset)
    _builder().assemble(dataset)
    combined = dataset / "groups" / "_all"

    excluded_keys = {name.split("-")[0] for name in _builder().EXCLUDED_GROUPS}
    assert excluded_keys, "the exclusion list should not be empty; see build_all_group.py"
    present = {task.parent.name.split("-")[0] for task in combined.rglob("task.toml")}
    assert not (present & excluded_keys), (
        f"combined group contains excluded group(s) {sorted(present & excluded_keys)}; run scripts/build_all_group.py"
    )


def test_combined_group_matches_its_sources(tmp_path: Path) -> None:
    """Check that the combined scenario matches its source task groups.

    Rebuild with scripts/build_all_group.py after changing any group.
    """
    dataset = tmp_path / "dataset"
    shutil.copytree(_EXAMPLE_DIR / "dataset", dataset)
    _renderer().render(dataset)
    _builder().assemble(dataset)
    groups = dataset / "groups"
    combined = groups / "_all"

    builder = _builder()
    expected: dict[str, Path] = {}
    for group_name in builder.source_groups(dataset):
        group = groups / group_name
        key = builder.group_key(group_name)
        for split in ("train", "validation"):
            for task in sorted((group / split).iterdir()):
                if (task / "task.toml").is_file():
                    expected[f"{split}/{key}-{task.name}"] = task

    actual = {f"{t.parent.parent.name}/{t.parent.name}": t.parent for t in combined.rglob("task.toml")}
    assert set(actual) == set(expected), (
        "combined group is stale; run scripts/build_all_group.py. "
        f"missing={sorted(set(expected) - set(actual))} unexpected={sorted(set(actual) - set(expected))}"
    )
    for rel, src in expected.items():
        for name in ("instruction.md", "task.toml", "tests/expected.txt"):
            assert (actual[rel] / name).read_bytes() == (src / name).read_bytes(), (
                f"combined {rel}/{name} differs from its source; run scripts/build_all_group.py"
            )


def test_every_shipped_config_validates() -> None:
    """A shipped config the schema rejects fails here, not minutes into a run.

    This refactor renamed run-config keys. `main` still carries the old spelling, so
    every merge re-introduces it, and the failure surfaces only after the sandbox, the
    image build and a 271-package resolve have already happened.

    The two files need *different* migrations, which is why this is a test rather than a
    one-time fix: `short.yaml` had the convergence check off, so its terminator becomes
    null; `full.yaml` had it on, so the key is dropped and the terminator keeps its
    default. Translating both the same way silently disables the one thing the combined
    scenario exists to exercise.
    """
    import yaml
    from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig

    configs = sorted((_EXAMPLE_DIR / "configs").glob("*.yaml"))
    assert configs, "no shipped configs found; the glob is wrong"

    for path in configs:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        EvolutionaryOptimizerConfig(**data)  # raises with the offending key named


def test_the_combined_scenario_keeps_its_terminator() -> None:
    """`full.yaml` is the only scenario that exercises early stopping.

    Pinned separately from the validation check above because the mistake it guards
    against -- turning the terminator off while migrating the key -- produces a config
    that still validates.
    """
    import yaml
    from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig

    full = EvolutionaryOptimizerConfig(
        **(yaml.safe_load((_EXAMPLE_DIR / "configs" / "full.yaml").read_text(encoding="utf-8")) or {})
    )
    short = EvolutionaryOptimizerConfig(
        **(yaml.safe_load((_EXAMPLE_DIR / "configs" / "short.yaml").read_text(encoding="utf-8")) or {})
    )

    assert full.terminator is not None, "the combined scenario lost the terminator it exists to test"
    assert short.terminator is None, "the per-group gates want a fixed round count, not early stopping"
