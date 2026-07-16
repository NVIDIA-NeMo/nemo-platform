# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""`testbed` — a test runner for the insights analysis workflow (maintainer tooling).

    uv run python -m testbed list
    uv run python -m testbed doctor [<name>]
    uv run python -m testbed run <name> [--base URL] [--set KEY=VALUE ...]                     # benchmark: produce traces + record the run
    uv run python -m testbed analyze <name> [--update-insights] [--base URL] [--platform-root PATH]  # reproducible default: restore the subject's pinned state, then analyze
    uv run python -m testbed analyze <name> --state (state-vN | FILE)                          # same, against another published state or a local bundle file
    uv run python -m testbed analyze <name> --live [--since S] [-v] [--set KEY=VALUE ...]      # analyze the platform's live traces (no restore)
    uv run python -m testbed snapshot <subject> [...] [-o FILE] [--base URL] [--since S]       # export subject workspaces (read API) into a state bundle
    uv run python -m testbed restore (FILE | --state state-vN) [--base URL] [--platform-root PATH]  # re-ingest an export bundle (additive, fixture workspaces)
    uv run python -m testbed roundtrip FILE [--base URL] [--platform-root PATH]                # mint-time fidelity guard: re-ingest into scratch, re-export, diff
    uv run python -m testbed publish FILE (--base URL | --no-verify) [--reason TEXT] [--platform-root PATH]  # mint the next state-v<N> from a candidate bundle and catalog it (guard first, or skip out loud)

Bare `analyze <subject>` is a fully reproducible run: the subject's pinned state
(from `[subjects]` in testbed/state.lock) is restored onto the local platform
(http://localhost:8080) and analyzed. Every deviation is one explicit flag:
`--state` picks another state, `--live` skips the restore and reads the live
platform, and `--base URL` retargets any command's platform (restore/analyze
target; run/snapshot/`analyze --live` source, replacing the stanza base_url).

Export bundles (`kind: testbed-export`) restore by re-ingesting through the real
APIs into fixture-scoped workspaces (`<ws>-<ref>` for published refs,
`<ws>-<sha256[:8]>` for local files) — additive, idempotent, and healing.
`restore --into WORKSPACE` is the direct alternative: it requires a fresh,
empty target and is not idempotent into a populated workspace. Legacy tar
bundles (state-v1..v5) are restorable only from a pre-migration checkout; see
testbed/README.md.

This drives the analyst (`nemo insights analyze`) against registered subjects; it is not
the product CLI and is not shipped in the wheel.
"""

import argparse
import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from testbed import artifact, publish, reingest, release
from testbed.adapters import build_adapter
from testbed.export import EPOCH
from testbed.registry import Subject, load_registry
from testbed.runstore import load_run, save_run
from testbed.summary import render_summary_md
from testbed.timeparse import parse_since

HERE = Path(__file__).parent
REGISTRY_PATH = HERE / "testbeds.toml"
TMP = HERE / "tmp"
ENV_PATH = HERE / ".env"
LOCAL_URL = artifact.LOCAL_URL  # the local NeMo Platform (the default restore/analyze target)


def _load_dotenv(path: Path = ENV_PATH) -> None:
    """Load ``KEY=VALUE`` lines from a .env file into ``os.environ``.

    A no-op if the file is absent. Existing environment variables win
    (``setdefault``), so a real shell value overrides the file per run. Lines
    that are blank, ``#`` comments, or have no ``=`` are skipped; an optional
    ``export`` prefix and surrounding quotes are stripped.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        # naive: trims surrounding quotes, not paired-quote matching (matches python-dotenv's laxity)
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _doctor(subjects: dict[str, Subject], name: str | None) -> None:
    """Print a readiness checklist for one subject (or all): what's set up, what's not."""
    names = [name] if name else sorted(subjects)
    for subject_name in names:
        subject = subjects.get(subject_name)
        if subject is None:
            print(f"✗ {subject_name}: unknown subject")
            continue
        unmet: list[str] = []
        if not os.environ.get("INFERENCE_API_KEY"):
            unmet.append("env INFERENCE_API_KEY (analyst key, in testbed/.env)")
        if shutil.which("gh") is None:
            unmet.append("gh CLI (needed for pinned/--state analyze; https://cli.github.com)")
        unmet += build_adapter(subject).check()
        if unmet:
            print(f"✗ {subject_name} ({subject.type}) — needs:")
            for item in unmet:
                print(f"    - {item}")
        else:
            print(f"✓ {subject_name} ({subject.type}) — ready: uv run python -m testbed analyze {subject_name} --live")


def _with_base(subject: Subject, base: str | None) -> Subject:
    """Rebuild *subject* pointed at *base* (the uniform ``--base`` override); unchanged when None."""
    if base is None:
        return subject
    return Subject(subject.name, subject.type, {**subject.config, "base_url": base})


