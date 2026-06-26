# NeMo Platform

![NEMO Platform](docs/assets/nemo-wordmark.svg)

[![CI](https://github.com/NVIDIA-NeMo/nemo-platform/actions/workflows/ci.yaml/badge.svg)](https://github.com/NVIDIA-NeMo/nemo-platform/actions/workflows/ci.yaml)
[![License](https://img.shields.io/badge/license-Apache_2.0-D22128?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11--3.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Docs](https://img.shields.io/static/v1?label=docs&message=docs.nvidia.com%2Fnemo-platform&color=76B900&style=flat-square&logo=readthedocs&logoColor=white)](https://docs.nvidia.com/nemo-platform)

Make the agents you ship faster, more accurate, and safer.

NeMo Platform brings NVIDIA NeMo libraries together under one CLI, Python SDK, and web UI. Hardening, evaluation, and tuning for the agents you put in production.

## Get started

**Prerequisites:** Python 3.11-3.14, uv, and an API key for an inference provider (NVIDIA Build, OpenAI, Anthropic, Google Gemini, or a local Ollama instance). Node.js 22.18.x with `pnpm` only if you want the web UI.

```bash
git clone https://github.com/NVIDIA-NeMo/nemo-platform.git
cd nemo-platform

make bootstrap
source .venv/bin/activate

nemo setup
```

`nemo setup` starts local services, registers your LLM provider, discovers available models, installs agent skills, and deploys a sample agent (see more below).

See **[SETUP.md](SETUP.md)** for the full setup playbook (local data dir, DB reset, manual service start, troubleshooting).

Verify:

```bash
nemo services status
```

To permanently reset the database state: `rm -rf ~/.local/share/nemo`.

<details>
<summary>Useful CLI commands once setup completes</summary>

```bash
nemo --help                # All commands
nemo models list           # Available models
nemo chat <model-name>     # Chat directly with a model
nemo services status       # Platform health
nemo skills list           # Skills installed on the platform
```

Every capability is also available via REST API. Model inference uses the model IDs returned from `nemo models list` and is available at:

```text
http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1/chat/completions
```

To run platform services in the foreground in a separate terminal (instead of the background process `nemo setup` starts):

```bash
nemo services run
```

</details>

<details>
<summary>Studio (web UI) bootstrap troubleshooting</summary>

If `make bootstrap` reports that Studio asset bootstrap did not complete, the API still runs but the web UI is unavailable until the bundle is built. Install Node 22.18.x with `pnpm env use --global 22.18.0`, then run `make bootstrap-studio` from the repo root.

</details>

<details>
<summary>Non-interactive setup (for agents, CI, or scripts)</summary>

```bash
export NVIDIA_API_KEY=nvapi...
export NEMO_DEFAULT_MODEL=nvidia-nemotron-3-super-120b-a12b
nemo setup --auto --start-services --install-skills --deploy-agent
```

</details>

## Use NeMo Platform from your coding agent

After installation, launch your coding agent (Claude Code, Codex, Cursor, OpenCode, etc) from inside the `nemo-platform` directory. This is the primary way of interacting with the NeMo Platform.

Things you can ask it to do, once the platform is running:

- "Scaffold an agent from this spec and deploy it."
- "Run an evaluation against my agent."
- "Add content-safety guardrails to my agent."
- "Help me optimize my agent."
- "Show me what's running on the platform."
- "Shut down NeMo cleanly."

## What's here today

- **Secure agents.** Guardrails (content safety, jailbreak detection, PII redaction), Auditor (red-teaming via garak), Anonymizer (PII handling for training data).
- **Evaluate agents.** LLM-as-judge, deterministic, agentic, and RAG benchmarks. Harbor-backed eval suites for regression testing.
- **Tune agents.** Skill optimization, prompt and hyperparameter tuning, Switchyard model routing.
- **Build agents.** NVIDIA NeMo Agent Toolkit (NAT) for LangGraph-based agents. Shared infrastructure: Inference Gateway, Secrets, Files, Entity Store, Jobs.
- **Generate synthetic data.** Generate synthetic data for training or evaluation purposes using Data Designer.
- **NeMo Studio (alpha).** Installed automatically with the platform. Browser UI for chat, monitoring, and reviewing optimization suggestions. Studio's agent-focused features are still a work in progress; the CLI is the primary surface today.

## What's coming soon

- Fine-tuning
- Safe Synthesizer (synthetic data with privacy guarantees)
- Broader agent framework support. Today NeMo Platform optimizes LangGraph agents wrapped in NAT. If your agent is in another framework, you need to write the NAT wrapper.

## Skills

`nemo setup` detects Claude Code, Cursor, Codex, and OpenCode and installs NeMo skills into your agent of choice, either into the local directory or globally. Platform-level skills live under `packages/nemo_platform_ext/src/nemo_platform_ext/skills/` and ship with the `nemo-platform` package; plugin-owned skills live under `plugins/<plugin>/src/<plugin>/skills/`.

To install or refresh skills:

```bash
nemo skills install --agent claude
nemo skills install --agent claude --skill nemo-build-agent --skill nemo-status
```

## Try the demo agent

`nemo setup --deploy-agent` deploys a demo calculator agent you can use to
explore the platform's evaluate / optimize loop.

```bash
nemo agents invoke --agent calculator-agent --input "what is 12 * 8?"
```

The calculator-agent package is installed automatically (`plugins/nemo-agents/examples/calculator-agent/`).

<details>
<summary>Deploy it manually</summary>
```bash
nemo agents create --name calculator-agent \
  --agent-config plugins/nemo-agents/examples/calculator-agent/src/calculator_agent/calculator-agent.yml
nemo agents deploy --agent calculator-agent
nemo agents deployments wait --agent calculator-agent
```
</details>

<details>
<summary>Evaluate the agent</summary>
```bash
nemo agents evaluate run \
  --eval-config plugins/nemo-agents/examples/calculator-agent/src/calculator_agent/calculator-eval.yml \
  --agent calculator-agent
```
</details>

<details>
<summary>Optimize the agent</summary>
```bash
nemo agents optimize run \
  --optimize-config plugins/nemo-agents/examples/calculator-agent/src/calculator_agent/calculator-optimize.yml \
  --agent calculator-agent
```
</details>

The demo agent uses `${NEMO_DEFAULT_MODEL}` for both execution and the judge LLM. To select different models for either/both, update the yaml config files.

## Documentation

Full documentation: [NeMo Platform docs](https://docs.nvidia.com/nemo-platform)

- [Setup](docs/get-started/setup.md): installation, providers, SDK.
- [CLI reference](docs/cli/index.md): all commands.
- [API reference](docs/api/index.md): REST endpoints.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow.
See [TESTING.md](TESTING.md) for testing strategy.

## License

NeMo Platform is licensed under the Apache License 2.0. Third-party open-source dependencies have their own licenses; review them before use.
