# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ResultEvent(BaseModel):
    """The outcome of a single coding-agent run.

    `success=True` means the agent reported task completion. `success=False`
    means the agent ran but reported an error (budget exceeded, tool refusal,
    etc.). If the agent couldn't run at all, `agent.run()` raises
    AgentRunError instead of returning a ResultEvent.

    `session_id` is the conversational identity — it can be reused across
    multiple `run()` calls when chaining with `resume_session_id`. To find
    the on-disk artifacts for *this specific run* (its prompt, JSONL, and
    stderr), use `artifact_dir` instead.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    artifact_dir: Path
    success: bool
    text: str | None = None
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    num_turns: int = 0
    stop_reason: str = ""
    timestamp: datetime