def _local_source(args: argparse.Namespace) -> str | None:
    """The local bundle file given on the command line, if any.

    ``restore`` takes it as the positional ``FILE`` (its ``--state`` is
    refs-only); ``analyze``'s ``--state`` doubles as the file source when its
    value names an existing FILE (``is_file``, so a directory that happens to
    carry a ref's name falls through to ref resolution) — checked before the
    ``state-v<N>`` pattern, so a ref-shaped filename still restores the file.
    """
    if file := getattr(args, "file", None):
        return str(file)
    state = getattr(args, "state", None)
    if args.cmd == "analyze" and state and Path(state).is_file():
        return state
    return None


def _resolve_bundle(args: argparse.Namespace) -> tuple[Path, str, str]:
    """The state bundle to restore, as ``(bundle_path, label, fixture_suffix)``.

    A local file source is used in place: *label* is its filename plus a
    ``(local file <digest8>)`` marker — so a provenance line can never pass a
    local file off as a published ref — and the fixture-workspace *suffix* is
    that content digest. A file whose name collides with the ref pattern
    shadows the published ref; the file wins, with a printed note. Otherwise
    the ref is resolved — an explicit ``--state`` verbatim, else the subject's
    ``state.lock`` pin (``analyze`` carries a subject in ``args.name``;
    ``restore`` is subject-agnostic, so its lock path hard-exits in
    resolve_state) — and downloaded into TMP/downloads, with the ref serving
    as both *label* and *suffix* (e.g. ``state-v6``). A path-shaped value
    (contains ``/`` or ends in ``.tar.zst``) that names no file exits as a
    missing file, not as resolve_state's malformed-ref message. *label* is
    what callers write into the step-summary provenance line.
    """
    if local_file := _local_source(args):
        path = Path(local_file)
        if not path.is_file():
            sys.exit(f"no such bundle file: {path}")
        if args.cmd == "analyze" and re.fullmatch(r"state-v\d+", path.name):
            print(f"note: '{path.name}' is a local file shadowing a published ref name — analyzing the file")
        digest = reingest.bundle_digest(path)
        return path, f"{path.name} (local file {digest})", digest
    state = getattr(args, "state", None)
    if (
        state
        and not re.fullmatch(r"state-v\d+", state)
        and not Path(state).is_file()
        and ("/" in state or state.endswith(".tar.zst"))
    ):
        sys.exit(f"no such bundle file: {state}")
    ref = release.resolve_state(
        state,
        subject=getattr(args, "name", None),
        lock_path=HERE / "state.lock",
    )
    print(f"resolved state ref: {ref}")
    return release.download_ref(ref, TMP / "downloads"), ref, ref


