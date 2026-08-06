# Email Phishing Agent — Fabric example (`nemo-agents-spec-v1`)

A DeepAgents **orchestrator** that delegates to a phishing **sub-agent**, which
calls a deterministic **`extract_iocs`** tool. The *shape* is the template —
copy it, then swap the domain pieces below for your own agent.

```
orchestrator (deepagents) ── delegates ──▶ phishing-analyzer sub-agent
      └───────────── calls ─────────────▶ extract_iocs (stdio MCP tool)
```

## Parts & what to swap

| Path | What it is | Swap for your own |
|---|---|---|
| `agent.yaml` | The `nemo-agents-spec-v1` config: harness, sub-agent, model, MCP server, telemetry | Rewrite the orchestrator `instructions.system` and the sub-agent `system_prompt` + `description`; set `models.default` (+ `temperature`); rename `name` / `telemetry.project` |
| `mcps/iocs.py` | `extract_iocs` (pure regex) + a FastMCP stdio server | Replace the function body with your tool's logic; keep the `@mcp.tool()` wrapper + `main()`. Rename the module and tool |
| `pyproject.toml` | Packages `mcps/`; exposes console `email-phishing-iocs` | Set `name` and `[project.scripts] <console> = "mcps.<module>:main"` |
| `data/smaller_test.csv` + `build_dataset.py` | Labeled eval rows; the builder assembles a sender-inclusive `email` column | Drop in your rows; edit the assembly to the fields your agent reads |
| `email-phishing-eval.yml` | Eval config (`question_key: email`, `answer_key: label`) | Point the keys at your columns; tune the judge weights/prompt |
| `tests/test_extract_iocs.py` | Unit tests for the tool | Rewrite for your tool's contract |

## Keep in sync

Two couplings break silently if you rename one side only:

- **Console name:** `pyproject.toml [project.scripts]` **must equal** `agent.yaml` → `mcp.servers.<name>.url`.
- **Workspace member:** add your directory to the **root** `pyproject.toml` `members`, then `uv sync --all-packages` — this installs the console so `--mode subprocess` can launch it.

Keep the `mcps/` package directory as-is (its name is a shared namespace across examples); rename the *module* inside it and the console, not the directory.

## Run it (to validate your swap)

Prereqs: platform up (`NMP_BASE_URL=http://localhost:8080`), `NVIDIA_API_KEY` set, `uv sync --all-packages` done. Studio also needs Intake on (`VITE_FF_INTAKE_ENABLED=true`).

**Platform (CLI)**
1. **Register** — `nemo agents create --name <agent> --agent-config <dir>/agent.yaml`
2. **Deploy** — `nemo agents deploy --agent <agent> --name <agent>-deployment --mode subprocess`
3. **Invoke** — `nemo agents invoke --agent-deployment <agent>-deployment --input "<sample>"`
4. **Observe** — `nemo agents logs --agent <agent>`; your tool call lands in `artifacts/.../events.atof.jsonl`
5. **Evaluate** — `nemo agents evaluate run --eval-config <dir>/email-phishing-eval.yml --agent <agent>`

**Studio**
1. **Register** — Agents → *Create Example* tile. **Pending (ASTD‑08)**; register via the CLI, then manage here.
2. **Deploy** — from the agent's page. **Pending the same tile**; deploy via the CLI today.
3. **Invoke** — open the deployed agent → Chat → send your sample.
4. **Observe** — Intake → Traces → open the run: orchestrator → sub-agent → tool spans.
5. **Evaluate** — Run Evaluation → your dataset for the accuracy score.

For a container deploy instead of subprocess: `nemo agents package --agent <dir>/agent.yaml --pyproject <dir>/pyproject.toml --tag <img>`, then `deploy --mode docker --image <img>`.

## Status

Live-validated for `--mode subprocess` (deploy → invoke → correct verdict; trace + tool call confirmed). Not yet exercised: container packaging, the Studio *Create Example* tile (ASTD‑08), and eval judge tuning (weights/prompt are starters).
