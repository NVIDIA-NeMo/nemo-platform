FROM nmp-agentic-base:latest

# Disable MCP by removing the MCP configuration file
# This forces Claude Code to use the CLI instead of MCP tools
RUN rm -f /app/.mcp.json

# Enable platform seeding at startup so system benchmarks (MMLU, etc.) are available
ENV NMP_SEED_ON_STARTUP=1
