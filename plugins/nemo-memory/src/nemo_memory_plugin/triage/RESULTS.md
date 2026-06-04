# Phase 1 smoke results

Status: Phase 1 code complete and validated. Strategic direction set
for Phase 2 (bd `mdubrinsky-7au.6`).

## Strategic reframe (after v4 smoke)

The original DESIGN.md describes a multi-judge council with
conservative-tie aggregation as the production architecture. The
Phase 1 smoke iterations showed that was the wrong abstraction. The
council is a **validation tool**, not a production shape.

The actual production goal is single-model-vote with a tuned in-house
Nemotron model that reaches Sonnet-baseline calibration. The Sonnet
baseline is the gold reference future tuned-model runs are measured
against. The council was useful to discover which models calibrate
at all (only Sonnet, in our tests) and to confirm the cheap-tier
candidates need fine-tuning, not better prompting.

See bd `mdubrinsky-7au.6` for the eval-loop work that operationalizes
this.

## Smoke evolution: v1 → v4

Four smoke runs against the same 71-entry consolidated USER.md
corpus. Each row is the aggregate council verdict distribution.

| run | council | aggregate keep | promote | refine | drop | errors | wallclock |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| v1 | sonnet 4.5 / nano-3 / kimi-k2.6 | 59% | 0% | 39% | 1% | 0 | 29 min |
| v2 | sonnet 4.5 / nano-3 / kimi-k2.6 (tightened prompt) | 92% | 3% | 4% | 1% | 2 | 28 min |
| v3 | nemotron-3-ultra / nano-omni-reasoning / super-v1-5 | 97% | 0% | 1% | 1% | 7 | 59 min |
| v4 | sonnet 4.6 / nano-3 / super-v1-5 | 90% | 6% | 3% | 1% | 0 | 47 min |

## Per-judge calibration matrix

What each individual judge proposed across runs (percentages, blank
= judge not in that council). The headline finding is in the
right-most column.

| judge | v1 | v2 | v3 | v4 | calibrated? |
| --- | --- | --- | --- | --- | --- |
| sonnet 4.5 | k44 p7 r45 d4 | k63 p17 r14 d6 | — | — | yes (v2 distribution) |
| sonnet 4.6 | — | — | — | **k41 p32 r24 d3** | yes (richer than 4.5) |
| nemotron-3-ultra | — | — | k90 p1 r4 d1 | — | mostly keep, no promote |
| llama-3-3-nemotron-super-49b-v1-5 | — | — | k97 r1 | k96 p1 r1 d1 | collapsed to keep |
| nemotron-3-nano-30b-a3b | k13 r82 | k93 p6 r1 | — | k89 p6 r1 d4 | swings with prompt |
| nemotron-3-nano-omni-30b-a3b-reasoning | — | — | k51 r3 d41 | — | wildly different from base nano |
| moonshotai-kimi-k2-6 | k94 r4 d1 | k91 p1 r4 d3 | — | — | rubber-stamp keep |

Key:
- `k` = keep, `p` = promote_to_prompt, `r` = refine, `d` = drop
- Numbers are percentages of the judge's 71 votes

## Findings

**1. Sonnet 4.6 is the only calibrated judge in any council we tested.**
It uses the full verdict space (41% keep, 32% promote, 24% refine, 3%
drop). Every Nemotron variant we tried (nano-3, nano-omni-reasoning,
super-v1-5, 3-ultra) collapses to almost-all-keep with the tightened
v2 prompt. Sonnet 4.6 also engages noticeably more than 4.5 — nearly
2x the promote rate and 70% more refines on the identical prompt.

**2. Cheap-tier Nemotron judges don't calibrate via prompt alone.**
Plain Nemotron-3-Nano under three different prompts/anchors:

| condition | keep | refine |
| --- | ---: | ---: |
| v1 loose prompt | 13% | 82% |
| v2 tight prompt | 93% | 0% |
| v4 tight prompt + Sonnet 4.6 anchor | 89% | 1% |

The candidate anchor doesn't influence Nano's decisions. The prompt
swings it between extremes: refine-everything under loose rules,
keep-everything under tight rules. Nano cannot distinguish
defect-refine from style-refine; it defaults to whichever extreme
the prompt makes safer. This is fine-tune territory, not prompt
territory.

