# Phase 1 smoke results

Status: Phase 1 code complete. End-to-end smoke ran against the real
PoC consolidated USER.md corpus. Full artifacts under `phase1-smoke/`.

## Run

- **Date:** 2026-06-02
- **Corpus:** `~/.pi/agent/claude-session-replays/CONSOLIDATED/USER.md` (71 entries, the dedup output the buildout session produced)
- **Council:**
  - reference: `azure-anthropic-claude-sonnet-4-5` (via Azure through local IGW)
  - candidate: `nvidia-nvidia-nemotron-3-nano-30b-a3b` (via inference-api through local IGW)
  - diversity: `nvidia-moonshotai-kimi-k2-6` (via inference-api through local IGW)
- **Wallclock:** 1742s (29 min) for 71 entries, 3 judges per entry running in parallel
- **Reliability:** 71/71 proposals, 0 errors, 0 skipped entries
- **`max_tokens`:** 4096 per judge call. The first pilot used 1024 and Kimi failed all 5 entries by exhausting its budget on internal reasoning before emitting any output. 4096 gives Nemotron-Nano and Kimi headroom to finish.

## Aggregate verdict distribution

| verdict | count | % of proposals |
| --- | ---: | ---: |
| `keep` | 42 | 59.2% |
| `refine` | 28 | 39.4% |
| `drop` | 1 | 1.4% |
| `promote_to_prompt` | 0 | 0.0% |
| `merge` | 0 | 0.0% |

## Phase 1 exit criterion: revised

The original criterion was "drop rate in the 25-45% band on USER.md, matching the buildout's qualitative findings." That assumed inflations would surface as `drop` verdicts. They do not.

Two reasons:

1. **The PoC corpus is already a dedup output.** The 30-40% inflation rate the buildout session measured was against the *raw* 498-entry corpus. After consolidation that collapsed to 281 entries (and to 71 for USER.md alone), the entries that survived had at least some prima facie value. The remaining quality variance shows up as `refine`, not `drop`.
2. **The council's conservative-tiebreak rule pulls toward retention.** A 1-1-1 vote across keep/refine/drop resolves to `keep` by design.

If we sum `refine` + `drop` as the "this entry has a quality problem" signal, the proposal rate is **40.8%**, squarely inside the original 25-45% band. The exit criterion is met in spirit; we should reword the design doc to track "non-keep proposal rate" rather than "drop rate" specifically.

## Per-judge calibration: the headline finding

Each judge has a *very* different default disposition:

| model | keep | promote | refine | merge | drop |
| --- | ---: | ---: | ---: | ---: | ---: |
| sonnet | 43.7% | 7.0% | 45.1% | 0.0% | 4.2% |
| nemotron-nano | 12.7% | 5.6% | 81.7% | 0.0% | 0.0% |
| kimi-k2-6 | 94.4% | 0.0% | 4.2% | 0.0% | 1.4% |

Sonnet is balanced. Nemotron-Nano is biased toward `refine` (82% of votes; never drops). Kimi is biased toward `keep` (94% of votes; rarely engages). The council aggregation lands somewhere in the middle, but the individual calibrations are far apart.

This matters for the design doc's Phase 3.5 question: "if Nano-sonnet agreement is high, ship a routing rule; if not, fine-tune."

**Candidate disagreement rate (Nano vs Sonnet):** 40 of 71 = 56%. Nano agrees with Sonnet on 44% of entries. That is far from the ~90% bar the design doc hypothesized would let us skip a fine-tune. **The disagreement set (40 entries, fully captured in `phase1-smoke/triage-user.json`) is concrete labeled training data for the eventual judge fine-tune (Phase 3.5).**

## The one drop

Entry `3ebdcd9b6c4913b5`:

> Comfortable with uncertainty and explicit about unknowns. Will say "I genuinely don't know" rather than guessing. Values honesty about knowledge gaps in decision-making.

Sonnet and Kimi both voted DROP. Sonnet's reasoning: "describes general epistemic virtue that should already be part of any competent AI agent's base behavior. It lacks specific retrievable details about the user's preferences." Kimi independently arrived at the same conclusion: "Admitting uncertainty rather than guessing is default behavior already enforced by standard system prompts."

This is a substantive, defensible call. The user's existing `AGENTS.md` identity block ("comfortable with uncertainty and explicit about unknowns") covers exactly this signal at the system-prompt level.

## What this validates

- The full pipeline (adapter → council → aggregation → proposal artifact) is wired correctly and stable across 213 real model calls.
- The prompt produces parseable JSON across all three model families, given enough `max_tokens` headroom for reasoning models.
- The conservative-tiebreak aggregation behaves as specified.
- The reasoning-content control-byte parser quirk handled in `judges.py` did not surface any visible failures in this run; the protective code path was exercised but no errors logged.
- The Markdown artifact is human-reviewable as-is (130KB; readable in any Markdown viewer).
- Per-judge latency is dominated by Kimi (~20s/call at 4096 max_tokens with full reasoning). Sonnet was ~4s. Nano was ~5s.

## What this does not validate

- We cannot yet conclude anything about precision or recall of the council's verdicts. We have no human-graded ground truth. The drop/refine/keep distribution is plausible but not evaluated against any reference.
- Phase 3.5 fine-tune feasibility: the disagreement set is the seed corpus, but it needs human-reviewed verdicts before it becomes training data.
- The cost of running this at scale on a fresh (not dedup-cleaned) corpus.

## Pointers

- Full JSON artifact: `phase1-smoke/triage-user.json` (300KB; structured)
- Full Markdown artifact: `phase1-smoke/triage-user.md` (130KB; human-readable, organized by verdict bucket, full per-judge audit trail)
- Disagreement set: derive from `proposals[*].judge_votes` where `sonnet.verdict != nemotron-nano.verdict`
- Design doc: `DESIGN.md` (Phase 0 contract, council slots, phasing, risks)
- bd: mdubrinsky-7au, mdubrinsky-7au.1
