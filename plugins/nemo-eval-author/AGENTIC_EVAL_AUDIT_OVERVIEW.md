<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Agentic Evaluation Audit Overview

NOTE: vibed w/ Codex but I did read it all + editied some, it is just my narrating what I've found to Codex and having it transcribe.

## Background

Teams building agents increasingly build agentic evaluation sets alongside those
agents. Those evaluation sets are used for regression testing, model selection,
agentic optimization, and decisions about whether a new agent version is good
enough to ship.

The missing piece is a way to reason about the quality of the evaluation set
itself. A team may have many agentic evaluation tasks, but still not know whether
those tasks cover the behaviors that matter, or whether the benchmark will
actually detect important regressions in the agent. Much literature is focused on
the _generation_ of additional tasks, but an infinitely growing set is also not
desirable.

The goal of an Eval Author audit is to help users make statements such as:

- this evaluation set covers the important behaviors we know about;
- this evaluation set is missing coverage for these behaviors;
- this evaluation set detects these intentional agent degradations;
- this evaluation set predicts external production outcomes when sufficiently
  good outcome data exists; and
- this evaluation set appears insufficient for these optimization or release
  decisions.

This is especially important for agentic optimization. If an optimizer uses an
evaluation set as its feedback signal, then missing or non-discriminating
evaluations can steer the optimizer toward changes that improve benchmark score
without improving the agent in practice.

## Metric Overview

There are many possible metrics for agentic evaluation set quality: construct
validity, discriminative power, flakiness, cost, reproducibility, judge bias, and
so on. Over time, we may want to add the ability to measure all of these things
to Eval Author.

However, for the current agent optimization framing, we are primarily interested
in three properties: completeness, discrimination, and downstream validity.

### Completeness

Completeness asks whether important behaviors are present in the evaluation set.

The core question is:

> Are there behaviors, workflows, capabilities, tools, failure modes, or product
> requirements that should be evaluated but are not represented by any task?

Completeness can be measured against different sources of expected behavior. Two
sources are especially useful:

- production behavior observed in traces; and
- declared behavior from specs, docs, tools, code, or human-authored capability
  taxonomies.

### Discrimination

The terminology in this subsection is intentionally pragmatic and does not
necessarily conform exactly to academic terminology. We use discrimination as the
umbrella term for whether an evaluation set can distinguish better agents from
worse agents. Sensitivity is one way of measuring discrimination when the weaker
agent is produced by intentionally degrading a stronger one.

The core question is:

> Does the evaluation set assign meaningfully better scores to stronger or intact
> agents than to weaker or degraded agents?

There are two especially useful ways to measure this property:

- population discrimination, where a benchmark is run across weak, medium, and
  strong agents or model-backed agent variants; and
- ablation-based discrimination, where a strong agent is intentionally weakened
  by removing or degrading tools, permissions, memory, retrieval, models, or
  other capabilities.

Psychometric item response analysis is a population-based discrimination method:
it estimates whether individual tasks have useful difficulty and positive
discrimination across a set of agents. Ablation is an interventional
discrimination method: it asks whether the benchmark reacts when a known
capability is deliberately broken. In both cases, the underlying question is
whether the evaluation set can distinguish quality rather than merely accumulate
tasks.

### Downstream Validity

Downstream validity asks whether benchmark performance predicts the external
outcome we actually care about. This is the most interesting form of benchmark
quality, but also the hardest to measure well.

The core question is:

> When the benchmark says one agent version is better than another, does that
> agent version actually perform better in production or in a production-like
> external outcome?

This is distinct from discrimination. A benchmark may separate weak, medium, and
strong agents, but still discriminate on the wrong behavior. Downstream validity
requires an external criterion: ticket resolution, no escalation, no repeat
contact, no manual override, accepted code changes, passing downstream CI,
successful workflow completion, user acceptance, or another outcome that is not
defined by the benchmark itself.

The caveat is that this requires unusually good production data. Production
outcomes are noisy, confounded by traffic mix, sparse, delayed, and often only
weak proxies for true success. The strongest version would use randomized
rollouts or paired replay over realistic production traces so that benchmark
scores can be compared against normalized production success. Without that kind
of data, downstream validity is usually aspirational rather than an audit that a
small team can run reliably.

## Solution Categories

### 1. Production Sampling for Completeness

