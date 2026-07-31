# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Persist discovery to a fileset.

One fixed fileset with agent-scoped paths, following the telemetry exporter's precedent of
``nemo-agent-telemetry`` plus ``{agent}/...``. Nothing is written into the user's repo: the
repo is the thing under inspection, and a command that inspects a repo should not change it.

``harbor-job.yaml`` is uploaded only when it exists, and it only exists when Harbor accepted
the schema. A config that is present in the fileset is therefore a config Harbor could load,
which is the invariant the whole artifact rests on.
"""

from typing import Any

from nemo_eval_author_plugin.discovery.models import (
    FILESET_NAME,
    JOB_CONFIG_FILENAME,
    REPORT_FILENAME,
    Finding,
)

_GROUP = "memory"


def remote_report_path(agent: str) -> str:
    return f"{agent}/{REPORT_FILENAME}"


def remote_config_path(agent: str) -> str:
    return f"{agent}/{JOB_CONFIG_FILENAME}"


async def persist(
    sdk: Any,
    *,
    agent: str,
    workspace: str,
    markdown: str,
    job_config: str | None,
) -> tuple[bool, list[Finding]]:
    """Upload the report, and the config when the caller passed one.

    Reports only what it did. Why a config might be absent is the caller's to explain —
    withheld because nothing validated, or not needed because the repo maintains its own —
    and a message here could only guess between them.

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

    return ok, findings
