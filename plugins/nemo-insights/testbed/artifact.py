# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Snapshot the platform's testbed state as portable export bundles.

Snapshot (capture) is a read-API export: :func:`snapshot_export` drains each
subject's workspaces through :mod:`testbed.export` into a JSONL bundle
(``kind: testbed-export``) — it works against any platform URL and never
touches ClickHouse directly.

Restore lives in :mod:`testbed.reingest`: an additive, idempotent re-ingest
into fixture-scoped workspaces through the real APIs. Legacy tar bundles
(state-v1..v5) are restorable only from a pre-migration checkout.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

import httpx
from testbed import export
from testbed.registry import Subject

LOCAL_URL = "http://localhost:8080"  # the local NeMo Platform (the default restore/analyze target)


def pick_records(tmp_dir: Path, subjects: list[str]) -> list[Path]:
    """The selected *subjects*' run records present in *tmp_dir* (sorted).

    Scoped by name (``<subject>.run.json``) so a bundle never captures another
    subject's records that happen to sit in the shared ``testbed/tmp``
    directory. Insight YAMLs never travel in bundles: insights are per-analyze
    output, not state (``analyze`` is fresh by default; ``--update-insights``
    seeds the analyst from the local file).
    """
    names = {f"{s}.run.json" for s in subjects}
    return sorted(p for p in (tmp_dir / n for n in names) if p.is_file())


# manifest key -> env var it is sourced from (CI produce job; parity with the old bundle.py)
_LINEAGE_ENV = {
    "nemo_platform_sha": "GITHUB_SHA",
    "tau2_bench_sha": "TAU2_BENCH_REF",
    "github_run_id": "GITHUB_RUN_ID",
    "num_tasks": "NUM_TASKS",
    "num_trials": "NUM_TRIALS",
    "judge_llm": "TAU2_JUDGE_LLM",
    "reason": "REASON",
}


