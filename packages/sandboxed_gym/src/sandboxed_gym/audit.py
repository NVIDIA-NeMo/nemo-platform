# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Decision log for the episode broker.

Every request the broker allows or refuses is recorded here as one JSON line, on a dedicated
logger so a deployment can route it separately from ordinary training output. The broker is the
component that decides what untrusted code may provision, so "what did it permit, for whom, and
why was that refused" needs to be answerable after the fact rather than reconstructed from a
stack trace.

What deliberately never reaches this log: the broker token, file contents, and environment
variable *values*. Environment keys are recorded because they are useful for debugging a rejected
episode; values are caller-supplied and may carry the tenant's own secrets.
"""

import json
import logging
from typing import Any

AUDIT_LOGGER = logging.getLogger("sandboxed_gym.audit")

# Commands are user code and can be arbitrarily long; enough is kept to identify what ran.
MAX_LOGGED_COMMAND_CHARS = 200


def truncate(value: str, limit: int = MAX_LOGGED_COMMAND_CHARS) -> str:
    """Shorten a value for the audit log, marking that it was cut."""
    return value if len(value) <= limit else f"{value[:limit]}...[{len(value) - limit} more]"


def record(event: str, *, job_id: str, outcome: str, **fields: Any) -> None:
    """Write one audit entry.

    Args:
        event: Dotted event name, e.g. ``episode.create``.
        job_id: The job the broker serves.
        outcome: ``allowed``, ``rejected``, or ``failed``.
        **fields: Additional non-sensitive context.
    """
    payload: dict[str, Any] = {
        "event": event,
        "job_id": job_id,
        "outcome": outcome,
        **fields,
    }
    AUDIT_LOGGER.info("episode-broker %s", json.dumps(payload, sort_keys=True, default=str))