def _read_bundle_manifest(bundle: Path) -> dict:
    """Peek at a bundle's ``state/manifest.json`` without a full extract.

    Each failure mode is loud and distinct: a missing file or an unreadable
    archive (corrupt/truncated download) exits carrying tar's own error; a
    readable tar without a parseable ``state/manifest.json`` exits as "not a
    testbed bundle". A manifest whose ``kind`` isn't ``testbed-export`` (legacy
    state-v1..v5 tars carry a manifest with ``state_ref`` but no ``kind``) is
    the callers' case — this returns the parsed manifest and each call site
    keeps its own legacy-bundle wording.
    """
    if not bundle.is_file():
        sys.exit(f"no such bundle file: {bundle}")

    def _tar_error(proc: subprocess.CompletedProcess) -> str:
        reason = (proc.stderr.strip().splitlines() or ["tar failed"])[0]
        return f"could not read bundle {bundle.name}: {reason} (corrupt or truncated? re-download or re-mint)"

    listing = subprocess.run(["tar", "--zstd", "-tf", str(bundle)], capture_output=True, text=True)
    if listing.returncode != 0:
        sys.exit(_tar_error(listing))
    if "state/manifest.json" not in listing.stdout.splitlines():
        sys.exit(f"{bundle.name} is not a testbed bundle (no state/manifest.json inside)")
    proc = subprocess.run(
        ["tar", "--zstd", "-xOf", str(bundle), "state/manifest.json"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.exit(_tar_error(proc))
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"{bundle.name} is not a testbed bundle (state/manifest.json is not valid JSON)")


def _restore_export_bundle(
    bundle: Path,
    *,
    base_url: str,
    suffix: str,
    platform_root: str | None,
    tmp_dir: Path,
    backup_dir: Path | None = None,
    into: str | None = None,
) -> tuple[dict, dict[str, str], list[str]]:
    """Re-ingest an export bundle into fixture workspaces.

    Returns ``(manifest, workspace_map, seeded)`` where *seeded* names the
    run-record files the bundle left in ``tmp_dir`` (callers use it to refuse
    analyzing a subject the bundle carries no run record for).

    The default fixture-scoped path is additive, idempotent, and healing
    (``reingest.ingest_bundle`` guards on per-collection counts). Direct
    ``--into`` restores require a fresh, empty target and are not idempotent
    into populated workspaces. Both warn on stale bundles. The catalog
    inversion is loaded up front so a missing nemo-platform checkout fails
    before any extraction or network I/O. The bundle's ``tmp/`` run records
    are copied beside the local ones (clobbered locals are backed up into
    *backup_dir*, the caller's per-invocation destination); insights never
    travel in bundles, so nothing else lands in ``tmp_dir``.
    """
    catalog = reingest.load_catalog(reingest.resolve_platform_root(platform_root))
    TMP.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP) as tmp:
        subprocess.run(["tar", "--zstd", "-xf", str(bundle), "-C", tmp], check=True)
        state = Path(tmp) / "state"
        manifest = json.loads((state / "manifest.json").read_text(encoding="utf-8"))
        workspace_map = (
            reingest.explicit_workspace_map(manifest["workspaces"], into)
            if into is not None
            else reingest.fixture_workspace_map(manifest["workspaces"], suffix)
        )
        outcome = reingest.ingest_bundle(
            base_url,
            state / "export",
            manifest,
            workspace_map=workspace_map,
            catalog=catalog,
            require_empty=into is not None,
        )
        # seed_records must run inside this `with` block: it copies the bundle's
        # records out of state/tmp (under the tempdir) before teardown.
        seed_message, seeded = artifact.seed_records(state / "tmp", tmp_dir, backup_dir=backup_dir)
        print(seed_message)
    ingested = sum(c["spans"]["ingested"] for c in outcome.values())
    skipped = sum(c["spans"]["skipped"] for c in outcome.values())
    targets = ", ".join(sorted(c["workspace"] for c in outcome.values()))
    print(f"✓ restored: {ingested} spans ingested, {skipped} skipped — workspaces: {targets}")
    return manifest, workspace_map, seeded


def _remap_record(record: dict, workspace_map: dict[str, str], *, base_url: str) -> dict:
    """Point a restored run record at the fixture workspaces on the target platform.

    Remaps every benchmark workspace field an adapter's analyze step reads
    (``realistic_workspace`` and its ``oracle_workspace`` twin)
    and pins ``base_url`` to the platform the bundle was just restored onto
    (the record's own value points at wherever produce originally ran).
    """
    remapped = dict(record)
    for key in ("realistic_workspace", "oracle_workspace"):
        value = remapped.get(key)
        if value and value in workspace_map:
            remapped[key] = workspace_map[value]
    remapped["base_url"] = base_url
    return remapped


def _ensure_fresh_insights(subject_name: str, update: bool, *, backup_dir: Path | None = None) -> None:
    """Fresh-by-default analyze: move any prior local insights YAML out of the analyst's path.

    The analyst backend picks up ``testbed/tmp/insights_<subject>.yaml`` as its
    prior-insight seed purely by presence, so a fresh run must take the file off
    that path — it moves into *backup_dir* (the caller's per-invocation
    ``tmp/backup-<UTC stamp>/``; never deleted) with one printed line saying so.
    ``--update-insights`` (*update*) leaves it in place to seed the analyst with
    priors. Runs for EVERY analyze mode (pinned, ``--state``, ``--live``),
    before the analyst.
    """
    if update:
        return
    name = f"insights_{subject_name}.yaml"
    if not (TMP / name).exists():
        return
    backup_dir = artifact.backup_records(TMP, [name], backup_dir=backup_dir)
    print(
        f"fresh insights: moved prior {name} to {backup_dir.name}/ "
        "(use --update-insights to seed the analyst with priors)"
    )


def _analysis_workspace(subject: Subject, record: dict | None) -> str | None:
    """The one workspace this analysis reads (None when it can't be known yet).

    Intake reads the subject config's ``workspace`` (already remapped onto the
    subject in pinned/state mode); benchmark reads the record's
    ``realistic_workspace``. A missing record yields None.
    """
    if subject.type == "intake":
        return str(subject.config.get("workspace") or "") or None
    if record is None:
        return None
    return str(record.get("realistic_workspace") or "") or None