Production sampling uses real-world traces as the source of expected behavior.
The audit looks at what the agent has actually seen or done in production and
asks whether the evaluation set covers those observed behaviors.

This approach is useful for measuring empirical completeness:

- Do observed request clusters have corresponding eval coverage?
- Do common workflows have eval coverage?
- Do production failures have regression evals?
- Do important tool paths or permission boundaries seen in traces have evals?
- Is the evaluation set overrepresenting toy scenarios relative to production?

The main limitation is that production sampling does not have a complete
denominator. It can measure coverage over the observed trace corpus, but it
cannot prove that the trace corpus exhaustively represents what the agent should
handle.

Trace2Env is a strong implementation reference for this category. It starts from
real agent traces, sanitizes and deduplicates them, extracts evidence-grounded
problem seeds, and converts supported seeds into evaluation tasks. A key design
choice is precision over recall: if a trace cannot support a grounded task, it
becomes an explicit no-candidate outcome rather than a guessed evaluation.

Algorithm sketch:

Start with an approved trace corpus and reconstruct the user-visible interaction
plus relevant agent activity for each trace: user request, context, model
responses, tool calls, tool results, retries, errors, final answer, final state,
and user correction or acceptance when available. Normalize each trace into one
or more behavior atoms, such as "search inventory before answering availability,"
"recover from empty tool result," or "ask for clarification before mutating
state." Cluster these atoms by underlying work and outcome rather than exact
wording.

Next, inspect the existing evaluation set and map each task onto the same
behavior atoms. This mapping should use the task instruction, environment,
verifier, run evidence, and any task metadata; it should distinguish direct
coverage from weak or inferred coverage. The audit then compares observed
behavior atoms against covered atoms and reports production-derived gaps, weighted
where useful by trace frequency, recency, severity, user dissatisfaction, or
business priority.

The output is a set of empirical completeness findings: observed behaviors with
no eval, observed failures without regression coverage, observed tool paths with
only shallow coverage, and existing evals that do not resemble the production
distribution. The report should be explicit that this measures coverage over the
observed corpus, not over the full possible behavior space.

Related references and candidates:

- Trace2Env: internal reference implementation for trace-grounded task generation.
- [SWE-bench](https://arxiv.org/abs/2310.06770): builds software engineering tasks
  from real GitHub issues and pull requests.
- [TRAIL](https://arxiv.org/abs/2505.08638): develops taxonomy and annotations over
  agent traces.
- [Measuring Agents in Production](https://arxiv.org/abs/2512.04123): motivates
  production-grounded evaluation of deployed agents.
- [Saving SWE-Bench](https://arxiv.org/abs/2510.08996): uses telemetry-derived
  interaction patterns to make formal benchmarks more realistic.

### 2. Declarative or Spec-Based Completeness

The declarative approach uses an explicit statement of what the agent should be
able to do as the source of expected behavior. That statement can come from
human-authored capability taxonomies, product requirements, documentation, tool
schemas, agent code, policies, or inferred drafts that a human later reviews.

This approach is useful because it creates a denominator:

- Which declared capabilities have eval coverage?
- Which tools have direct eval coverage?
- Which workflows have happy-path, negative-path, and recovery coverage?
- Which requirements or policy boundaries are untested?
- Which expected behavior categories are over- or underrepresented?

Unlike production sampling, declarative completeness can produce coverage-style
statements such as "12 of 20 declared capabilities are covered." The caveat is
that the denominator is authored. A spec-based audit is only as complete as the
capability model it uses.

LangChain's eval-engineering skill is a strong implementation reference for this
category. It inspects a repository, harness, traces, existing evals, and human
goals; creates reusable project world knowledge; drafts reviewed Task Specs; and
then turns approved specs into runnable tasks. This is not a pure taxonomy tool,
but it represents the same spec-based pattern: define the intended task, review
it, then build evaluation coverage from that specification.

Algorithm sketch:

Start by building a draft capability model for the agent. Inputs can include
human-authored taxonomies, product requirements, documentation, tool schemas,
agent code, tests, prompts, skills, policies, and representative traces. Normalize
these into declared behavior atoms with enough structure to be evaluated:
capability, scenario, tool or system dependency, expected outcome, failure mode,
priority, and any required test type such as happy path, negative path, recovery,
or policy boundary. Have a human review or amend the taxonomy when the denominator
matters.

Then map each existing evaluation task to the declared behavior atoms. A task
should count as direct coverage only when its instruction, environment, and
verifier actually exercise the declared behavior. Weaker relationships can be
recorded as partial, indirect, or inferred coverage. The audit can then compute
coverage over the declared denominator: which capabilities, workflows, tools,
policies, and failure modes are covered, missing, or only weakly covered.

The output is a spec-relative completeness report. It can make statements like
"12 of 20 declared capabilities have direct coverage" or "tool use is covered
for happy paths but not for permission failures." The central caveat is that the
result is only as good as the declared capability model; the audit should keep
unknown or disputed taxonomy items visible rather than pretending the denominator
is natural or complete.

Related references and candidates:

- [LangChain eval-engineering skill](https://github.com/langchain-ai/langchain-skills/tree/main/config/skills/eval-engineering):
  skill-based repository inspection, world knowledge, Task Specs, and Spec2Task.
- [CheckList](https://arxiv.org/abs/2005.04118): capability-by-test-type behavioral
  testing framework.
- [HELM](https://arxiv.org/abs/2211.09110): separates scenarios, metrics, and
  coverage in holistic model evaluation.
- [Continuous Benchmark Generation for Enterprise-scale LLM Agents](https://arxiv.org/abs/2511.10049):
  generates benchmarks from developer-authored knowledge bases as requirements
  evolve.
- [Anchor / ERP-Bench](https://arxiv.org/html/2605.26321v1): generates instruction,
  environment, oracle, and verifier from formal workflow specifications.

### 3. Ablation-Based Discrimination

Ablation-based discrimination measures whether the evaluation set detects
intentional degradation of the agent. Instead of asking whether a behavior is
represented, it asks whether the benchmark can distinguish the intact agent from
a weakened version of the same agent.

Example mutations include:

- remove or disable a tool;
- restrict permissions;
- weaken the model;
- disable retrieval or memory;
- corrupt a tool schema or tool response;
- remove retries or fallback logic;
- shorten context;
- disable a planner, router, or subagent; or
- inject controlled latency, empty results, or transient errors.

The audit then runs the mutated agent against the evaluation set. If at least
one relevant task fails, the mutation is detected. If the mutated agent still
passes, the mutation survives, which suggests that the evaluation set does not
discriminate that capability loss.

This provides a mutation-style discrimination metric:

> ablation discrimination = detected meaningful mutations / total meaningful mutations

The closest established analogy is mutation testing in software, where a test
suite is evaluated by its ability to kill seeded faults. For agentic evaluation,
the same idea becomes capability ablation: does the benchmark notice when the
agent has been made meaningfully worse?

Algorithm sketch:

Start from the agent architecture and capability model, then define a set of
localized mutations. Each mutation should intentionally degrade one meaningful
agent capability while keeping the agent runnable: remove a tool, weaken a model,
disable retrieval, restrict a permission, corrupt a tool response, shorten
context, remove memory, or break a router. Each mutation should name its targeted
capability and the evaluations expected to detect it. Mutations that make the
agent fail to start, or break everything indiscriminately, should be marked
invalid rather than counted.

Run the baseline agent and each mutated agent against the relevant evaluation
tasks. A mutation is detected when at least one relevant evaluation moves from
passing to failing, or its score degrades in the expected direction. A mutation
survives when the degraded agent still passes the evaluations that should have
noticed the degradation. Some mutations may be equivalent or irrelevant to the
current benchmark and should be excluded from the denominator after review.

The output is a discrimination report: detected mutations, surviving mutations,
invalid mutations, and the mutation-style discrimination score. Surviving mutations
are especially valuable because they identify cases where the eval set appears
complete but has no causal signal. For example, if an eval claims to measure
tool-grounded answers but still passes when the tool is removed, the benchmark is
not discriminating that capability loss.

Related references and candidates:

- Classic mutation testing: seed controlled code faults and measure the test
  suite's ability to detect them.
- [Property-Based Mutation Testing](https://arxiv.org/html/2301.13615v1): connects
  mutation score to specific tested properties, which maps well to agent
  capability discrimination.
- [MutGen](https://arxiv.org/html/2506.02954v2): uses mutation feedback to improve
  generated tests.
- [Agentic Benchmark Checklist](https://arxiv.org/abs/2507.02825): highlights
  degenerate-agent and benchmark-validity checks for agentic benchmarks.
- Anchor / ERP-Bench's no-op and oracle gates: an adjacent pattern for checking
  whether tasks fail under a degenerate agent and pass under an oracle.

### 4. Item-Response Discrimination

Psychometric item response analysis treats an evaluation set like an exam. Each
evaluation task is an item, each agent or model-backed agent variant is a
respondent, and each run produces a response such as pass/fail or a normalized
score. The model estimates latent agent ability and item properties such as
difficulty and discrimination. A useful task is neither passed by everyone nor
failed by everyone; it has positive discrimination, meaning stronger agents pass
it more reliably than weaker agents.

This belongs alongside ablation, not above it. Ablation-based discrimination
creates weaker agents by intentionally breaking a known capability. Item-response
discrimination can use the same degraded agents as respondents, but it can also
use a broader population: weak models, mid-tier models, frontier models, older
agent versions, agent variants, and intentionally ablated agents. The output is a
statistical view of whether the benchmark separates agents over the ability range
we care about.

Algorithm sketch:

Start by selecting a respondent pool: a model ladder, older and newer agent
versions, simple baselines, and optionally intentionally ablated versions of a
strong agent. Run every respondent against every evaluation task, preferably with
repeats when task or agent behavior is stochastic. Convert the results into a
response matrix where rows are respondents, columns are tasks, and cells contain
pass/fail outcomes or normalized scores.

Fit an item response model, usually starting with a simple one- or two-parameter
model before considering richer variants. For a binary pass/fail task, the model
estimates task difficulty and task discrimination. The benchmark-level audit then
looks for useful difficulty coverage, positive item discrimination, low rates of
near-duplicate items, and high total measurement information over the target
ability range. Tasks with negative discrimination, extreme difficulty, or high
apparent guessability are candidates for review or removal.

The output is a discrimination report: which tasks distinguish agent quality,
which tasks appear trivial or impossible, which tasks may be noisy or mislabeled,
and where the benchmark has measurement strength or weakness across the ability
range. The caveat is that item response analysis does not prove semantic
completeness and does not by itself explain causality. If an ablated agent scores
lower, IRT can show that the benchmark separated it from the intact agent, but
the ablation design is what tells us which capability loss was responsible.

Related references and candidates:

- Classical item response theory: estimates item difficulty, item discrimination,
  respondent ability, and test information from response matrices.
- [Lost in Benchmarks? Rethinking Large Language Model Benchmarking with Item Response Theory](https://arxiv.org/abs/2505.15055):
  applies item response analysis to LLM benchmark separability and benchmark
  quality.
- [Auditing LLM Benchmarks with Item Response Theory](https://arxiv.org/abs/2605.30504):
  uses IRT-style signals to surface likely mislabeled or ambiguous benchmark
  items across many model responses.
- [Can We Trust Item Response Theory for AI Evaluation?](https://arxiv.org/abs/2607.15190):
  studies when IRT inferences are reliable or fragile for AI benchmark response
  matrices.

### 5. Downstream Validity

Downstream validity measures whether benchmark scores predict external success.
It treats the benchmark as a proxy for a real deployment outcome and asks whether
that proxy is actually useful.

This is the strongest quality signal when it is available. If an evaluation set
predicts production success, it becomes much easier to justify using it for model
selection, agent optimization, regression gating, and release decisions. The
problem is that most teams do not have production data that is clean enough to
support this claim. In practice, the outcome labels are often delayed, implicit,
sparse, confounded, or unavailable.

Algorithm sketch:

Start by defining the production outcome at the same unit of work as the
evaluation task when possible: request, conversation, ticket, issue, workflow, or
artifact. The outcome should be external to the benchmark. Examples include
resolved-without-escalation, no repeat contact within a fixed window, accepted
code change, downstream CI success, successful tool-mediated state change, no
manual override, or explicit user acceptance. Segment the outcome by intent or
workflow so that traffic mix does not dominate the result.

Next, collect a pool of agent versions or model-backed variants. These can be
historical releases, current candidates, model swaps, prompt variants, tool
configurations, or controlled ablations. For each variant, compute its score on
the benchmark under audit. Separately, estimate that same variant's production
success rate, ideally using randomized rollout data, A/B tests, or paired replay
against production traces and environment snapshots. Retrospective release data
can be useful, but it is weaker because traffic, product behavior, and user mix
change over time.

Finally, measure whether benchmark score predicts external success. This can be a
rank correlation between benchmark score and production outcome across agent
versions, a regression or calibration analysis, or a release-decision analysis
that asks whether benchmark-selected candidates would have selected the better
production performer. A downstream-valid benchmark is one where score
improvements reliably correspond to production improvements. A benchmark that
separates agents but fails to predict production outcomes has discrimination
without downstream validity.

Related references and candidates:

- [Benchmark^2](https://arxiv.org/abs/2601.03986): evaluates benchmark quality
  using cross-benchmark ranking consistency, discriminability, and capability
  alignment deviation. This is adjacent to downstream validity, but it mostly
  validates benchmarks against peer benchmark behavior rather than production
  outcomes.
- [Medical Large Language Model Benchmarks Should Prioritize Construct Validity](https://arxiv.org/abs/2503.10694):
  directly examines criterion validity by asking whether MedQA benchmark accuracy
  predicts performance on matched real-world EHR cases.
- [Evaluating LLM Metrics Through Real-World Capabilities](https://arxiv.org/abs/2505.08253):
  uses survey and usage-log evidence to identify real-world capabilities and
  assess whether existing benchmarks reflect common LLM usage.
- [Towards Ecologically Valid LLM Benchmarks](https://arxiv.org/abs/2511.05501):
  frames benchmark design around domain practice and real-world usage context.
- [CirrusBench](https://arxiv.org/abs/2603.28569): builds an agent benchmark from
  real cloud-service support tickets and includes metrics tied to resolution
  efficiency and customer-service workflow realism.

## Metric Evaluation

The sections above describe metrics or audit methods for measuring benchmark
quality. We also need to evaluate whether those benchmark-quality metrics are any
good. This is a separate question: not "is this benchmark good?", but "does this
metric correctly reward and penalize benchmark changes that we understand?"

I see two tiers of metric evaluation.

### Tier 1: Metamorphic Metric Evaluation

Tier 1 is a cheap, repeatable sanity check for a benchmark-quality metric. Start
with a benchmark that is trusted enough to use as a reference, then create
controlled degraded versions of that benchmark using benchmark mutations. These
mutations should be intentional and interpretable: remove whole capability
categories, duplicate one task many times, leak answers in prompts, make tasks
impossible, randomize graders or labels, remove tool-requiring tasks, replace
realistic tasks with toy tasks, or corrupt task environments.

For each mutation, define the expected metric behavior before running the
experiment. A completeness metric should drop when declared capability categories
are removed. A discrimination metric should drop when answer leakage causes weak
agents to pass, when labels are randomized, or when tool-requiring tasks are
removed from a tool-use benchmark. A downstream-validity metric should drop when
production-realistic tasks are replaced with tasks that no longer resemble the
external outcome, assuming such outcome data exists.

The evaluation then computes the metric on the original benchmark and each
mutated benchmark. A good metric should satisfy the expected metamorphic
relationships: the trusted benchmark should score higher than degraded variants,
larger corruptions should generally produce larger drops, and the affected
submetric should move more than unrelated submetrics. This does not prove the
metric is scientifically complete, but it is a practical daily test that catches
metrics that reward duplication, miss answer leakage, ignore removed coverage, or
otherwise behave nonsensically.

### Tier 2: Optimization Outcome Evaluation

Tier 2 asks whether the metric is useful inside a larger agent optimization loop.
Instead of only checking that the metric reacts correctly to controlled benchmark
mutations, use the metric to guide a real optimization or eval-improvement
process and measure whether the resulting agent improvements are better.

For example, compare optimization runs that use different benchmark-quality
metrics to select, weight, audit, or generate evaluation tasks. Each run starts
from the same agent and same candidate eval pool, then uses its assigned metric
to guide the optimization process. After optimization, evaluate the resulting
agents on held-out benchmarks, trusted regression suites, production replay
tasks, or downstream production outcomes. The stronger metric is the one that
leads to better final agents under these external checks, not merely better
scores on the metric it optimized.

This tier is much more expensive. It requires multiple optimization runs,
candidate agent variants, held-out evaluation data, and ideally production-like
or production-derived outcomes. It is therefore not something to run daily. Tier
1 should be the regular regression suite for metric implementations; Tier 2 is
the deeper validation used periodically to establish that the metric is actually
helping the agent improvement process.
