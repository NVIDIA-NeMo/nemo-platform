# `mock-tools/` — Quill's tools as a stdio MCP server

`mock_tools_server.py` exposes Quill's four tools with **canned results** over stdio
MCP. Fabric's deepagents adapter can't take in-process Python tools, so tools come
from an MCP server; the mock lets `demos/fabric_demo.py` make **real** tool calls the
guardrail can gate, without a real backend.

**Swap this for your real tool endpoints** (expose your tool server as MCP, or point
`add_mcp_server` at it). Tool names must match the `guardrail__<tool>__*` tasks in
`guardrails_config/prompts.yml`.
