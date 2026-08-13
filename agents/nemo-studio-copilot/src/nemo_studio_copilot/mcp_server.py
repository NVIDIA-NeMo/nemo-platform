# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fabric-native MCP boundary for NeMo Studio Copilot tools."""

from fastmcp import FastMCP
from nemo_studio_copilot.register import (
    ask_user_question,
    check_status,
    job_progress,
    nemo_api,
    select_agent,
    select_dataset_file,
    select_eval_config,
    select_model,
    studio_link,
)

TOOLS = (
    nemo_api,
    check_status,
    select_agent,
    select_model,
    select_dataset_file,
    select_eval_config,
    job_progress,
    studio_link,
    ask_user_question,
)


def create_server() -> FastMCP:
    server = FastMCP("NeMo Studio Copilot")
    for tool in TOOLS:
        server.tool(tool)
    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
