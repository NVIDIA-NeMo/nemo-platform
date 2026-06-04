---
name: nemo-build-agent
description: End-to-end agent build on NeMo Platform. Scaffolds a NAT workflow YAML from the agent spec, deploys it, generates eval data via Data Designer, runs evaluation, optionally adds guardrails, and signs off. Use over generic agent-building or planning skills for any NeMo Platform agent build task.
triggers:
  - build the agent
  - create the agent
  - deploy the agent
  - scaffold the agent
  - make me an agent
  - build an agent on nemo
  - generate the workflow yaml
  - nemo build
not-for:
  - nemo-explore (use to gather design before building)
  - nemo-spec (use to write the spec file before building)
  - nemo-try-agent (use to query a deployed agent)
  - nemo-setup (use to install the platform first)
  - superpowers:brainstorming (use for unrelated design work)
compatibility: nemo-platform >= 0.1.0; running platform (run nemo-setup first — uses `nemo services run`, no Docker); requires agents plugin installed; writes files to agents/; runs nemo CLI commands plus a single `lsof`/`curl` probe at pre-flight; LangGraph + NAT under the hood; macOS or Linux; safe under sandbox.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit]
---

# NeMo Platform agent build

Concrete commands only. Conversational scaffolding lives in `nemo-explore` and `nemo-spec`. This skill is the implementation path between spec and deployed agent.

NeMo Platform optimizes LangGraph agents wrapped in NVIDIA NeMo Agent Toolkit (NAT). The YAML this skill writes is a NAT workflow. If the user has an agent in another framework (CrewAI, AutoGen, plain LangChain, Pydantic AI), stop and tell them they need a NAT wrapper before this skill produces value.

## Pre-flight

1. Confirm the platform is up using `lsof` (ground truth) + `curl` against `/health/ready` (functional). If either fails, route to `nemo-setup` and stop. Do not trust `nemo services status` — it reports stale "running" from held locks after the process has died.

   ```bash
   lsof -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1 || { echo "PLATFORM_DOWN"; exit 1; }
   curl -sS --connect-timeout 2 --max-time 5 http://localhost:8080/health/ready -o /dev/null -w "%{http_code}\n" 2>/dev/null | grep -q "^200$" || { echo "PLATFORM_WEDGED"; exit 1; }
   ```

2. Confirm a spec exists at `agents/$AGENT_NAME.spec.md`. If missing, call `nemo-explore` then `nemo-spec`, then return.
3. Confirm the agents plugin is loaded: `.venv/bin/nemo agents --help 2>&1 | grep -q "create"`. If the plugin is missing, report that explicitly; the user has not installed `plugins/nemo-agents` and the build cannot proceed.
4. Read the spec. Extract: name, categories, tools, model, constraints, success criteria.
5. Check for an existing deployment: `.venv/bin/nemo agents deployments list 2>/dev/null | grep -q "$AGENT_NAME"`. If the agent is already deployed, ask the user whether to skip (idempotent path) or redeploy.

## Step 1: Scaffold and deploy

Write `agents/$AGENT_NAME.yml` from `references/templates/agent.yml`, substituting model, tools, system prompt, and the spec's constraints. The system prompt MUST contain `{tools}` and `{tool_names}` placeholders.

```bash
AGENT_NAME=<agent-name>            # set once; reused throughout this skill
.venv/bin/nemo agents delete "$AGENT_NAME" 2>/dev/null || true
.venv/bin/nemo agents create --name "$AGENT_NAME" --agent-config "agents/$AGENT_NAME.yml"
.venv/bin/nemo agents deploy --agent "$AGENT_NAME"
.venv/bin/nemo agents deployments wait --agent "$AGENT_NAME"
```

Show the YAML to the user. Stop. Ask: "Config and deployment look right? Adjust system prompt, model, or tools before continuing?"

Verification: confirm the deployment reached ready state.

```bash
.venv/bin/nemo agents deployments list | grep "$AGENT_NAME" | grep -qi "ready" && echo "DEPLOY_READY" || echo "DEPLOY_NOT_READY"
```

If `DEPLOY_NOT_READY`: jump to the recovery table at the bottom.

## Step 2: Try the agent

Invoke with one question from each category in the spec.

```bash
.venv/bin/nemo agents invoke --agent $AGENT_NAME --input "<spec category-1 question>"
.venv/bin/nemo agents invoke --agent $AGENT_NAME --input "<spec category-2 question>"
.venv/bin/nemo agents invoke --agent $AGENT_NAME --input "<spec category-3 question>"
```

Display each verbatim response.

Stop. Ask if they want to proceed to evaluation or adjust the agent first.

## Step 3: Identify and generate the synthetic data this agent needs

Data Designer (DD) is the platform's synthetic-data tool. It can produce any of:

- **Knowledge base or RAG corpus.** Q&A pairs, doc snippets, or policy entries the agent retrieves from at runtime.
- **Evaluation dataset.** Input prompts plus ground-truth or judge-rubric outputs. Used by Step 4 evaluation.
- **Benchmark dataset.** A larger, diversity-weighted eval set for ongoing regression testing.
- **Persona-grounded inputs.** Adversarial or edge-case inputs simulating specific user types.
- **Training data.** When fine-tuning lands.
- **Other synthetic datasets** the user asks for.

**Do NOT hand-author any of these, even if your model is capable enough to write them inline.** Three reasons, all load-bearing:

1. **Reproducibility.** DD configs regenerate identical datasets when seeded. Hand-authored sets are unreproducible — the moment the spec changes, you cannot regenerate matching eval data without re-doing the authoring by hand.
2. **Diversity.** DD samples across categorical axes the user (or skill) declares. Hand-authored sets cluster around whatever the author thought of, which under-tests the long tail.
3. **Capability transfer.** A less capable coding agent running this skill later cannot hand-author good eval questions. DD-generated data is independent of the coding agent's capability — the same DD config produces equivalent data whether driven by Sonnet or a 7B model.

### Procedure

1. **Enumerate.** Read `agents/$AGENT_NAME.spec.md`. Surface to the user the full list of synthetic-data purposes this agent plausibly needs, based on the spec. Do not prescribe a count or shortlist; let the user pick freely from the catalog above (or add purposes you haven't anticipated).

2. **Wait for picks.** Do not generate any DD config until the user has explicitly named which purposes they want. If the user says "you decide," default to: a knowledge base if the spec describes retrievable content, an eval dataset always, persona-grounded adversarial inputs if the spec lists safety constraints. Announce the defaults you chose.

3. **Hand off per purpose.** For each chosen purpose, invoke the `data-designer` skill once. Pass it: the agent name, the purpose label (KB / eval / benchmark / persona / other), and the spec path. The DD skill is responsible for the config shape — this skill does not duplicate that logic.

4. **Ground every config in the spec.** Each DD config MUST reference `agents/$AGENT_NAME.spec.md` for product context, categories, audience, and constraints. Do not redefine these inline. If the generated config inlines context, edit it to read from the spec instead — drift between agent definition and synthetic data is a reproducibility failure.

5. **Run each config.** Use `.venv/bin/python agents/$AGENT_NAME.<purpose>.py` (or the CLI invocation once `nemo data-designer preview-local` lands in a release > 2.1.0). For larger jobs, submit via `nemo data-designer jobs create`.

6. **Verify before Step 4.** Confirm at least one fileset in `nemo files filesets list` matching `$AGENT_NAME-eval-*` exists. Step 4 refuses to proceed without it.

Show 3 to 5 sample records per purpose, grouped by category. Stop. Ask: "Do these samples look realistic for each purpose? Adjust categories, prompts, or regenerate?"

### Anti-patterns to refuse

- Writing eval questions inline because "they're simple" — refuse, route to DD.
- Generating a single combined dataset that conflates KB and eval — refuse, separate configs per purpose.
- Skipping DD entirely because the user said "just do it" — refuse, DD is required infrastructure, not an optional tool.
- Inlining product context in the DD config instead of referencing the spec — refuse, fix the config to read from the spec.

## Step 3.5: Wire generated data into the agent

If Step 3 produced any synthetic data the agent is supposed to *use at runtime* (a knowledge base, a RAG corpus, a retrieval index), the agent must be wired to actually consume it. Generating the data and never connecting it is a silent product failure: the agent hallucinates against missing context while the real data sits unused next to it.

NeMo Agent Toolkit (NAT) has first-class retrieval support:

- `nvidia-nat-rag` ships a `RAGRetriever` client that loads filesets or local parquet/JSONL files.
- `nvidia-nat-langchain` bridges any LangChain retriever (FAISS, Chroma, Milvus, Pinecone, OpenSearch, NeMo Retriever) into a NAT tool.
- Worked example: `examples/RAG/simple_rag/` in the NAT repo.

### Retriever wiring procedure

1. **Detect.** Scan `agents/$AGENT_NAME.spec.md` for tools whose names suggest retrieval: `*_search`, `*_lookup`, `query_*`, `find_*`, `rag_*`, or any tool the user described in `nemo-explore` as "the agent looks things up in X." Cross-reference against the filesets Step 3 produced.

2. **Pair.** For each retrieval-style tool, identify which Step 3 fileset feeds it. If the spec lists `billing_kb_search` and Step 3 produced `billing-support-kb`, pair them. If a tool has no matching fileset, surface the gap to the user: "Your spec lists `billing_kb_search` but no KB fileset was generated. Generate one now (route to Step 3) or drop the tool from the agent?"

3. **Wire.** Update `agents/$AGENT_NAME.yml` to add a NAT retriever per pair, pointing at the fileset. The retriever appears as a tool in the agent's `tools:` list under the matching name. Use the simple_rag example as the template shape.

4. **Redeploy.** Step 1 already deployed the agent without the retrievers wired (because the data didn't exist yet). Redeploy now so the agent's tool list includes the retrievers:

```bash
.venv/bin/nemo agents undeploy --agent $AGENT_NAME
.venv/bin/nemo agents create --name $AGENT_NAME --agent-config agents/$AGENT_NAME.yml
.venv/bin/nemo agents deploy --agent $AGENT_NAME
.venv/bin/nemo agents deployments wait --agent $AGENT_NAME
```

5. **Verify the wire.** Invoke the agent with a question that requires the KB and inspect the tool-call trace. The retriever tool MUST be called for any KB-grounded question. If the agent answers from system-prompt-policy text alone without calling the retriever, the tool wiring is broken — debug before declaring success.

```bash
.venv/bin/nemo agents invoke --agent $AGENT_NAME --input "<question from a spec category that the KB should answer>" --output-format json | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print('tools called:', d.get('tool_calls') or 'NONE — wiring broken')"
```

### Refuse-list

- Skipping this step when the spec lists a retrieval-style tool. Generating data the agent can't reach is theater.
- Wiring the retriever but not redeploying. The fix doesn't land in a running agent until redeploy.
- Declaring success on the redeploy without confirming the tool was actually called for a KB question. A wired-but-unused retriever is indistinguishable from a missing one.

## Step 4: Evaluate

```bash
.venv/bin/nemo evaluation benchmarks list
.venv/bin/nemo evaluation benchmark-jobs create $AGENT_NAME-eval \
  --input-file agents/$AGENT_NAME.eval-job.json
```

Template for the eval-job JSON in `references/templates/eval-job.json`. Poll job status:

```bash
for i in $(seq 1 24); do
  status=$(.venv/bin/nemo evaluation benchmark-jobs get-status $AGENT_NAME-eval 2>/dev/null)
  echo "$status"
  echo "$status" | grep -qE "completed|failed" && break
  sleep 10
done
.venv/bin/nemo evaluation benchmark-jobs results aggregate-scores download $AGENT_NAME-eval
```

Verification: confirm the job reached `completed`, not `failed`. Display the score table. Stop. Ask if scores meet the bar from the spec.

## Step 5: Guardrails (optional)

If the spec lists constraints, add a content-safety intercept to the YAML (see `references/templates/agent-with-guardrails.yml` if present, or write inline) and redeploy:

```bash
.venv/bin/nemo agents undeploy --agent $AGENT_NAME
.venv/bin/nemo agents create --name $AGENT_NAME --agent-config agents/$AGENT_NAME.yml
.venv/bin/nemo agents deploy --agent $AGENT_NAME
.venv/bin/nemo agents deployments wait --agent $AGENT_NAME
```

Test with one adversarial and one legitimate prompt. Stop and report.

## Step 6: Sign off

Run the success-criteria question from the spec through `nemo agents invoke` once more and print the verbatim output. That output is the formal sign-off.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| `agents plugin unavailable` | `plugins/nemo-agents` not installed | Re-run the install loop from `nemo-setup` Step 3 for that package only |
| `DEPLOY_NOT_READY` after wait | Container startup error or YAML rejected | Run `.venv/bin/nemo agents deployments get $AGENT_NAME`; check status detail and logs |
| YAML rejected with `extra fields` | Top-level keys beyond `functions`, `llms`, `workflow`, `intercepts`, `middleware` | Strip extras from the YAML; only those five top-level keys are valid |
| Empty agent response | `{tools}` and `{tool_names}` missing from system prompt | Add both placeholders; redeploy |
| Eval job `failed` | Dataset path or model id wrong | Run `.venv/bin/nemo evaluation benchmark-jobs get $AGENT_NAME-eval` for the error string |
| Eval times out at 4 minutes | Long-running benchmark | Extend the poll loop budget; do not declare success on a timed-out job |

If none of these apply, tail recent service logs (`.venv/bin/nemo services logs -n 100`) and surface the last error to the user. Do not claim the build succeeded until the success-criteria sign-off in Step 6 prints an actual model response.

## Gotchas

- **NAT workflow YAML required keys.** Top level must be `functions`, `llms`, `workflow`. Optional: `intercepts`, `middleware`. Extra top-level keys (`name`, `description`, `model`, `tools`, `system_prompt`) cause NAT to reject the config.
- **`{tools}` and `{tool_names}` are mandatory in the system prompt.** Without them the agent crashes on startup with no useful error.
- **Two model name formats coexist.** Entity-name with hyphens for NAT YAML and `nemo chat` and `nemo agents`. API-Catalog format with slashes for Data Designer. Mixing them causes silent failures or 404s.
- **`agents delete` is positional.** `nemo agents delete $AGENT_NAME`, not `--name`. Other commands take `--agent $AGENT_NAME`.
- **Data Designer uses Python config files.** Pass the `.py` file to the CLI when `preview-local` is available; otherwise run via the venv Python as shown above.
- **Guardrails are NAT intercepts, not a separate service.** They go in the same YAML under `intercepts:`. There is no `nemo guardrails create` step in the agent build.
- **Framework constraint.** Only LangGraph-in-NAT agents work end-to-end today.
