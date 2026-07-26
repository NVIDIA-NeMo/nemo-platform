# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local HTTP server for Platform-managed Fabric agent runtimes."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from nemo_agents_plugin.agent_config import AgentConfig, load_agent_config

logger = logging.getLogger(__name__)


async def _validate_agent_config(config: AgentConfig, *, base_dir: Path) -> Any:
    from nemo_agents_plugin.fabric.validation import validate_platform_agent_config

    return await validate_platform_agent_config(config, base_dir=base_dir)


def create_fabric_serving_app(agent_config_path: str | Path) -> FastAPI:
    """Create a serving app that validates its agent definition at startup."""
    config_path = Path(agent_config_path).resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        agent_config = load_agent_config(config_path)
        validation_result = await _validate_agent_config(agent_config, base_dir=config_path.parent)
        app.state.agent_config = agent_config
        app.state.base_dir = config_path.parent
        app.state.validation_result = validation_result
        logger.info("Validated Fabric-backed agent config at %s", config_path)
        yield

    app = FastAPI(title="NeMo Agents Fabric Server", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions() -> None:
        raise HTTPException(status_code=503, detail="Fabric runtime session manager is not initialized.")

    return app


def main(argv: list[str] | None = None) -> int:
    """Run the local Fabric agent server."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-config", required=True, type=Path, help="Path to an agent YAML config file.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args(argv)

    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        create_fabric_serving_app(args.agent_config),
        host=args.host,
        port=args.port,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
