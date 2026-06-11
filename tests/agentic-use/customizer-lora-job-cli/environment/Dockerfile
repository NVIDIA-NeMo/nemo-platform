FROM nmp-agentic-base:latest

# Disable MCP by removing the MCP configuration file
# This forces Claude Code to use the CLI instead of MCP tools
RUN rm -f /app/.mcp.json

# Install Docker CLI for job container management
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*

# Copy environment scripts
COPY image-env.sh /app/image-env.sh
COPY setup-env.sh /app/setup-env.sh
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/image-env.sh /app/entrypoint.sh /app/setup-env.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["sleep", "infinity"]
