# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Entity Store models owned by the Studio service."""

from typing import ClassVar, Literal

from nmp.common.entities.client import EntityBase
from nmp.studio.copilot_artifacts import ChatArtifactsResponse
from pydantic import BaseModel, Field


class CopilotMessage(BaseModel):
    """One user or assistant message in a persisted Copilot conversation."""

    role: Literal["user", "assistant"]
    content: str


class CopilotConversation(EntityBase):
    """A workspace-scoped, user-owned NeMo Copilot conversation."""

    __entity_type__: ClassVar[str] = "copilot_conversation"

    session_id: str = Field(description="Stable Studio session UUID exposed to the UI.")
    owner_id: str = Field(description="Principal that owns and may read this conversation.")
    messages: list[CopilotMessage] = Field(default_factory=list)
    chat_artifacts: ChatArtifactsResponse = Field(default_factory=ChatArtifactsResponse)