**3. The conservative-tie aggregation rule was actively harmful.**
In v4, Sonnet 4.6 flagged 56% of entries as needing change (promote +
refine + drop). The council aggregate said 10% needed change because
Nano + Super together always voted keep and out-voted Sonnet. The
"council" right now is anti-helpful when only one judge is actually
calibrating; majority over uncalibrated judges drowns the signal.

**4. The all-Nemotron council (v3) was the worst-performing run.**
7 errors (Nemotron family has reliability issues Anthropic doesn't),
59 min wallclock, and the most extreme keep-collapse (97% aggregate
keep). Confirms we cannot ship a Nemotron-only judge today without a
fine-tune.

**5. Reliability deltas matter for production cadence.**
- Sonnet 4.5/4.6: 0 errors across 213+ calls per run.
- Kimi-k2.6: empty content at <2048 max_tokens (reasoning exhausts budget).
- Super v1-5: timeouts, invalid verdicts ("valid" not in enum), string scores.
- Nemotron-3-Ultra: malformed JSON twice in 71 calls (truncated/garbled output).
- Nano-omni-reasoning: empty content + malformed JSON in 71 calls.

Sonnet is the only judge that's reliably JSON-disciplined.

## Locked baseline

`phase1-smoke/baselines/baseline-sonnet-4-6-user.json` is the gold
reference for Phase 2 eval work. Produced by a single-judge run of
`azure-anthropic-claude-sonnet-4-6` against the consolidated USER.md
corpus, with the v2 (tightened) prompt and `max_tokens=4096`. Future
candidate-model runs diff their proposals against this baseline; the
eval primitive (bd `mdubrinsky-7au.6`) computes per-verdict agreement
rate, confusion matrix, and the disagreement set.

The earlier `phase1-smoke/triage-user-*.json` artifacts are kept as
the per-iteration record but are no longer the operative reference.

## Prompt evolution

- **v1 prompt:** loose REFINE definition ("keep the signal but rewrite
  for clarity or specificity"). Permitted any stylistic rewrite.
- **v2 prompt (current):** REFINE requires a nameable concrete defect
  from a closed list (combined topics, vague language, 2x too long).
  Explicit DO-NOT list forbids same-content paraphrase, dropping
  quotes/examples/named entities, and pure stylistic diffs. KEEP
  strengthened: "if the only improvement is rephrasing, this is the
  right verdict, not refine."

The v2 prompt change disciplined Sonnet (45%→14% refine, all of the
remaining refines name a defect per the new rules) and over-restricted
Nemotron-Nano (82%→0% refine, collapsed entirely). Both effects are
real and consistent with the calibration story above.

## What this validates

- Pipeline (adapter → council → aggregation → proposal artifact) is
  stable across 4 runs and 700+ real model calls.
- Sonnet 4.6 is the production-ready single judge. Use as the
  baseline.
- The Phase 1 exit criterion (non-keep proposal rate in 25-45% band)
  is met when measured against Sonnet 4.6 alone (56% non-keep) rather
  than the council aggregate.

## What this does not validate

- Whether Sonnet 4.6's proposals are correct in absolute terms. We
  have no human-graded ground truth; the user reviewed 5 of the v1
  disagreements and confirmed Nano's bias but did not validate
  Sonnet's calls in isolation.
- Whether a fine-tuned Nemotron can reach Sonnet's calibration. That's
  the Phase 3.5 hypothesis (bd `mdubrinsky-7au.3`).
- Cost / wallclock on tuned-model iteration. Moving the eval loop to
  omnistation is part of Phase 2 (bd `mdubrinsky-7au.6`).

## Pointers

- Locked baseline (gold reference): `phase1-smoke/baselines/baseline-sonnet-4-6-user.json`
- Per-iteration history: `phase1-smoke/triage-user.{json,md}` (v1), `triage-user-v2.{json,md}`, `triage-user-v3-allnemotron.{json,md}`, `triage-user-v4.{json,md}`
- Disagreement review template (v1): `phase1-smoke/disagreement-review.md`
- Smoke driver: `plugins/nemo-memory/examples/triage/triage.py`
- Design doc: `DESIGN.md` (Phase 0 contract, original council shape that the smoke superseded)
- bd: `mdubrinsky-7au` (parent), `.1` (Phase 1, closed), `.3` (judge fine-tune corpus), `.4` (reword exit criterion), `.5` (Intake annotations shim), `.6` (judge eval loop, current)
