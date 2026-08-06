# Email Phishing Agent — Fabric example (`nemo-agents-spec-v1`)

A DeepAgents **orchestrator** that delegates the verdict to a phishing
**sub-agent**, which calls a deterministic **`extract_iocs`** tool. Prompt and
model live in `agent.yaml` (tunable); every step emits a trace span.

```
orchestrator (deepagents) ── delegates ──▶ phishing-analyzer sub-agent
      └───────────── calls ─────────────▶ extract_iocs (stdio MCP tool)
```

## Parts

| Path | What | Why |
|---|---|---|
| `agent.yaml` | The `nemo-agents-spec-v1` config: harness, sub-agent, model, MCP server, telemetry | The single tunable surface — prompts + hyperparameters |
| `mcps/iocs.py` | `extract_iocs` (pure regex) + FastMCP stdio server | The one real tool; URL/domain extraction incl. the sender |
| `pyproject.toml` | Packages `mcps/`; exposes console `email-phishing-iocs` | Makes the tool resolvable at runtime |
| `data/smaller_test.csv` | Labeled emails with an assembled `email` column (`From:`/`Subject:`/body) | Eval input; keeps the sender (a top phishing tell) |
| `data/build_dataset.py` | Rebuilds that column from the upstream NAT dataset | Regenerate after changing the assembly |
| `email-phishing-eval.yml` | Eval config; `question_key: email` | Scores verdicts against the `label` column |
| `tests/test_extract_iocs.py` | Unit tests for the tool | Guards the extractor |

## Port it (to your own agent)

1. **Copy** this directory to `nemo-agent-config/<your-agent>/`.
2. **Rename** in `pyproject.toml` (`name`, `[project.scripts]` console), `agent.yaml` (`name`, `project`, and `mcp.servers.<n>.url` → your console), and your tool in `mcps/`.
3. **Register** as a workspace member: add the path to root `pyproject.toml` `members`, then `uv sync --all-packages` (installs your console into `.venv` for local runs).
4. **Point** `data/` + `email-phishing-eval.yml` at your dataset.

## Use it in Platform (CLI)

Prereqs: platform up (`NMP_BASE_URL=http://localhost:8080`), `NVIDIA_API_KEY` set, `uv sync --all-packages` done.

1. **Register** — `nemo agents create --name email-phishing-agent --agent-config plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/agent.yaml`
2. **Deploy** — `nemo agents deploy --agent email-phishing-agent --name email-phishing-agent-deployment --mode subprocess` (for `docker`/`k8s`, first `nemo agents package --pyproject <this>/pyproject.toml --tag <img>`, then deploy `--mode docker --image <img>`).
3. **Invoke** — `nemo agents invoke --agent-deployment email-phishing-agent-deployment --input "<full email>"` → a YAML verdict.
4. **Observe** — `nemo agents logs --agent email-phishing-agent`; the `extract_iocs` call lands in `artifacts/.../events.atof.jsonl` (`category: tool`).
5. **Tune & evaluate** — edit `agent.yaml` (sub-agent `system_prompt`, `models.default.temperature`), re-deploy, then `nemo agents evaluate run --eval-config <this>/email-phishing-eval.yml --agent email-phishing-agent`.

## Use it in Studio

Prereqs: same platform + key; Studio with Intake on (`VITE_FF_INTAKE_ENABLED=true`), at `…/studio/workspaces/default`.

1. **Register** — Agents → *Create Example* → the `email-phishing-agent` tile. **Pending (ASTD‑08)**; until it lands, register via the CLI (left), then manage it here.
2. **Deploy** — from the agent's page. **Pending the same tile**; deploy via the CLI today.
3. **Invoke** — open the deployed agent → Chat → paste the email → read the verdict.
4. **Observe** — Intake → Traces → open the run: orchestrator → `phishing-analyzer` → `extract_iocs` spans.
5. **Tune & evaluate** — edit `agent.yaml` and re-deploy (CLI), then Run Evaluation → `smaller_test.csv` for the accuracy score.

## Status

Live-validated for `--mode subprocess` (deploy → invoke → correct verdict; trace + `extract_iocs` call confirmed). Not yet exercised: container (`docker`/`k8s`) packaging, the Studio *Create Example* tile (ASTD‑08), and eval judge tuning (weights/prompt are starters).
