# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""stdio MCP server exposing the deterministic ``extract_iocs`` tool.

Launched by the Fabric deepagents harness as a ``harness_native`` stdio MCP
server (see agent.yaml). The console script name ``email-phishing-iocs-mcp`` is
installed by ``uv pip install .`` and referenced verbatim as the server url.
"""

from __future__ import annotations

from email_phishing_fabric import iocs
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("email-phishing-iocs")


@mcp.tool()
def extract_iocs(text: str) -> dict[str, list[str]]:
    """Extract URLs and domains (IOCs) from email text, including the From: line."""
    return iocs.extract_iocs(text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
