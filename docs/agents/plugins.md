# Plugins and Skills

<a id="agents-plugins"></a>

{{platform_name}} {{ release }} is extended through Python plugins and
coding-agent skills. Plugins add runtime capabilities to the local platform.
Skills teach your coding agent how to operate those capabilities on your behalf.

## Plugin Surfaces

Plugins are Python packages discovered at startup through entry points. A plugin
can contribute one or more surfaces:

| Surface | Entry-point group | What it adds |
|---------|-------------------|--------------|
| HTTP service | `nemo.services` | FastAPI routers mounted under `/apis/<name>/...` |
| CLI | `nemo.cli` | `nemo <plugin> ...` commands |
| Job | `nemo.jobs` | Local or submitted jobs with generated `run`, `submit`, and `explain` verbs |
| Controller | `nemo.controllers` | Background reconciliation loops |
| Inference middleware | `nemo.inference_middleware` | Virtual-model request or response middleware |
| Entity | plugin code | Entity definitions stored in Entity Store |

The default first-party plugins are installed by `uv sync` and
`make bootstrap-python` through the root workspace's `enabled-plugins` group.
Install or remove custom plugins in the same environment as `nemo-platform`,
then restart local services so entry points are discovered:

```bash
nemo services run
```

## First-Party Plugins

| Plugin | Purpose |
|--------|---------|
| Agents | Manage NeMo Agent Toolkit workflows with `nemo agents` |
| Switchyard middleware | Route or translate model traffic inside virtual models |
| Guardrails | Add safety checks to model endpoints |
| Data Designer | Optional synthetic-data workflows |
| Evaluator | Optional model and agent evaluation workflows |
| Auditor | Red-teaming against deployed agents |
| Anonymizer | PII handling for training data |

## Coding-Agent Skills

`nemo setup` can install NeMo skills for supported coding agents. Skills are
not runtime services; they are instructions that help your coding agent use
the local platform correctly.

For the full list of installed skills, run:

```bash
nemo skills list
nemo skills show <skill-id>
```

The skills that drive the agent lifecycle are:

| Skill ID | Purpose |
|----------|---------|
| `nemo-setup` | Verifies the platform is installed and running. Walks the user through `make bootstrap`, `nemo services run`, the local data directory (`NMP_DATA_DIR` / `XDG_DATA_HOME`), and DB reset. Use this when the user asks to set up the platform or hits a startup issue. |
| `nemo-explore` | Design conversation that feeds into an agent spec. Use before scaffolding an agent. |
| `nemo-spec` | Writes an agent spec at `agents/<name>-spec/AGENT-SPEC.md` from the explore output. |
| `nemo-build-agent` | Scaffolds a NAT workflow YAML from the spec and deploys it. |
| `nemo-try-agent` | Sends a query to a deployed agent. |
| `nemo-status` | Read-only platform health dashboard. |
| `nemo-teardown` | Guided shutdown with confirmation. |
| `agents-optimize` | Selects a deployed agent, establishes an evaluation baseline, and suggests Switchyard routing, model swaps, skill optimization, prompt tuning, and new-model evaluations. See [Optimize Agents](optimization.md). |
| `agents-secure` | Selects a deployed agent, checks guardrail coverage, and scans recent telemetry for sensitive data. See [Secure Agents](security.md). |

Plugin-owned skills cover guardrails, evaluations, optimization, data
designer, anonymizer, and auditor. They are installed with their plugin and
appear in `nemo skills list` once the platform restarts.

Manage packaged skills with the CLI:

```bash
nemo skills list
nemo skills show agents-optimize
nemo skills install --agent claude
```

## Virtual Models and Middleware

Virtual models provide the cleanest extension point for model-path behavior. An
agent can point at one model entity while the virtual model handles routing,
translation, or guardrail middleware behind that entity.

Common middleware patterns:

- **Switchyard random routing** for strong/weak model splits.
- **Switchyard translation** for cross-format model providers.
- **Guardrails middleware** for request and response checks.

For command details, see the [Inference Gateway API Reference](../api/index.md#tag-inference-gateway)
and the [CLI reference](../cli/reference.md).

## Writing Plugins

Plugin authors use the `nemo-platform-plugin` package. A minimal plugin declares entry
points in `pyproject.toml`, implements the matching class, and restarts
`nemo services run` so the local platform discovers it.

Keep plugins local-first for OSS {{ release }}: avoid requiring a cluster,
container runtime, or external control plane for the documented launch path.