def _warn_insights_workspace_mismatch(subject_name: str, workspace: str | None) -> None:
    """--update-insights sanity check: warn when the kept priors can't be seen.

    The analyst backend scopes the local YAML's prior insights by their
    ``workspace`` field, so priors kept from another mode (e.g. a live run's,
    before a pinned analyze that runs under fixture workspaces) silently match
    nothing — the analyst would skip every update and re-create each insight.
    When ZERO records match this analysis's workspace, print one prominent
    warning. Never rewrites the file: the priors stay valid for their own
    workspace.
    """
    path = TMP / f"insights_{subject_name}.yaml"
    if workspace is None or not path.is_file():
        return
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return  # best-effort check: not the backend's shape, so nothing to compare
    carried = sorted({str(r.get("workspace")) for r in raw.get("insights", []) if r.get("workspace")})
    if not carried or workspace in carried:
        return
    print(
        f"warning: --update-insights: insights_{subject_name}.yaml carries workspace(s) "
        f"{', '.join(carried)} but this analysis runs under '{workspace}' — "
        "priors will be invisible and updates will be skipped"
    )


def _run_roundtrip(bundle: Path, base: str, platform_root: str | None) -> None:
    """Round-trip fidelity guard: re-ingest *bundle* into scratch workspaces, re-export, diff.

    ``sys.exit``s on any mismatch (or on a non-export/corrupt bundle), so
    callers only continue past this on a fully faithful round trip. Shared by
    the ``roundtrip`` subcommand and ``publish --base`` (the mint-time gate).
    """
    if _read_bundle_manifest(bundle).get("kind") != "testbed-export":
        sys.exit(f"roundtrip: {bundle.name} is not a testbed-export bundle — nothing to guard")
    # Load the inversion catalog up front so a missing nemo-platform checkout
    # fails before any extraction or network I/O (same discipline as restore).
    catalog = reingest.load_catalog(reingest.resolve_platform_root(platform_root))
    TMP.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP) as tmp:
        subprocess.run(["tar", "--zstd", "-xf", str(bundle), "-C", tmp], check=True)
        state = Path(tmp) / "state"
        manifest = json.loads((state / "manifest.json").read_text(encoding="utf-8"))
        mismatches = reingest.roundtrip_diff(
            base,
            state / "export",
            manifest,
            scratch_prefix="scratch-rt-",
            catalog=catalog,
            content_key=reingest.bundle_digest(bundle),
        )
    if mismatches:
        for line in mismatches:
            print(line)
        sys.exit(
            f"✗ round-trip guard: {len(mismatches)} mismatch(es) — "
            f"{bundle.name} does not restore with full read-API fidelity"
        )
    print(f"✓ round-trip guard: {bundle.name} restores with full read-API fidelity")


def _coerce_override(subject: Subject, key: str, raw: str) -> object:
    """Coerce a ``--set`` value to the type of the stanza's existing value for *key*.

    The stanza-type rule: a key already in the merged config keeps its type —
    bool takes only ``true``/``false`` (case-insensitive), int/float must parse
    (hard exit naming the key otherwise), str stays verbatim. A key absent from
    the stanza is allowed: bare ``true``/``false`` literals (case-insensitive)
    always become booleans — there is no stanza type to preserve, and a
    ``"false"`` STRING is truthy — while everything else stays a verbatim
    string (no guessing). bool is checked before int: it's an int subclass.
    """
    if key not in subject.config:
        lowered = raw.strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        return raw
    current = subject.config[key]
    if isinstance(current, bool):
        lowered = raw.strip().lower()
        if lowered not in ("true", "false"):
            sys.exit(f"--set {key} expects true or false, got '{raw}'")
        return lowered == "true"
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            sys.exit(f"--set {key} expects an integer, got '{raw}'")
    if isinstance(current, float):
        try:
            return float(raw)
        except ValueError:
            sys.exit(f"--set {key} expects a number, got '{raw}'")
    return raw


