---
name: nemo-model-selection
description: Recommends an LLM for a NeMo Platform agent based on what the agent actually has to do, explained in plain English before any benchmark name appears. Use when the user is choosing a model for a new agent, asking which model to use, or unsure what to put in their spec or NAT workflow YAML. Invoked by nemo-explore at the model question; also runs standalone when the user starts mid-flow.
triggers:
  - which model should I use
  - what model is best for this
  - help me pick a model
  - recommend a model
  - I don't know what model to use
  - model selection
  - which LLM
not-for:
  - nemo-explore (use first to capture the agent's job, audience, and tools)
  - nemo-spec (use to persist the design once model is chosen)
  - nemo-build-agent (use to scaffold the YAML once the spec is signed off)
compatibility: nemo-platform >= 0.1.0; read-only; loads references/benchmark_cache.json if present; works offline; safe under any sandbox.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Bash]
---

# NeMo Platform model selection

Recommends a NIM model for a new agent. Plain-English first, benchmark numbers second, never the other way around. Output: one recommended model with a one-sentence reason, ready to drop into a spec or NAT workflow YAML.

## Pre-flight

Load the benchmark cache if it exists. The cache adds fresh scores and richer per-model "strong at" / "watch out for" wording to the static knowledge below.

```bash
test -f packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-model-selection/references/benchmark_cache.json && echo "cache_present" || echo "cache_missing"
```

If `cache_missing`, proceed with the static table in this file. Tell the user once that benchmark data is stale and they can refresh it with:

```bash
python scripts/refresh-benchmark-cache.py
```

## Step 1 — Profile the agent

Ask all three questions in a single message. Skip any that the conversation has already answered (for example, `nemo-explore` already captured tools and deployment).

```
Before I recommend a model, three quick things about what the agent will do:

1. **Tool density.** How many tools, and how do they interact?
   - One tool (search, lookup, or similar)
   - 3–5 tools whose outputs chain into each other
   - Many tools, often called in parallel

2. **Primary capability.** What does the model spend most of its time doing?
   - Calling APIs or tools reliably (MCP, structured function calls)
   - Working with code (reading repos, editing, writing patches)
   - Reading and reasoning over long documents
   - General conversation and instruction following

3. **Deployment.**
   - Cloud (NVIDIA Build API, OpenAI, Anthropic, etc.)
   - Self-hosted on a GPU — if so, roughly how much VRAM is available?
   - Not decided yet
```

Do not propose a model before all three answers are in. Push back on "you decide" — commit to a default and announce it ("I'll assume cloud and a tool-heavy agent. Tell me if that's wrong.").

## Step 1.5 — Pick a presentation pattern based on evidence quality

The cache marks each benchmark score with `source: "direct"` or `source: "inferred_from_ancestor"`, and carries `intent_hints` for models with no benchmark coverage. Pick the presentation pattern based on what's available for the candidate model that best matches the user's profile answer to question 2 (primary capability).

```
Identify the candidate model that best matches the profile.
Inspect scores.<primary_axis>.source for that candidate, where primary_axis is:
  - "code"               → scores.arena_elo.coding  AND  scores.bfcl_v4
  - "tools"              → scores.bfcl_v4
  - "long documents"     → scores.arena_elo.hard_prompts
  - "general/instruction"→ scores.arena_elo.overall AND scores.arena_elo.instruction_following

If the relevant scores all have source == "direct":
  → Pattern A (single recommendation, current Step 2 template)

If one or more relevant scores have source == "inferred_from_ancestor",
or the candidate has scores == {} but has intent_hints:
  → Pattern B (forced trade-off, withhold model name until user resolves it)

If 3+ candidates have similar profiles and similar evidence-quality:
  → Pattern C (shortlist with explicit "I'd want an eval before deciding")
```

### Pattern B — forced trade-off

**Hard rule: when the primary candidate's evidence is anything other than `direct`, the model name does NOT appear in your response until the user has resolved the trade-off.** This is the anchoring guard. Without it, users default to the first model named regardless of caveats.

Structure:

1. State that there's a trade-off to settle before naming a model.
2. Present exactly two candidates labeled A and B (NOT named):
   - **A. The matched specialist** — the candidate that best fits the profile by name/intent, with its inferred/missing-data caveat.
   - **B. The measured generalist** — the model with the strongest *direct* score on the same primary axis, even if less specialized.
3. For each, summarize the `plain` text from the cache (which already carries the editorial caveat for inferred entries) in your own words.
4. Recommend a 5–10 prompt eval from the user's spec on both as the "real answer."
5. If the user can't run an eval, ask: which framing of your priority is right — A's specialist intent or B's measured discipline?
6. **Only after the user picks** — name the chosen model and proceed to Step 2's recommendation template (skipping the model-selection paragraph since it's resolved).

Example output for a code-heavy agent where the natural pick has inferred BFCL data:

