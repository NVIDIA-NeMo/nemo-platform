# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_platform.cli.manifest import TopLevelEntry

TOP_LEVEL_ENTRIES = (
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.auth:app",
        help="Manage authentication for NeMo Platform.",
        name="auth",
        panel="Setup",
        kind="group",
        hidden=True,
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.config:app",
        help="""\
Manage NeMo Platform CLI configuration.

Examples:
# Set the cluster base URL (most common first step).
nemo config set --base-url https://nmp.example.com
# View current effective configuration.
nemo config view
# Switch to a named context.
nemo config use-context dev""",
        name="config",
        panel="Setup",
        kind="group",
        hidden=True,
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.setup:setup_command",
        help="""\
Set up NeMo Platform: start services, configure a provider, install skills.

Walks through starting local services, selecting a provider, entering
credentials, registering the provider with the platform, picking a
default model, installing coding agent skills, and optionally deploying
a demo agent.

Requires an interactive terminal (TTY). In non-interactive contexts
(CI, piped input), pass --auto to use environment variables instead.

Use --auto for non-interactive setup from environment variables
(NEMO_DEFAULT_INFERENCE_KEY, NVIDIA_API_KEY, OPENAI_API_KEY,
ANTHROPIC_API_KEY, GEMINI_API_KEY).
Override the default model with NEMO_DEFAULT_MODEL.

Examples:
  nemo setup
  nemo setup --auto
  nemo setup --auto --start-services --install-skills --deploy-agent
  nemo setup --auto --start-services --ready-timeout 360
  nemo setup --workspace my-workspace
  nemo setup --no-install-skills --no-deploy-agent""",
        name="setup",
        panel="Setup",
        kind="command",
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.skills.cli:app",
        help="""\
Install AI agent skill files for Nemo.

Supported agents: claude, codex, cursor, opencode

Examples:
# List available skills.
nemo skills list
# Show a skill's content.
nemo skills show inference
# Install all skills for Claude Code.
nemo skills install --agent claude
# Install specific skills only.
nemo skills install --agent claude --skill inference""",
        name="skills",
        panel="Setup",
        kind="group",
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.quickstart.cli:quickstart_app",
        help="Quickstart commands for managing the NeMo Platform container.",
        name="quickstart",
        panel="Setup",
        kind="group",
        hidden=True,
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.services.cli:services_app",
        help="Run platform services locally.",
        name="services",
        panel="Setup",
        kind="group",
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.quickstart.cli:cluster_info_app",
        help="Show information about the connected platform cluster.",
        name="cluster-info",
        panel="Setup",
        kind="group",
        hidden=True,
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.use_cases.chat:chat",
        help="""\
Start an interactive chat session with a model.

By default, uses model entity routing where the model name should match
what's shown in 'nemo models list'.

Use --provider for direct provider routing, where the model argument is
passed directly to the provider's API.

Passing PROMPT sends one message and exits unless --interactive is set.
Omitting PROMPT in a TTY starts the interactive chat UI. In non-TTY
contexts, PROMPT may also be piped on stdin. Piped stdin is read in full
before sending. If both PROMPT and piped stdin are provided, PROMPT takes
precedence.

Examples:
  nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5
  nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 "What is machine learning?"
  nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 "What is machine learning?" --interactive
  echo "What is machine learning?" | nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5
  nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 "What is machine learning?" -f json
  nemo chat nvidia/llama-3.3-nemotron-super-49b-v1.5 --provider nvidia-build""",
        name="chat",
        panel="CLI functions",
        kind="command",
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.docs:docs_command",
        help="""\
Read NeMo Platform documentation.

Examples:
nemo docs get-started/setup
nemo docs set-up/helm/install
nemo docs --list
nemo docs cli/configuration""",
        name="docs",
        panel="CLI functions",
        kind="command",
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.use_cases.wait:app",
        help="Wait for resources to reach a desired status.",
        name="wait",
        panel="CLI functions",
        kind="group",
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.use_cases.agent:app",
        help="""\
Commands for AI agent context and capability discovery.

Examples:
# Dump full agent context (plugins, commands, skills).
nemo agent context
# List all available commands.
nemo agent commands""",
        name="agent",
        panel="CLI functions",
        kind="group",
    ),
    TopLevelEntry(
        import_path="nemo_platform.cli.commands.plugins:app",
        help="""\
Commands for plugin discovery.

Examples:
# List installed plugins.
nemo plugins list""",
        name="plugins",
        panel="CLI functions",
        kind="group",
    ),
)
