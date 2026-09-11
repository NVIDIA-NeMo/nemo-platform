# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FileSet-delivered Gym resources server for the ASCII Tree example.

Gym launches this module inside OpenSandbox using ``ascii_tree.yaml``. It
extracts assistant text from each model response, calls the scorer installed
from the adjacent wheel requirement, and returns the reward and parsed tree.
The server is environment code; developers invoke the parent ``run.py`` rather
than running this file locally.
"""

from __future__ import annotations

from typing import Any

from nemo_gym.base_resources_server import (  # ty: ignore[unresolved-import] - supplied by the Gym runtime
    BaseResourcesServerConfig,
    BaseVerifyRequest,
    BaseVerifyResponse,
    SimpleResourcesServer,
)
from nmp_ascii_tree_evaluator.scoring import (  # ty: ignore[unresolved-import] - installed from the FileSet wheel
    ascii_tree_reward,
    extract_ascii_formatted,
)


class AsciiTreeResourcesServerConfig(BaseResourcesServerConfig):
    """Configuration for the FileSet-provided ASCII Tree resources server."""


class AsciiTreeVerifyRequest(BaseVerifyRequest):
    """Expected ASCII tree and model response supplied by Gym."""

    answer: str
    question: str = ""
    task: str = "ascii_tree_formatting"
    example_id: int | str | None = None
    info: dict[str, Any] | None = None
    task_idx: int | None = None
    vf_env_id: str | None = None


class AsciiTreeVerifyResponse(BaseVerifyResponse):
    """Custom reward and parsed model output returned to Gym."""

    answer: str
    observed_text: str
    parsed_ascii: str | None


def assistant_text(response: Any) -> str:
    """Collect output text from a Responses API object or equivalent mapping."""
    outputs = response.get("output", []) if isinstance(response, dict) else getattr(response, "output", [])
    text_parts: list[str] = []
    for output_item in outputs:
        item_type = output_item.get("type") if isinstance(output_item, dict) else getattr(output_item, "type", None)
        if item_type != "message":
            continue
        content_items = (
            output_item.get("content", []) if isinstance(output_item, dict) else getattr(output_item, "content", [])
        )
        for content_item in content_items:
            content_type = (
                content_item.get("type") if isinstance(content_item, dict) else getattr(content_item, "type", None)
            )
            if content_type != "output_text":
                continue
            text = content_item.get("text", "") if isinstance(content_item, dict) else getattr(content_item, "text", "")
            text_parts.append(str(text))
    return "".join(text_parts)


class AsciiTreeResourcesServer(SimpleResourcesServer):
    """Score model responses with FileSet-provided ASCII Tree code."""

    config: AsciiTreeResourcesServerConfig

    async def verify(
        self,
        body: AsciiTreeVerifyRequest,
    ) -> AsciiTreeVerifyResponse:
        """Extract the assistant response, calculate its reward, and return evidence."""
        observed_text = assistant_text(body.response)
        return AsciiTreeVerifyResponse(
            **body.model_dump(),
            reward=ascii_tree_reward(observed_text, body.answer),
            observed_text=observed_text,
            parsed_ascii=extract_ascii_formatted(observed_text),
        )


if __name__ == "__main__":
    AsciiTreeResourcesServer.run_webserver()