> "Before I name a model — one thing to settle. Your profile (code-focused, three tools, cloud) has two reasonable candidates with different evidence quality:
>
> **A. The specialist.** Built for this exact job. Arena's coding-category Elo (1418, strong) IS measured for this exact model. *But BFCL hasn't measured its tool-calling discipline — only its base model (Qwen3-30B-A3B at 37%) and we're inferring from there.*
>
> **B. The measured generalist.** Best directly-measured tool-calling in our NIM set (BFCL 52%, mid). Not code-specialized, but disciplined.
>
> If you can run a 5–10 prompt eval from your spec on both, that's the real answer. If you need to commit now: which matters more — specialist intent (A) or measured discipline (B)?"

### Pattern C — shortlist (rare)

Use only when 3+ candidates have similar profiles and similar evidence-quality, and no honest trade-off binary exists. Present them in a numbered list with `plain` summaries and **explicit phrasing that an eval is the only way to actually decide.** Do not commit to one. Default to recommending an eval as the next step.

## Step 2 — Recommend in plain English

Lead with the *capability that matters most for this agent*, then name the model as the conclusion. Use this shape (adapt the content, do not copy verbatim):

> "For an agent that <restate what the user described>, the thing that matters
> most is <one capability in plain words — e.g. 'reliably picking the right
> tool without hallucinating its arguments'>. That's what <model shortname> is
> built for — <one sentence on what the model actually does well, not what it
> scored>. The tradeoff is <honest caveat>. Given you're deploying <cloud /
> self-hosted>, **`<model string>`** is the practical choice."

### Recommendation table

| Agent profile | Recommended model |
|---|---|
| Many tools, parallel or chained calls | `qwen/qwen3-235b-a22b` |
| Many tools, cost or speed is a constraint | `qwen/qwen3-30b-a3b` |
| Code-focused: reading repos, writing patches | `qwen/qwen3-coder-30b-a3b-instruct` |
| Reasoning over long documents or many chunks | `nvidia/llama-3.1-nemotron-ultra-253b` |
| General-purpose, balanced default (platform-curated) | `nvidia/llama-3.3-nemotron-super-49b-v1` |
| General-purpose, widely-deployed alternative | `meta/llama-3.3-70b-instruct` |
| Fast and cheap, simple tool loops | `microsoft/phi-4-mini-instruct` |
| Self-hosted, single consumer GPU (<24 GB) | `qwen/qwen3-8b` |

### What each model is strong at

If `benchmark_cache.json` is present, read each model's `strong_at` and `watch_out_for` from the cache — those are kept in sync with the script. The text below is the fallback when the cache is missing.

**qwen/qwen3-235b-a22b**
- Correctly calls multiple tools in a single turn without mixing up arguments
- Handles parallel tool invocation where call order matters
- Recovers gracefully when a tool returns an error instead of hallucinating a result
- Watch out for: heavy VRAM footprint for self-hosting; overkill for single-tool agents

**qwen/qwen3-30b-a3b**
- High-throughput tool calling at low inference cost (sparse MoE, ~3B active params)
- Good baseline before you know whether you need the larger model
- Watch out for: lower ceiling on complex nested tool chains

**qwen/qwen3-coder-30b-a3b-instruct**
- Navigates unfamiliar codebases and makes targeted edits
- Agents that interact with git, CI, or code-review workflows
- Watch out for: general reasoning suffers from the specialization

**nvidia/llama-3.1-nemotron-ultra-253b**
- Follows threads across very long documents without losing context
- Multi-step reasoning over dense technical material
- Watch out for: slower inference; cloud API is the practical deployment path

**nvidia/llama-3.3-nemotron-super-49b-v1**
- The platform's curated default for cloud agents — well-tested across the build path
- Balanced: solid tool-calling, solid prose, no glaring weakness
- Watch out for: a specialist will beat it on heavy tool chains or hard code tasks

**meta/llama-3.3-70b-instruct**
- Reliable across a wide range of tasks with well-characterized behavior
- Good starting point when you don't yet know where the bottleneck will be
- Watch out for: not a specialist — pick one if tool-calling or code quality is critical

**microsoft/phi-4-mini-instruct**
- Fast, cheap inference for latency-sensitive agents or high-volume loops
- Fits on small hardware for edge or resource-constrained deployments
- Watch out for: lower ceiling for complex multi-tool orchestration

**qwen/qwen3-8b**
- Tool calling on a single consumer GPU (fits in 12–16 GB VRAM)
- Best choice for local development and prototyping
- Watch out for: not competitive on complex reasoning; context reliability drops faster

## Step 3 — Mention the evidence only after the plain-English case

After explaining the recommendation, briefly note *how we know* — framed as "the test that simulates this" not "the score it got".

Right framing:
> "We know this because it consistently outperforms comparable models on tests
> that simulate exactly this kind of multi-tool coordination — not toy examples,
> but real scenarios where the model has to decide which tool to call, in what
> order, with what arguments, and when to call nothing at all."