def build_export_manifest(
    subjects: list[str],
    records: list[Path],
    stats: dict,
    *,
    source_url: str,
    platform_info: dict | None,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Export-bundle manifest; CI lineage fields are merged in only when their env vars are set.

    *stats* is :func:`testbed.export.export_workspaces`'s return value (per-collection
    counts + span time bounds). *platform_info* is :func:`fetch_platform_info`'s
    best-effort answer (None when the platform didn't say). Laptop snapshots (no CI
    env) keep the lite manifest.
    """
    manifest = {
        "kind": "testbed-export",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_url": source_url,
        "subjects": sorted(subjects),
        "workspaces": sorted(stats["workspaces"]),
        "counts": stats["workspaces"],
        "min_start_time": stats["min_start_time"],
        "max_start_time": stats["max_start_time"],
        "platform_version": (platform_info or {}).get("platform_version"),
        "platform_revision": (platform_info or {}).get("revision"),
        "records": [r.name for r in records],
    }
    env = env or {}
    manifest |= {key: env[var] for key, var in _LINEAGE_ENV.items() if env.get(var)}
    return manifest


def fetch_platform_info(base_url: str) -> dict | None:
    """Best-effort platform identity from ``GET /cluster-info`` (None when it can't say).

    The platform serves ``{"platform_version": ..., "revision": ...}`` on an
    unauthenticated route; recording it pins which platform build minted the
    bundle (a later task's attribute-catalog inversion keys off it).
    """
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/cluster-info", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return {"platform_version": data.get("platform_version"), "revision": data.get("revision")}
    except Exception:
        return None


def workspaces_for_subject(subject: Subject) -> list[str]:
    """The intake workspaces a subject's export must capture.

    Benchmark subjects own their realistic workspace plus the ``-oracle`` twin
    (the answer key) unless ``include_rewards`` is off; intake subjects own just
    their workspace. Any other type has no owned-workspace scoping rule, so it
    is a hard error.
    """
    workspace = str(subject.config.get("workspace") or "")
    if not workspace:
        sys.exit(f"snapshot: subject '{subject.name}' has no workspace configured")
    if subject.type == "benchmark":
        if subject.config.get("include_rewards", True):
            return [workspace, f"{workspace}-oracle"]
        return [workspace]
    if subject.type == "intake":
        return [workspace]
    sys.exit(
        f"snapshot: subject '{subject.name}' has type '{subject.type}' — only 'benchmark' and "
        "'intake' subjects own intake workspaces to export (this type has no workspace-scoping rule)"
    )


def backup_records(testbed_tmp: Path, names: list[str], *, backup_dir: Path | None = None) -> Path:
    """Move the named local files into *backup_dir* (default ``<testbed_tmp>/backup-<UTC stamp>/``);
    returns that dir.

    The shared no-silent-destruction mechanism: restores park clobbered local
    records here, and fresh-by-default analyze parks the prior insights YAML
    here — nothing in ``testbed/tmp`` is ever deleted, only moved (no prompt —
    CI-safe). Callers print their own one-liner naming the moved files. A CLI
    invocation that backs up more than once (analyze: the restore's
    clobber-backup, then the fresh-insights move) passes one *backup_dir* so a
    single command yields a single backup dir, not one per stamp.
    """
    if backup_dir is None:
        # Microseconds keep two invocations within the same second from sharing a dir.
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        backup_dir = testbed_tmp / f"backup-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.move(testbed_tmp / name, backup_dir / name)
    return backup_dir


def seed_records(state_tmp: Path, testbed_tmp: Path, *, backup_dir: Path | None = None) -> tuple[str, list[str]]:
    """Copy the bundle's ``tmp/`` run records beside the local ones; ``(message, seeded names)``.

    Only ``*.run.json`` files travel: insights are per-analyze output, not
    state, so any ``insights_*.yaml`` a pre-cutover bundle still carries is
    ignored (and local insight YAMLs are never touched — the fresh/keep choice
    lives in the analyze CLI). Never destroys local state silently: any local
    record the bundle is about to overwrite is first moved into *backup_dir*
    (default: a fresh ``<testbed_tmp>/backup-<UTC stamp>/``) with one printed
    line saying so.
    """
    testbed_tmp.mkdir(parents=True, exist_ok=True)
    bundle_files = sorted(p for p in state_tmp.glob("*.run.json") if p.is_file()) if state_tmp.is_dir() else []
    clobbered = [p.name for p in bundle_files if (testbed_tmp / p.name).exists()]
    if clobbered:
        backup_dir = backup_records(testbed_tmp, clobbered, backup_dir=backup_dir)
        print(f"backed up {len(clobbered)} local record(s) to {backup_dir}: {', '.join(clobbered)}")
    for item in bundle_files:
        shutil.copy2(item, testbed_tmp / item.name)
    seeded = [p.name for p in bundle_files]
    if not seeded:
        return "the bundle carries no run records", seeded
    return f"seeded {len(seeded)} run record(s) from the bundle: {', '.join(seeded)}", seeded


def snapshot_export(
    subjects: list[Subject],
    out: Path,
    tmp_dir: Path,
    *,
    since: datetime.datetime | None,
) -> Path:
    """Export the subjects' workspaces from the read API into one bundle at *out*.

    Bundle layout matches the legacy tar (root ``state/``) but the payload is
    ``export/<workspace>/*.jsonl`` from :func:`testbed.export.export_workspaces`
    plus the ``tmp/`` run records and a ``kind: testbed-export`` manifest.
    Source URL is each subject's stanza ``base_url`` (they must agree; the
    CLI's ``--base`` override rewrites every stanza before this is called).
    """
    workspaces: list[str] = []
    for subject in subjects:
        for workspace in workspaces_for_subject(subject):
            if workspace not in workspaces:
                workspaces.append(workspace)
    # Every selected subject must carry a base_url: a partial miss would silently
    # let the agreement check pass on the configured subset and export the
    # unconfigured subject from the others' platform.
    missing = [s.name for s in subjects if not s.config.get("base_url")]
    if missing:
        sys.exit("snapshot: no base_url configured for subject(s) " + ", ".join(missing) + " (pass --base URL?)")
    urls = {str(s.config["base_url"]) for s in subjects}
    if not urls:
        sys.exit("snapshot: no base_url configured for the selected subjects (pass --base URL?)")
    if len(urls) > 1:
        sys.exit(
            "snapshot: subjects disagree on base_url (" + ", ".join(sorted(urls)) + ") — "
            "snapshot them separately or pass --base URL"
        )
    source_url = urls.pop()
    records = pick_records(tmp_dir, [s.name for s in subjects])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_dir) as tmp:
        state = Path(tmp) / "state"
        (state / "tmp").mkdir(parents=True)
        stats = export.export_workspaces(source_url, workspaces, state, since=since)
        for rec in records:
            shutil.copy2(rec, state / "tmp" / rec.name)
        manifest = build_export_manifest(
            [s.name for s in subjects],
            records,
            stats,
            source_url=source_url,
            platform_info=fetch_platform_info(source_url),
            env=os.environ,
        )
        (state / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["tar", "--zstd", "-cf", str(out), "-C", tmp, "state"], check=True)
    print(f"export bundle written to {out}")
    return out
