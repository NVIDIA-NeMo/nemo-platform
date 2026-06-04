# Memory triage — design doc

Status: draft, pre-implementation. Tracks bd issue `mdubrinsky-7au`.

## Problem

Agent memory stores accumulate two pathologies the existing `improvement/`
loop doesn't address:

1. **Inflation**: model-written entries dressed as user preferences with no
   specific evidence behind them. The PoC at
   `~/projects/personal/claude-session-poc/` measured ~30-40% inflation in
   USER.md after a multi-model dedup pass over 90 sessions.
2. **Restatement**: entries that duplicate something already covered by the
   surrounding system prompt or `AGENTS.md` block, so they retrieve noise
   without changing behavior.

The existing improvement lever (skills under `.agents/skills/`) can't fix
either. We need memory as a first-class artifact the loop reasons about.

## Scope (Phase 0, locked)

- **Eval-time only.** The target is whatever memory store the agent under
  eval owns. Developer-local stores (e.g. `~/.pi/agent/pi-hermes-memory`)
  are explicitly out of scope. The personal PoC stays where it is for that
  use case.
- **Harness-agnostic.** The triage step consumes `TraceSummary` + memory
  entries, never raw runner-specific shapes. The existing `TraceParser`
  protocol is the seam.
- **Proposal-only mutation contract.** Memory writes are staged for human
  review. Memory strategies do not expose `apply()`, only `propose()`. This
  is a hard architectural rule, not a config flag.

## Non-goals

- Mutating pi-hermes-memory or any other developer-local store.
- Auto-applying memory changes in CI or any loop.
- Replacing the existing skills-optimization strategy. Memory is a new
  lever next to it, not a substitute.
- Fine-tuning a judge model in the first cut. Tuning happens after the
  flow generates labeled data, not before.

## Two flows

The issue conflates two related things. They share primitives but ship
separately.

**Flow A — Memory as a new improvement lever.**
Eval cluster signals trigger a `MemoryStrategy` that proposes
add/edit/drop on the agent-under-test's memory store. Plugs into
`improvement/strategies/` next to `SkillsOptimizerStrategy`. Closes the
eval loop with memory as the artifact.

**Flow B — Post-trajectory memory triage.**
A standalone job consumes a memory store and a corpus of trajectories,
runs the consolidate/distill pipeline, emits a triage report
(keep / merge / refine / drop / promote). Does not require failing
evals. Runs on volume, on a slow cadence.

Build Flow B first. It is the cheapest path to value and produces the
labeled corpus we'll need before Flow A's hypotheses are useful.

## Council models (Phase 1, locked)

Three judges run in parallel against each entry. Votes aggregate into a
single proposal with per-model breakdown preserved for inspection.

| Slot | Model | Role |
| --- | --- | --- |
| Reference | `claude-sonnet-4-5` | Quality bar; the PoC's effective ground truth |
| Candidate | `nvidia/nemotron-3-nano-30b-a3b` | Cheap judge under evaluation. Agreement rate with sonnet becomes the fine-tune signal later. |
| Diversity | `nvidia/moonshotai/kimi-k2.6` | Different lineage than Nemotron's Llama base. In shipping switchyard presets. |

**Parsing note.** Nemotron-nano (and similar reasoning models) sometimes
emit raw control bytes inside `reasoning_content`. The judge response
parser must use `json.loads(..., strict=False)` or strip C0 controls
before parsing. This is documented in `.agents/skills/nemo-inference/SKILL.md`
and bites elsewhere in the repo today.

**Reasoning-effort budget.** Nano needs `max_tokens >= ~200` for
reasoning models per the same skill doc. Use the existing switchyard
`LLMBackendTuning` config rather than re-inventing per-call tuning.

## Architecture

### Seams

```
improvement/
├── memory/                         (new)
│   ├── DESIGN.md                   (this file)
│   ├── store.py                    MemoryEntry, MemoryStore protocol
│   ├── triage.py                   Council orchestration
│   ├── judges.py                   Per-model judge wrappers
│   ├── proposal.py                 MemoryProposal, aggregation
│   ├── report.py                   JSON + Markdown artifact emitters
│   └── adapters/
│       └── pi_hermes.py            Read-only adapter for the PoC corpus
└── strategies/
    └── memory.py                   (Phase 3) MemoryStrategy(ImprovementStrategy)
```

### Contracts

```python
class MemoryEntry:
    id: str
    content: str
    source_session_ids: list[str]     # for seen-in-N corroboration
    created_at: datetime
    last_used_at: datetime | None     # populated if the store tracks retrieval
    tags: dict[str, str]

class MemoryStore(Protocol):
    name: str                          # e.g. "pi-hermes-memory", "nat-agent-memory"
    def list_entries(self) -> Iterable[MemoryEntry]: ...
    def get(self, entry_id: str) -> MemoryEntry: ...
    # No write methods. Mutation goes through MemoryProposal artifacts only.

class MemoryProposal:
    entry_id: str
    verdict: Literal["keep", "merge", "refine", "drop", "promote_to_prompt"]
    merge_with: list[str] = []         # other entry IDs when verdict=merge
    refined_text: str | None = None    # set when verdict in {merge, refine}
    quality_score: float               # 0..1, from judge aggregate
    necessity_score: float             # 0..1, "would behavior change without this"
    confidence: float                  # 0..1, judge agreement strength
    judge_votes: dict[str, Judgment]   # keyed by model name; full per-judge record
    justification: str                 # human-readable summary

class Judgment:
    model: str
    verdict: str
    quality: float
    necessity: float
    raw_response: str                  # full text, for audit
    elapsed_sec: float
```

