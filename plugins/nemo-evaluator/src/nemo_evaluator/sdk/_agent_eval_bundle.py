# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reading an agent-eval run bundle back into a result.

Separate from the executor and the job handle so both can use it without a cycle.
"""

from __future__ import annotations

import json
import tarfile
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

from nemo_evaluator_sdk.agent_eval.results import AgentEvalResult, AgentEvalSummary, RunMetadata
from nemo_evaluator_sdk.agent_eval.scores import AgentEvalTaskScore
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalTask
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrial

#: Bundle files needed to rebuild the result. ``tasks.jsonl`` is deliberately absent — the caller
#: already holds the tasks it submitted, and a persisted task's metrics are serialized as
#: descriptors that cannot be validated back into live ``Metric`` objects.
_RUN = "run.json"
_TRIALS = "trials.jsonl"
_SCORES = "scores.jsonl"
_SUMMARY = "summary.json"
_METADATA = "metadata.json"
_WANTED = frozenset({_RUN, _TRIALS, _SCORES, _SUMMARY, _METADATA})


def read_bundle(payload: bytes) -> dict[str, str]:
    """Read the result files out of a run-bundle tarball, in memory, keyed by base name.

    Nothing is written to disk and members are matched on base name only, so a malformed archive
    has no path to traverse.
    """
    contents: dict[str, str] = {}
    with tarfile.open(fileobj=BytesIO(payload), mode="r:*") as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name).name
            if not member.isfile() or name not in _WANTED or name in contents:
                continue
            handle = tar.extractfile(member)
            if handle is not None:
                contents[name] = handle.read().decode("utf-8")
    return contents


def assemble_result(
    contents: Mapping[str, str],
    *,
    tasks: Sequence[AgentEvalTask],
    job_name: str,
) -> AgentEvalResult:
    """Rebuild the result from the bundle plus the tasks the caller submitted.

    ``tasks`` come from the caller rather than the bundle: they are already live objects here,
    whereas ``tasks.jsonl`` stores metrics as descriptors that cannot round-trip into ``Metric``.
    """
    run = json.loads(_require(contents, _RUN, job_name))
    return AgentEvalResult(
        run_id=str(run.get("run_id") or job_name),
        tasks=list(tasks),
        trials=[AgentEvalTrial.model_validate(row) for row in _jsonl(_require(contents, _TRIALS, job_name))],
        scores=[AgentEvalTaskScore.model_validate(row) for row in _jsonl(_require(contents, _SCORES, job_name))],
        summary=AgentEvalSummary.model_validate(json.loads(_require(contents, _SUMMARY, job_name))),
        metadata=RunMetadata.model_validate(json.loads(_require(contents, _METADATA, job_name))),
    )


def _require(contents: Mapping[str, str], name: str, job_name: str) -> str:
    if name not in contents:
        raise ValueError(f"agent-eval run bundle for job {job_name!r} has no {name}")
    return contents[name]


def _jsonl(payload: str) -> list[dict[str, Any]]:
    """Parse a JSONL bundle artifact, skipping blank lines."""
    return [json.loads(line) for line in payload.splitlines() if line.strip()]