Wrong framing (do not do this):
> "It scored 0.91 on BFCL v4, which is top tier, and 1342 Arena Elo."

If the user asks what benchmark was used or wants the raw number, tell them. Do not lead with it.

## Step 4 — Output

Two ready-to-paste blocks. Show whichever fits the user's stage. **When the chosen model's primary-axis score has `source: "inferred_from_ancestor"` or the model relies on `intent_hints` only, include an explicit evidence caveat in the output** — don't let the spec or YAML carry the recommendation forward without surfacing the inference.

If they're authoring an agent spec for `nemo-spec`:

```markdown
## Model

- **Family/size:** <plain description, e.g. "Qwen3 235B MoE">
- **NIM model id:** `<model-string>`
- **Why this choice:** <one plain-English sentence — same words you used above>
- **Evidence:** <"Direct BFCL and Arena measurements" | "BFCL inferred from ancestor <ancestor-id>; Arena measured directly" | "No public benchmark coverage — selection based on model-name intent only, eval recommended">
- **Deployment:** <cloud | self-hosted (VRAM)>
```

If they're editing a NAT workflow YAML directly (e.g. tweaking the `agent.yml` `nemo-build-agent` produced):

```yaml
llms:
  primary_llm:
    _type: nim
    model_name: <model-string>
    # Chosen because: <one plain-English sentence — same words you used above>
    # Evidence: <direct | inferred from <ancestor-id> | name-intent only — eval recommended>
    max_tokens: 4096

workflow:
  _type: <agent_type>
  llm_name: primary_llm
  tool_names: []
```

### Pair the model with the right agent type

| What the agent needs to do | Use |
|---|---|
| Call tools in a loop, observe results, adjust | `react_agent` |
| Dispatch tools directly without intermediate reasoning | `tool_calling_agent` |
| Reason through a problem before acting | `reasoning_agent` |
| Follow a fixed plan with no dynamic re-planning | `rewoo_agent` |

## Step 5 — Staleness notice

End with:

```
These recommendations reflect benchmark data current as of this skill's last
cache refresh. LLM rankings shift often. To pull fresh scores:

    python scripts/refresh-benchmark-cache.py

Raw leaderboards:
  Tool calling:        https://gorilla.cs.berkeley.edu/leaderboard.html
  Human preference:    https://lmarena.ai
                       (live Elo data: huggingface.co/datasets/lmarena-ai/leaderboard-dataset)
```

## Verification

This skill writes nothing. Verification is conversational: summarize the recommendation in 3 lines (capability that mattered most, model chosen, one tradeoff) and ask "Does this match what you need?" Do not hand off until the user confirms.

If `nemo-explore` invoked this skill, return control to `nemo-explore` with the chosen model so it can continue to the constraints question. If the user invoked standalone, hand off to `nemo-spec` if they want to persist the design.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| User says "wrong recommendation" | One of the three profile answers was misread | Re-ask just that question; do not restart |
| User wants a model not in the table | The table is curated, not exhaustive | Tell them honestly; describe the capability gap their choice would have vs the closest recommended model |
| `cache_missing` and user wants fresh data | Cache has never been refreshed in this checkout | Tell them the refresh command and note that the static table is still usable |
| User picks self-hosted but the recommended model needs cloud | Hard constraint conflict | Drop the recommendation; pick the closest self-hosted-compatible model from the table |

## Hard rules

- Never name a model before all three profile questions are answered.
- Never lead with a model name, benchmark name, or score.
- Never recommend a cloud-only model when the user said self-hosted.
- Never write `model_name` (YAML) or "NIM model id" (spec) without showing the plain-English reason alongside it.
- **When the primary candidate's evidence is anything other than `direct`, the model name does not appear in your response until the user has resolved the trade-off in Pattern B.** Anchoring is the failure mode this guards against — users default to the first model named regardless of caveats. The withhold is non-negotiable.
- When emitting the spec or YAML block, always include an Evidence line/comment naming the source quality. Inferred or name-only choices that propagate downstream without that signal mislead the build skill and the user both.

## Gotchas

- **"You decide" needs a committed default, not a silent fill-in.** Same rule as `nemo-explore`. Pick something, name it, tell the user.
- **The platform default is `nvidia/llama-3.3-nemotron-super-49b-v1`.** If `nemo-explore` already captured "cloud, no preference", you can route there without re-profiling — but still explain *why* in plain English instead of just naming it.
- **Two model name formats coexist.** Entity-name with hyphens for NAT YAML / `nemo chat` / `nemo agents`. API-Catalog format with slashes for Data Designer. Use the slashed form (`qwen/qwen3-235b-a22b`) in NAT YAML for cloud NIMs; the build skill converts when needed.
- **Watch the deployment column.** A 235B cloud-API recommendation aimed at a self-hoster with a 24 GB GPU is the most common mismatch and the easiest to catch by re-reading Step 1.
