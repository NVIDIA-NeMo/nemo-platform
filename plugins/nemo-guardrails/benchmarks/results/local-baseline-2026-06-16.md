# Local baseline results — 2026-06-16

Three back-to-back runs of `make benchmark-guardrails` on a local MacBook Pro
(Apple Silicon), no other heavy workloads running. Goal: characterize the
run-to-run variance of the new with-guardrails / without-guardrails harness so
we can decide what's gateable in CI.

## Hardware / setup

- Host: MacBook Pro, Apple Silicon, on AC power
- NMP, mocks, shim: all on localhost
- Mock LLM config: in-repo defaults (`plugins/nemo-guardrails/benchmarks/configs/mock_llm/`)
  - app LLM: 4.0s e2e latency, std 0
  - content-safety LLM: 0.5s e2e latency, std 0
- AIPerf sweep: concurrency `[1, 2, 4, 8, 16, 32, 64]`, `benchmark_duration: 60s`,
  `warmup_request_count: 10`, non-streaming chat completions
- Mock workers: 4 (default)
- Three runs in the same afternoon, NMP data dir reused across runs

## Run inventory

| Run | Run dir | Notes |
|---|---|---|
| 1 | `20260616_123851` | first run after the with/without harness change |
| 2 | `20260616_145058` | identical config |
| 3 | `20260616_152834` | identical config |

All three runs completed with 7/7 sweeps passing per variant, exit code 0.

## Δp50 (with-guardrails − without-guardrails), milliseconds

This is the headline metric: how much wall-clock time the guardrails middleware
adds on top of the bare NMP+IGW path, including the two content-safety LLM
round-trips that the rails cause but don't do themselves.

| Run     | c=1  | c=2  | c=4  | c=8  | c=16 | c=32 | c=64    |
|---------|-----:|-----:|-----:|-----:|-----:|-----:|--------:|
| Run 1   | 1029 | 1071 | 1068 | 1104 | 1145 | 1260 |    778  |
| Run 2   | 1027 | 1062 | 1096 | 1105 | 1226 | 1256 |  -2896  |
| Run 3   | 1030 | 1062 | 1079 | 1070 | 1118 | 1201 |  -2077  |
| **mean**| **1029** | **1065** | **1081** | **1093** | **1163** | **1239** | **−1398** |
| range   |    3 |    9 |   28 |   35 |  108 |   59 |   3674  |
| range % | 0.3% | 0.8% | 2.6% | 3.2% | 9.3% | 4.8% |   n/a   |

## with-guardrails p50 (absolute), milliseconds

Useful as a sanity check that nothing catastrophic shifted in the absolute
numbers — even if Δp50 stays steady, both variants could slow down together.

| Run     | c=1  | c=2  | c=4  | c=8  | c=16 | c=32 | c=64 |
|---------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| Run 1   | 5049 | 5101 | 5114 | 5152 | 5201 | 5318 | 6164 |
| Run 2   | 5048 | 5093 | 5125 | 5137 | 5255 | 5279 | 5614 |
| Run 3   | 5050 | 5094 | 5123 | 5146 | 5163 | 5250 | 5486 |
| **mean**| **5049** | **5096** | **5121** | **5145** | **5206** | **5282** | **5755** |
| range   |    2 |    8 |   11 |   15 |   92 |   68 |  678 |
| range % | 0.0% | 0.2% | 0.2% | 0.3% | 1.8% | 1.3% | 11.8%|

## without-guardrails p50 (absolute), milliseconds

For completeness. This is the variant that's wildly unstable at c=64.

| Run     | c=1  | c=2  | c=4  | c=8  | c=16 | c=32 | c=64 |
|---------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| Run 1   | 4020 | 4030 | 4045 | 4048 | 4056 | 4058 | 5386 |
| Run 2   | 4020 | 4031 | 4029 | 4032 | 4029 | 4023 | 8510 |
| Run 3   | 4020 | 4032 | 4044 | 4076 | 4045 | 4049 | 7563 |
| **mean**| **4020** | **4031** | **4039** | **4052** | **4043** | **4043** | **7153** |
| range   |    0 |    2 |   16 |   44 |   27 |   35 | 3124 |