def _apply_overrides(subject: Subject, sets: list[str]) -> Subject:
    """Apply repeatable ``--set key=value`` overrides onto a subject's config.

    Each value is coerced to the type its key already has in the stanza
    (:func:`_coerce_override`); keys new to the stanza stay strings.
    """
    if not sets:
        return subject
    cfg = dict(subject.config)
    for item in sets:
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or not key:
            sys.exit(f"--set expects key=value, got '{item}'")
        cfg[key] = _coerce_override(subject, key, value)
    return Subject(subject.name, subject.type, cfg)


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(
        prog="testbed",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List configured testbed subjects.")
    p_ins = sub.add_parser(
        "analyze",
        help="Generate Insights for a subject (default: restore its pinned state onto the "
        "local platform, then analyze — fully reproducible).",
    )
    p_ins.add_argument("name", help="Subject name from testbeds.toml.")
    p_ins_mode = p_ins.add_mutually_exclusive_group()
    p_ins_mode.add_argument(
        "--live",
        action="store_true",
        help="Analyze the platform's live traces instead of a pinned state (no restore; "
        "target = --base, else the stanza base_url).",
    )
    p_ins_mode.add_argument(
        "--state",
        default=None,
        metavar="STATE",
        help="Analyze a specific state instead of the pinned one: a published ref (state-vN) or a local bundle file.",
    )
    p_ins.add_argument(
        "--since",
        help="Trace lower bound, --live only: Nd/Nh/Nm (days/hours/minutes) or ISO date "
        "(default: the stanza's since, else 30d; '' = epoch, no lower bound).",
    )
    p_ins.add_argument(
        "--base",
        default=None,
        help=f"Target platform URL (default: {LOCAL_URL}; with --live: replaces the stanza "
        "base_url and the recorded run's).",
    )
    p_ins.add_argument("--verbose", "-v", action="store_true")
    p_ins.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a subject config key (repeatable), e.g. --set num_tasks=2. Values take the "
        "stanza key's type (int/float/bool true|false); keys new to the stanza stay strings.",
    )
    p_ins.add_argument(
        "--summary-md",
        help="Append a markdown summary of the insights to this file (e.g. $GITHUB_STEP_SUMMARY).",
    )
    p_ins.add_argument(
        "--update-insights",
        dest="update_insights",
        action="store_true",
        help="run against the existing local insights (prod-like update flow: updates them and adds new ones); "
        "default is a fresh start with priors moved to backup.",
    )
    p_ins.add_argument(
        "--platform-root",
        default=None,
        help="nemo-platform checkout for the span-attribute-catalog inversion "
        "(default: $NMP_PLATFORM_ROOT, the CI sibling checkout, then ~/workstation/nemo-platform).",
    )
    p_snap = sub.add_parser(
        "snapshot",
        help="Export subject workspaces from the intake read API into a portable bundle.",
    )
    p_snap.add_argument("names", nargs="*", metavar="subject", help="Subject names from testbeds.toml.")
    p_snap.add_argument(
        "-o",
        "--out",
        default=None,
        help="Output bundle path (default: testbed/tmp/snapshot-<UTC yyyymmdd-hhmmss>.tar.zst).",
    )
    p_snap.add_argument(
        "--base",
        default=None,
        help="Export from this platform URL instead of each subject's stanza base_url "
        "(overrides every listed subject, so stanzas need not agree).",
    )
    p_snap.add_argument(
        "--since",
        help="Span lower bound: Nd/Nh/Nm (days/hours/minutes) or ISO date (default: epoch — export everything).",
    )
    p_snap.add_argument(
        "--subjects-json",
        default=None,
        help="CI sugar: JSON array of subject names, e.g. '[\"tau2-airline\"]'.",
    )
    p_res = sub.add_parser(
        "restore",
        help="Restore a state bundle by re-ingesting it additively into fixture workspaces "
        "(legacy tar bundles, state-v1..v5, need a pre-migration checkout).",
    )
    # No pinned default here: state.lock pins are per-subject and restore is
    # subject-agnostic — use `analyze <subject>` for the pinned loop.
    p_res.add_argument("file", nargs="?", help="Local state bundle file to restore.")
    p_res.add_argument(
        "--state",
        default=None,
        metavar="STATE-VN",
        help="Restore a published state ref (state-vN); local files go through the positional FILE. "
        "Pins are per-subject: for the pinned state, use `analyze <subject>` instead.",
    )
    p_res.add_argument(
        "--into",
        default=None,
        metavar="WORKSPACE",
        help="Restore a single-workspace bundle directly into this workspace instead of the "
        "fixture-scoped <ws>-<ref> default. Requires a fresh, empty target and is "
        "not idempotent into a populated workspace.",
    )
    p_res.add_argument(
        "--base",
        default=None,
        help=f"Target platform URL for the re-ingest (default: {LOCAL_URL}).",
    )
    p_res.add_argument(
        "--platform-root",
        default=None,
        help="nemo-platform checkout for the span-attribute-catalog inversion "
        "(default: $NMP_PLATFORM_ROOT, the CI sibling checkout, then ~/workstation/nemo-platform).",
    )
    p_rt = sub.add_parser(
        "roundtrip",
        help="Mint-time fidelity guard: re-ingest an export bundle into scratch workspaces, "
        "re-export, and diff (non-zero exit on any mismatch).",
    )
    p_rt.add_argument("file", help="Export bundle (tar.zst) to check.")
    p_rt.add_argument(
        "--base",
        default=None,
        help=f"Target platform URL for the scratch re-ingest (default: {LOCAL_URL}).",
    )
    p_rt.add_argument(
        "--platform-root",
        default=None,
        help="nemo-platform checkout for the span-attribute-catalog inversion "
        "(default: $NMP_PLATFORM_ROOT, the CI sibling checkout, then ~/workstation/nemo-platform).",
    )
    p_pub = sub.add_parser(
        "publish",
        help="Mint the next state-v<N> from a candidate export bundle: upload it to the "
        "testbed-state release and prepend its fixture-catalog row.",
    )
    p_pub.add_argument("file", help="Candidate export bundle (tar.zst).")
    p_pub.add_argument(
        "--reason",
        default=None,
        help="Why this fixture exists (one line for the release catalog; REASON env fallback).",
    )
    p_pub_verify = p_pub.add_mutually_exclusive_group()
    p_pub_verify.add_argument(
        "--base",
        default=None,
        help="Platform URL to run the round-trip fidelity guard against before minting.",
    )
    p_pub_verify.add_argument(
        "--no-verify",
        action="store_true",
        help="Mint without running the round-trip guard (only when the guard already ran, e.g. as its own CI step).",
    )
    p_pub.add_argument(
        "--platform-root",
        default=None,
        help="nemo-platform checkout for the --base round-trip guard's span-attribute-catalog inversion "
        "(default: $NMP_PLATFORM_ROOT, the CI sibling checkout, then ~/workstation/nemo-platform).",
    )
    p_doc = sub.add_parser("doctor", help="Check prerequisites for a subject (or all).")
    p_doc.add_argument("name", nargs="?", help="Subject name; omit to check every subject.")
    p_run = sub.add_parser(
        "run",
        help="Produce traces for a subject (benchmark: run tau2 + ingest), then record the run.",
    )
    p_run.add_argument("name", help="Subject name from testbeds.toml.")
    p_run.add_argument(
        "--base",
        default=None,
        help=f"Target platform URL instead of the stanza base_url (e.g. {LOCAL_URL}).",
    )
    p_run.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a subject config key (repeatable), e.g. --set num_tasks=2. Values take the "
        "stanza key's type (int/float/bool true|false); keys new to the stanza stay strings.",
    )
    args = parser.parse_args()

    if not REGISTRY_PATH.exists():
        sys.exit(f"No testbed registry found at {REGISTRY_PATH}.")
    subjects = load_registry(REGISTRY_PATH)
    if args.cmd == "list":
        print("Testbeds:", ", ".join(sorted(subjects)) or "(none)")
        return
    if args.cmd == "doctor":
        _doctor(subjects, args.name)
        return

    if args.cmd == "run":
        subject = subjects.get(args.name)
        if subject is None:
            sys.exit(f"Unknown testbed '{args.name}'. Available: {', '.join(sorted(subjects)) or '(none)'}")
        subject = _with_base(subject, args.base)
        subject = _apply_overrides(subject, args.sets)
        record = asyncio.run(build_adapter(subject).produce())
        TMP.mkdir(parents=True, exist_ok=True)
        save_run(TMP / f"{args.name}.run.json", record)
        ws_line = f"realistic ws '{record['realistic_workspace']}'"
        if record.get("oracle_workspace"):
            ws_line += f" + oracle ws '{record['oracle_workspace']}'"
        print(
            f"✓ recorded run '{record['agent']}' ({ws_line}) — analyze with: "
            f"uv run python -m testbed analyze {args.name} --live"
        )
        return

    if args.cmd == "snapshot":
        names = list(args.names)
        if args.subjects_json:
            try:
                extra = json.loads(args.subjects_json)
            except json.JSONDecodeError as exc:
                sys.exit(f"--subjects-json is not valid JSON: {exc}")
            if not isinstance(extra, list):
                sys.exit("--subjects-json must be a JSON array of subject names")
            names += [str(n) for n in extra]
        names = list(dict.fromkeys(names))  # de-dupe, order preserved
        if not names:
            sys.exit("snapshot: give at least one subject (positional or --subjects-json)")
        unknown = [n for n in names if n not in subjects]
        if unknown:
            sys.exit(f"Unknown testbed(s): {', '.join(unknown)}. Available: {', '.join(sorted(subjects)) or '(none)'}")
        # parse_since exits on garbage HERE — before any client construction or network I/O.
        since = parse_since(args.since)
        out = (
            Path(args.out)
            if args.out
            else TMP / (f"snapshot-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}.tar.zst")
        )
        # --base replaces every listed subject's source URL, so snapshot_export's
        # all-stanzas-must-agree check trivially holds; without it the stanza
        # agreement (or disagreement) stands as-is.
        result = artifact.snapshot_export(
            [_with_base(subjects[n], args.base) for n in names],
            out,
            TMP,
            since=since,
        )
        print(f"✓ snapshot: {result}")
        return

    if args.cmd == "restore":
        if (args.file is not None) + (args.state is not None) != 1:
            sys.exit(
                "restore: give exactly one of FILE or --state <state-vN> "
                "(state pins are per-subject — use `analyze <subject>` for the pinned loop)"
            )
        if args.file is not None and not args.file:
            # `restore ""` passes the arity check but names nothing; without this
            # it would fall through to ref resolution's subject-less lock lookup.
            sys.exit("restore: FILE must be a non-empty path")
        bundle_path, _label, suffix = _resolve_bundle(args)
        manifest = _read_bundle_manifest(bundle_path)
        if manifest.get("kind") != "testbed-export":
            sys.exit(
                f"restore: {bundle_path.name} is a legacy tar bundle (state-v1..v5) — "
                "restorable only from a pre-migration checkout; see testbed/README.md"
            )
        if args.into is not None:
            # Validate the direct target before catalog loading, extraction, or network I/O.
            reingest.explicit_workspace_map(manifest["workspaces"], args.into)
        _restore_export_bundle(
            bundle_path,
            base_url=args.base or LOCAL_URL,
            suffix=suffix,
            platform_root=args.platform_root,
            tmp_dir=TMP,
            into=args.into,
        )
        return

    if args.cmd == "roundtrip":
        _run_roundtrip(Path(args.file), args.base or LOCAL_URL, args.platform_root)
        return

    if args.cmd == "publish":
        bundle_path = Path(args.file)
        # Minting is immutable, so an unverified mint must be an explicit choice:
        # --base runs the round-trip guard here (sys.exits on mismatch, so a
        # failed guard can never mint); --no-verify skips it out loud.
        if args.base:
            _run_roundtrip(bundle_path, args.base, args.platform_root)
        elif args.no_verify:
            print(f"publish: skipping round-trip guard for {bundle_path.name} (--no-verify)")
        else:
            sys.exit(
                "publish: minting is immutable — verify first. Pass --base <platform> to run "
                "the round-trip guard against it, or --no-verify to mint unverified."
            )
        publish.publish(bundle_path, reason=args.reason)
        return

    # args.cmd == "analyze" — pinned/--state mode restores a bundle first; --live doesn't.
    subject = subjects.get(args.name)
    if subject is None:
        sys.exit(f"Unknown testbed '{args.name}'. Available: {', '.join(sorted(subjects)) or '(none)'}")
    if not args.live and args.since is not None:
        # For pinned/state analysis the lower bound is derived from the bundle's
        # manifest (min_start_time floored) — a user-supplied --since would be
        # silently ignored.
        sys.exit("--since only applies to --live; pinned/state analysis derives since from the bundle manifest")
    # Target platform: --base wins everywhere; without it, pinned/state mode
    # restores onto the local platform (reproducible default) and --live reads
    # the stanza's own base_url.
    subject = _with_base(subject, args.base if args.live else (args.base or LOCAL_URL))
    subject = _apply_overrides(subject, args.sets)
    if not os.environ.get("INFERENCE_API_KEY"):
        sys.exit("Set INFERENCE_API_KEY (NVIDIA Inference Gateway sk-... key) and re-run.")
    # One backup destination per invocation: the restore's clobber-backup and the
    # fresh-insights move both park files here, so a single analyze yields at most
    # one tmp/backup-<stamp>/ dir (created lazily, only if something moves).
    # Microseconds keep two invocations within the same second from sharing a dir.
    backup_stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = TMP / f"backup-{backup_stamp}"

    workspace_map: dict[str, str] = {}
    if args.live:
        label = "live"
        # `--since ''` explicitly means "no lower bound"; only fall back to the
        # stanza default (then the client-side 30d default, mirroring the read
        # API's implicit lookback — but pinned explicitly) when the flag is
        # absent (None), not when it's empty.
        if args.since == "":
            # parse_since('') returns None, and a None bound would let the read
            # API reapply its implicit 30d lookback — pin the epoch instead
            # (export.py's `since or EPOCH` discipline).
            since, origin = EPOCH, "--since (epoch — no lower bound)"
        elif args.since is not None:
            since, origin = parse_since(args.since), "--since"
        elif subject.config.get("since") is not None:
            since, origin = parse_since(subject.config.get("since")), "stanza"
        else:
            since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
            origin = "default 30d"
        print(f"since: {since.isoformat() if since else 'none'} ({origin})")
    else:
        if subject.type not in ("benchmark", "intake"):
            # Only benchmark/intake subjects own a workspace a bundle can carry.
            # This must exit HERE, before the membership check would call into
            # workspace scoping — artifact.workspaces_for_subject's exit for
            # these types is worded for snapshot, not analyze.
            sys.exit(
                f"analyze: subject '{args.name}' has type '{subject.type}' — bundle-based "
                f"analysis supports benchmark and intake subjects; use `analyze {args.name} --live`"
            )
        bundle_path, label, suffix = _resolve_bundle(args)
        peek = _read_bundle_manifest(bundle_path)
        if peek.get("kind") != "testbed-export":
            sys.exit(
                f"analyze: {bundle_path.name} is a legacy tar bundle (state-v1..v5) — "
                "restorable only from a pre-migration checkout; see testbed/README.md"
            )
        # Membership check BEFORE restoring: the one workspace the analysis reads
        # (benchmark: the realistic workspace; intake: the workspace) must be in
        # the bundle, or the analyst would read an empty fixture. The oracle twin
        # is never required — analysis doesn't read it — but when the bundle
        # carries it, the restore below still ingests it (restore takes every
        # manifest workspace).
        workspace = str(subject.config.get("workspace") or "")
        if not workspace:
            sys.exit(f"analyze: subject '{args.name}' has no workspace configured")
        bundle_workspaces = [str(ws) for ws in peek.get("workspaces") or []]
        if workspace not in bundle_workspaces:
            bundle_subjects = ", ".join(str(s) for s in peek.get("subjects") or []) or "(unknown)"
            sys.exit(
                f"analyze: subject '{args.name}' needs workspace '{workspace}', "
                f"but bundle {label} carries only {', '.join(bundle_workspaces) or '(none)'} "
                f"(subjects: {bundle_subjects})"
            )
        manifest, workspace_map, seeded = _restore_export_bundle(
            bundle_path,
            base_url=str(subject.config["base_url"]),
            suffix=suffix,
            platform_root=args.platform_root,
            tmp_dir=TMP,
            backup_dir=backup_dir,
        )
        if subject.type != "intake" and f"{args.name}.run.json" not in seeded:
            # Falling back to a pre-existing local record would be a silent trap: its
            # stale experiment_id filters every restored trace out of the analysis.
            sys.exit(
                f"analyze: bundle {label} carries no run record for subject '{args.name}' — "
                "it cannot be analyzed from this bundle"
            )
        source_ws = str(subject.config.get("workspace") or "")
        if source_ws in workspace_map:
            # Intake subjects analyze the workspace from their config stanza (not the
            # run record), so the fixture remap must land on the subject too.
            subject = Subject(subject.name, subject.type, {**subject.config, "workspace": workspace_map[source_ws]})
        # Explicit lower bound derived from the bundle (min_start_time floored): the
        # read API injects a 30-day default lookback whenever `since` is absent, which
        # would silently hide restored spans older than a month.
        since = reingest.manifest_since(manifest)

    if args.summary_md:
        # Written before the insights rendering below — right after any restore
        # completes — so the summary records which state (or `live`) the
        # analysis that follows actually ran against.
        with Path(args.summary_md).open("a", encoding="utf-8") as fh:
            fh.write(f"### analyze @ {label} ({args.name})\n")

    # Fresh by default, in every mode: a prior insights YAML on the analyst's
    # path would silently seed this run — move it aside unless --update-insights.
    _ensure_fresh_insights(args.name, args.update_insights, backup_dir=backup_dir)
    out = TMP / f"insights_{args.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    record = load_run(TMP / f"{args.name}.run.json")
    if not args.live and record is not None:
        # The analyst must read the fixture workspaces on the platform the bundle
        # was just restored onto, not the workspaces/URL the record was minted with.
        record = _remap_record(record, workspace_map, base_url=str(subject.config["base_url"]))
        if subject.type == "benchmark":
            # The record's analysis workspace must be one the restore just wrote,
            # or the analyst reads an empty (or wrong) fixture. Intake reads its
            # workspace from config, not the record.
            analysis_ws = str(record.get("realistic_workspace") or "")
            if analysis_ws and analysis_ws not in workspace_map.values():
                sys.exit(
                    f"bundle record for '{args.name}' points at workspace '{analysis_ws}' "
                    f"which is not among the restored workspaces "
                    f"({', '.join(sorted(workspace_map.values()))}) — "
                    "the bundle was minted with a mismatched record"
                )
    elif args.live and args.base is not None and record is not None:
        # --live --base must be honest end-to-end: benchmark analysis reads the
        # record's base_url (minted at run time), not the stanza's.
        record = {**record, "base_url": args.base}
    if args.update_insights:
        # The kept priors are workspace-scoped inside the YAML; runs after the
        # remap (state mode) / record load (live) so it compares against the
        # workspace this analysis actually reads.
        _warn_insights_workspace_mismatch(args.name, _analysis_workspace(subject, record))
    adapter = build_adapter(subject)
    report = asyncio.run(adapter.analyze(record=record, since=since, verbose=args.verbose, out_path=out))
    print(report)
    print(f"\n✓ Insights written to {out}")
    if args.summary_md:
        with Path(args.summary_md).open("a", encoding="utf-8") as fh:
            fh.write(render_summary_md(out, args.name))