### Aggregation rule

The aggregate verdict is the majority across 3 judges. Ties resolve to
the more conservative verdict (keep > refine > merge > drop). Confidence
is the fraction of judges in agreement. Any entry where the candidate
judge (Nano) disagrees with the reference judge (sonnet) gets logged to
a disagreement set; that set is the seed corpus for the eventual
fine-tune.

## Phasing

### Phase 1 — Primitives, no CLI

Build `memory/store.py`, `triage.py`, `judges.py`, `proposal.py`,
`report.py`, plus the `pi_hermes.py` adapter so we can exercise against
the existing 281-entry `CONSOLIDATED/` corpus without inventing new
data.

Tests assert: council runs end-to-end against a small fixture; reasoning-
content control-char inputs parse without raising; aggregation honors
the conservative-tie rule; disagreement logging populates.

Exit when: `python -m nemo_memory_plugin.triage.triage`
(or equivalent) produces a proposal artifact from the PoC corpus that
matches the buildout's qualitative findings (drop rate in the 25-45% band
on the USER corpus).

### Phase 2 — Standalone job: `nemo memory triage`

Wire Flow B as a NemoJob with `run / submit / explain` verbs, following
the existing `optimize-skills` shape. Spec-file driven. Inputs: a
`MemoryStore` reference and a trajectory corpus pointer. Output: a
proposal artifact written to the platform files service (or a local
path in dev mode).

No eval suite required for this verb. This is the offline garbage
collection pass.

Exit when: a user can run `nemo memory triage run --spec-file
triage.yml` against an agent's memory store and get a reviewable
proposal artifact, with the council audit trail intact.

### Phase 3 — `MemoryStrategy` plugged into the improvement loop

Add `strategies/memory.py` implementing `ImprovementStrategy.writable_paths`
+ `render_prompt`. Extend `analysis/llm.py`'s prompt to advertise memory
as a lever and add `memory_missing`, `memory_inflated`, `memory_misfiring`
to `GapCategory`. The loop's "apply" step for memory hypotheses emits
proposals; it does not invoke a coding agent.

Exit when: an eval batch with a memory-flavored failure produces a staged
memory proposal alongside the existing skills proposals, and the loop
re-verifies correctly when the operator accepts the proposal.

### Phase 3.5 — Judge fine-tune (conditional)

If by end of Phase 2 the Nano-sonnet agreement rate is below ~90% on
high-confidence verdicts, kick off a fine-tune job using the
disagreement-set artifact as training data. The customizer plugin
handles the actual training run. Output: a tuned Nano checkpoint that
ships as a council judge alongside the base Nano (or replaces it).

If agreement is already high, Phase 3.5 collapses to "ship a routing
rule that calls sonnet only when the cheap judges disagree." That's a
switchyard config, not a customizer job.

### Phase 4 — Closing the loop

Use Phase 2's triage output as input to Phase 3's hypotheses. A high-
quality, rarely-used entry is a candidate for "promote to system
prompt." A repeatedly-flagged inflation is signal that the agent's
memory-writing prompt itself needs hardening. Out of scope until Phases
1-3 land and we have data to reason about.

## Risks

1. **Judge cost at scale.** Mitigated by Flow B's offline cadence and
   the routing-rule fallback if Nano agrees with sonnet often enough.
2. **No NAT-native memory primitive today.** The improvement loop's
   current agent-under-test is Claude Code. For Flow A to be useful on
   a NAT agent we need a memory primitive in NAT or a NAT-side adapter.
   Tracked separately; doesn't block Phases 1-2.
3. **Eval suite gap.** Nothing under `tests/agentic-use/` is gated on
   durable memory being correct. Phase 3 will need a small set of
   memory-sensitive evals or its hypotheses will have no signal to fire
   on. File as a follow-on bd issue when Phase 2 lands.
4. **Trajectory volume.** The PoC needed ~90 sessions to surface
   inflation patterns. Single-batch eval runs may not produce enough
   signal for Flow B to be useful per-batch. Flow B is cross-batch by
   default; treat single-batch invocations as best-effort.

## Open questions (do not need answers to start Phase 1)

- Where does the proposal artifact live? Files service vs git-tracked
  vs both? Probably files service for archive + a CLI command to fetch
  to a local review file.
- Does the proposal UI live in Studio, or is CLI-only enough for the
  POC? Phase 2 ships CLI-only; Studio integration is a follow-on.
- Should the council vote on quality and necessity as separate dimensions
  or as a single verdict? Current shape keeps them separate; if judges
  consistently couple them in practice we can collapse.

## References

- bd issue: `mdubrinsky-7au`
- PoC scripts: `~/projects/personal/claude-session-poc/`
  (`replay.mjs`, `consolidate.mjs`, `distill.mjs`)
- Consolidated corpus: `~/.pi/agent/claude-session-replays/CONSOLIDATED/`
- Existing improvement loop: `plugins/nemo-agents/src/nemo_agents_plugin/improvement/`
  (`README.md`, `loop.py`, `analysis/llm.py`, `strategies/`)
- Reasoning-content parsing quirk: `.agents/skills/nemo-inference/SKILL.md`
- Switchyard random-routing presets:
  `plugins/nemo-switchyard/vendor/switchyard/switchyard/lib/factories/random_routing/random_routing_presets.py`