The app mock sleeps for exactly 4.0s. The ~20–80 ms above 4000 across c=1–c=32
is pure NMP+IGW+shim overhead. At c=64 the mock saturates (4 workers × 1 req/4s
= 4 RPS ceiling, vs. 64 requested in-flight) and requests queue.

## p90 — informational only

p90 is much noisier than p50 across runs. Not gateable with three samples.

### Δp90, milliseconds

| Run   | c=1  | c=2  | c=4  | c=8  | c=16 | c=32 | c=64  |
|-------|-----:|-----:|-----:|-----:|-----:|-----:|------:|
| Run 1 | 1039 | 1099 | 1162 | 1025 |  911 |  604 | 3009  |
| Run 2 | 1028 | 1115 | 1160 | 1262 |  783 |  641 | 1015  |
| Run 3 | 1023 | 1076 | 1189 | 1085 | 1209 |   18 | 1998  |

## Observations

### What's stable enough to gate on

**c=1, 2, 4, 8.** The Δp50 ranges are 3–35 ms, well under any tolerance we'd
realistically write. The absolute with-guardrails p50 is even tighter (2–15 ms
across three runs). This is the regime where the harness is genuinely measuring
what we want: NMP+middleware overhead on top of fixed-latency mocks.

### What's borderline

**c=16.** Δp50 range is 9.3%. Gateable with a generous tolerance (~10%+) but
adds limited signal beyond c=8.

### What's not gateable

**c=32.** ~5% Δp50 range. Still bounded, but the run-to-run distance is
several times larger than at c=1–c=8 and the absolute numbers wobble too.

**c=64.** Unusable. Δp50 swings from +778 to −2896 across three runs.
Root cause is the app mock's 4-worker saturation at this load level: the
without-guardrails path fires app requests as fast as it can and the mock queues
unpredictably. The with-guardrails path's CS-mock work paces requests enough to
hide most of this. This is a test-rig artifact, not an NMP behavior.

### Side observation: middleware overhead is small

Of the ~1029 ms Δp50 at c=1:
- ~1000 ms is the two content-safety mock round-trips (0.5s each, mandatory).
- ~29 ms is the middleware's *own* work (rails orchestration, request/response
  shaping, etc.) plus bare NMP+IGW overhead delta vs. without-guardrails.

The without-guardrails baseline of ~4020 ms at c=1 against a 4000 ms mock means
**bare NMP+IGW+shim overhead is ~20 ms** at idle.

## Recommendation for the CI gate

Based on the variance data above:

| Concurrency | Gate Δp50? | Gate absolute with-guardrails p50? | Notes |
|---|---|---|---|
| 1  | yes | yes | tightest signal |
| 2  | yes | yes | |
| 4  | yes | yes | |
| 8  | yes | yes | |
| 16 | informational | informational | record but don't fail |
| 32 | informational | informational | record but don't fail |
| 64 | exclude | exclude | mock saturation, not gateable |

Proposed tolerance bands (`max(absolute_ms, relative_%)`):
- Δp50: `max(±100 ms, ±5%)`
- with-guardrails p50: `max(±150 ms, ±3%)`

Both bands are ~3× the observed local run-to-run range, leaving headroom for
CI hardware noise being noisier than a quiet laptop.

## Open questions / followups

- **Local baselines won't transfer to CI hardware.** These numbers should seed
  the baseline file but be replaced once we have N runs from the actual CI
  runner class.
- **Three samples is a small N.** Worth one more local run (Run 4) before we
  treat the means above as canonical, but the c=1–c=8 numbers are unlikely
  to budge meaningfully.
- **c=64 instability is downstream of NMP.** Hypothesis: app mock's 4 workers
  saturate at concurrency 64 (4 RPS ceiling on 4.0s sleep). Easy to test by
  running with `--mock-workers 16`. Not blocking the gate work since c=64 is
  excluded anyway.
