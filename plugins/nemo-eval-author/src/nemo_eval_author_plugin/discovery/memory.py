# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persist discovery to a fileset, and read back what a previous run concluded.

One fixed fileset with agent-scoped paths, following the telemetry exporter's precedent of
``nemo-agent-telemetry`` plus ``{agent}/...``. Nothing is written into the user's repo: the
repo is the thing under inspection, and a command that inspects a repo should not change it.

The read side is what makes discovery cheap to repeat. A prior report lists the files it was
derived from along with their hashes, so a re-run can re-hash exactly those paths and
compare one digest, deciding whether anything relevant moved without touching Harbor. That
is the same property that lets a later, weaker model trust the artifact instead of
rediscovering it.

``harbor-job.yaml`` is uploaded only when it exists, and it only exists when Harbor accepted
the schema. A config that is present in the fileset is therefore a config Harbor could load,
which is the invariant the whole artifact rests on.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from nemo_eval_author_plugin.discovery.models import Finding, InputFingerprint
from nemo_eval_author_plugin.discovery.report import (
    JOB_CONFIG_FILENAME,
    REPORT_FILENAME,
    fingerprint_inputs,
)
from pydantic import BaseModel, Field

FILESET_NAME = "nemo-eval-author"

_GROUP = "memory"
_FRONT_MATTER_FENCE = "---"


class PriorRecord(BaseModel):
    """The parts of a previously persisted report that decide whether to redo the work."""

    inputs_digest: str | None = None
    runnable: bool = False
    harbor_version: str | None = None
    last_validated_at: str | None = None
    inputs: list[InputFingerprint] = Field(default_factory=list)
    text: str = Field(default="", description="The report as stored, so a fresh re-run can restamp and reupload it.")


def remote_report_path(agent: str) -> str:
    return f"{agent}/{REPORT_FILENAME}"


def remote_config_path(agent: str) -> str:
    return f"{agent}/{JOB_CONFIG_FILENAME}"


def _split_front_matter(text: str) -> tuple[str, str] | None:
    """Separate the front matter from the body, or ``None`` if there is no front matter.

    One implementation for both readers, because the fence is easy to miscount: the
    closing ``\\n---`` is consumed by the split, so the body it returns still carries the
    blank line that followed it and can be concatenated straight back on.
    """
    if not text.startswith(_FRONT_MATTER_FENCE):
        return None
    head, _, body = text.partition(f"\n{_FRONT_MATTER_FENCE}")
    if not _:
        return None
    return head[len(_FRONT_MATTER_FENCE) :], body


def parse_front_matter(text: str) -> dict[str, Any] | None:
    """Pull the YAML front matter out of a rendered report."""
    split = _split_front_matter(text)
    if split is None:
        return None
    try:
        payload = yaml.safe_load(split[0])
    except yaml.YAMLError:
        return None
    return payload if isinstance(payload, dict) else None


async def load_previous(sdk: Any, *, agent: str, workspace: str) -> PriorRecord | None:
    """Fetch the last report for this agent, or ``None`` when there is nothing to compare.

    A missing file and an unreachable platform are the same answer here: rediscover. That
    is why every failure mode returns ``None`` rather than raising.
    """
    try:
        raw = await sdk.files.download_content(
            remote_path=remote_report_path(agent),
            fileset=FILESET_NAME,
            workspace=workspace,
        )
    except Exception:
        return None

    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    except UnicodeError:
        return None

    front = parse_front_matter(text)
    if front is None:
        return None

    inputs = [
        InputFingerprint(path=str(item["path"]), sha256=str(item["sha256"]))
        for item in front.get("inputs") or []
        if isinstance(item, dict) and "path" in item and "sha256" in item
    ]
    return PriorRecord(
        inputs_digest=front.get("inputs_digest"),
        runnable=bool(front.get("runnable")),
        harbor_version=front.get("harbor_version"),
        last_validated_at=front.get("last_validated_at"),
        inputs=inputs,
        text=text,
    )


def restamp(text: str, *, when: datetime, harbor_version: str) -> str | None:
    """Update a stored report's validation stamp without regenerating its narrative.

    Used when nothing the report depends on has changed: the findings would come out
    word for word, so re-deriving them would only spend a Harbor resolution and a Docker
    preflight to reprint the same file. The stamp still has to move, because
    ``last_validated_at`` answers "when did someone last confirm this", and the Harbor
    version has to move with it, since confirming under a different Harbor is a different
    claim.

    Returns ``None`` when the front matter cannot be re-serialized, which tells the caller
    to fall back to a full re-render rather than upload something malformed.
    """
    split = _split_front_matter(text)
    front = parse_front_matter(text)
    if split is None or front is None:
        return None
    front["last_validated_at"] = when.isoformat()
    front["harbor_version"] = harbor_version
    rendered = yaml.safe_dump(front, sort_keys=False, default_flow_style=False).rstrip()
    return f"{_FRONT_MATTER_FENCE}\n{rendered}\n{_FRONT_MATTER_FENCE}{split[1]}"


def rehash_prior_inputs(prior: PriorRecord, repo_root: Path) -> list[InputFingerprint]:
    """Re-hash the files a prior report named, so its digest can be recomputed today.

    A path the prior run recorded and that no longer exists is dropped, which changes the
    digest and correctly forces revalidation: a report derived from a file someone deleted
    is exactly the kind of stale claim this comparison exists to catch.
    """
    return fingerprint_inputs([repo_root / item.path for item in prior.inputs], repo_root)


async def persist(
    sdk: Any,
    *,
    agent: str,
    workspace: str,
    markdown: str,
    job_config: str | None,
) -> tuple[bool, list[Finding]]:
    """Upload the report, and the config when there is one worth uploading.

    Returns whether everything landed. Upload failures are reported as warnings rather
    than failures, because ``runnable`` answers one question only — can Harbor run this
    config — and a fileset being down does not change that answer. The caller folds the
    ``False`` into its exit code.
    """
    findings: list[Finding] = []
    ok = True

    for remote_path, content, label in (
        (remote_report_path(agent), markdown, REPORT_FILENAME),
        *(((remote_config_path(agent), job_config, JOB_CONFIG_FILENAME),) if job_config is not None else ()),
    ):
        try:
            await sdk.files.upload_content(
                content=content.encode("utf-8"),
                remote_path=remote_path,
                fileset=FILESET_NAME,
                workspace=workspace,
                fileset_auto_create=True,
            )
        except Exception as exc:
            ok = False
            findings.append(
                Finding(
                    name="upload",
                    group=_GROUP,
                    status="warn",
                    message=f"Could not upload {label}: {type(exc).__name__}: {exc}",
                    hint=f"Target was fileset '{FILESET_NAME}' at {remote_path} in workspace '{workspace}'.",
                )
            )
            continue
        findings.append(
            Finding(
                name="upload",
                group=_GROUP,
                status="pass",
                message=f"Uploaded {label} to fileset '{FILESET_NAME}' at {remote_path}",
            )
        )

    if job_config is None:
        findings.append(
            Finding(
                name="upload",
                group=_GROUP,
                status="warn",
                message=f"Withheld {JOB_CONFIG_FILENAME}: no config passed Harbor's schema check",
                hint="A config in this fileset is always one Harbor could load, so none was written.",
            )
        )
    return ok, findings
