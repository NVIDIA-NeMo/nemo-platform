# Eval Author Design Overview

> **Status:** Initial discussion draft. This document describes the system we
> want to build, not the system that exists today.

## Purpose

Eval Author measures the quality and adequacy of evaluation sets for agents and
generates new evaluations to address identified gaps. Its purpose is to provide
the evaluation coverage needed to measure agent quality reliably and optimize
agents effectively.

## Mission

Eval Author provides a stable, production-grade foundation for building,
evaluating, and operating approaches that measure and improve agent evaluation
sets. It supplies the common contracts, evidence access, orchestration,
artifacts, provenance, conformance tooling, and integration points needed to
develop and compare measurement and generation strategies reliably. On that
foundation, NeMo Platform ships composable, production-ready reference
strategies—grounded in the best available research and advanced through our own
empirical work—so customers can use effective approaches out of the box, mix
and match them within larger evaluation and optimization workflows, and extend
the toolkit without changing its core infrastructure.

## Operating Model

Eval Author follows a three-stage workflow:

- `discover` establishes the state of the world by producing a factual snapshot
  of the evaluation set and the evidence associated with it;
- `audit` measures that world by applying one or more strategies to identify
  strengths, gaps, and other dimensions of evaluation-set quality; and
- `propose` extends the world by producing reviewable candidate changes that
  address the audit findings.

The initial reference workflow builds on the approach used today: Insights
derived from production and evaluation traces provide evidence of important
agent behaviors and failures, the existing evaluation set is assessed against
those Insights, and uncovered behaviors are turned into additional evaluations.

That Insight-driven workflow is one useful reference strategy, not the system's
defining abstraction: audit and proposal are extensible surfaces that can also
support strategies based on raw trace analysis, clustering, agent capabilities
and tools, source code, specifications, human feedback, or future research.

## CLI

The proposed command surface is:

```text
nemo agents eval-author
|-- doctor
|-- discover
|-- audit
|-- propose
`-- run
```

### `doctor`

`doctor` is a read-only preflight command that determines whether a specific
Eval Author invocation is ready to run. It validates the common platform and
artifact requirements, resolves the requested strategies, and asks each
strategy to validate its own configuration and dependencies. It does not
discover, audit, propose, or modify an evaluation set.

Key parameters identify the intended command or end-to-end recipe, the target
evaluation set, the selected strategies and their configuration, the Platform
workspace and endpoint, and the artifact output location. Its inputs are the
resolved invocation configuration plus the capability and dependency
requirements declared by each selected strategy. Its output is a structured,
human-readable readiness report of passed, advisory, and blocking checks, with
an exit status suitable for scripts and continuous integration.

### `discover`

`discover` establishes the state of the world by collecting factual data and
metadata about an evaluation set and recording a point-in-time snapshot for
later `audit` and `propose` invocations. The initial implementation discovers
repository-owned Harbor configurations and datasets, available agent doctrine,
and associated Intake traces, then preflights each evaluation entrypoint to
establish whether its configuration, agent, environment, and tasks are
runnable. It records these observed facts, validation findings, relevant
metadata, and an input fingerprint in a standard `discovery.md` report.
Discovery is read-only: it describes the existing evaluation set and its
supporting evidence without judging its quality, generating evaluations, or
changing repository files.

### `audit`

`audit` measures the quality, completeness, and adequacy of an existing
evaluation set. It is the entry point for executing a named audit strategy; a
strategy must be selected, and the command forwards the remaining command-line
arguments to that strategy without imposing a common configuration or result
model. The initial reference strategy assesses whether behaviors and failures
captured by Insights are represented in the evaluation set, but other installed
strategies may measure production-trace coverage, capability or tool coverage,
diversity, redundancy, evaluator quality, or other dimensions of quality. An
audit is read-only; each initial strategy owns its particular inputs, metrics,
findings, and output representation until repeated implementations establish a
useful common contract.

### `propose`

`propose` bootstraps or extends an evaluation set by producing additional
agentic evaluation tasks. It is the entry point for executing a named proposal
strategy; a strategy must be selected, and the command forwards the remaining
command-line arguments to that strategy without imposing a common configuration
or result model. The initial reference strategy turns uncovered Insight
behaviors and their supporting traces into targeted evaluations, while other
installed strategies may generate from production clusters, agent capabilities
and tools, specifications, source code, human feedback, or other evidence. Each
initial strategy owns its particular inputs and output representation. Proposal
does not silently mutate the canonical evaluation set; validation, review, and
permanent adoption are explicit downstream steps.

### `run`

`run` executes a codified end-to-end workflow that composes `discover`,
`audit`, and `propose`. A run recipe defines the audit and proposal strategies,
the arguments passed to each, their required evidence, and how their outputs
flow between the stages. The existing Insight-driven workflow is one example:
discover the current evaluation set, audit it against an Insight and its
evidence traces, and propose targeted evaluations for uncovered behavior before
agent optimization begins. `run` provides orchestration and reproducibility;
it is not itself a measurement or generation strategy. Its initial inputs and
outputs should be defined by the first concrete recipe rather than by a
universal run contract.

## Architectural Model

### Starting Point and Direction

Eval Author starts with one in-flight, Insight-driven implementation and a small
amount of supporting infrastructure. The immediate goal is to make that
workflow available through the standalone commands without first designing a
general framework for every possible measurement or generation technique. The
long-term goal is to preserve the fixed `discover`, `audit`, and `propose`
workflow while allowing the implementation of audit and proposal to be selected
by name. As additional strategies are built, repeated integrations and
behaviors should be extracted into common components and contracts.

```text
evaluation sources ──> discover ──> evaluation snapshot
                                          |
                                          v
                                  named audit strategy
                                          |
                                          v
                                named proposal strategy
                                          |
                                          v
                              candidate evaluation changes
```

The phases are fixed. A strategy is the initial customization boundary. A
strategy may be a self-contained implementation or may privately decompose its
work into agents, components, skills, libraries, service calls, or subprocesses.
We should introduce shared component interfaces only after multiple strategies
demonstrate that the same boundary is genuinely reusable.

### Discovery

Discovery is intentionally different from audit and proposal. It collects
objective information about an evaluation set and writes an evaluation snapshot
in a standard Eval Author format. The snapshot should initially contain only
the information needed by the Insight workflow, such as evaluation sets and
tasks, evaluator configuration, available execution results and trace
associations, and relevant metadata. The format can expand as new strategies
demonstrate the need for additional information.

Source-specific integration may be needed to collect information from Harbor,
NeMo Platform, a repository, or another evaluation system. Discovery owns the
normalization of that information. It does not decide whether the evaluation
set is good and should distinguish directly observed information from any
association that had to be inferred.

### Host Responsibilities

Eval Author owns the fixed command flow, selection and invocation of strategies,
and access to shared integrations. Initially those integrations should be the
basic functionality already needed by the Insight workflow: Platform entities,
Intake evidence, agent artifacts, Harbor evaluation inputs, model access, and
the output working directory. The host should also provide consistent
configuration loading, preflight checks, logging, and error handling.

Strategies may use these integrations directly. When multiple strategies begin
implementing the same behavior—such as trace retrieval, clustering,
materializing Harbor tasks, or validating generated evaluations—that behavior
can be extracted into a shared component supplied by Eval Author. The host
should grow from demonstrated reuse rather than an upfront catalog of abstract
capabilities.

### Strategy Extension Mechanism

Eval Author should define two small Python abstractions: `AuditStrategy` and
`ProposalStrategy`. An implementation of one of these abstractions is a
strategy. Their initial API should intentionally contain only one asynchronous
entry point:

```python
from abc import ABC, abstractmethod


class AuditStrategy(ABC):
    @abstractmethod
    async def run(self, args: list[str]) -> None:
        """Run an audit using strategy-specific command-line arguments."""


class ProposalStrategy(ABC):
    @abstractmethod
    async def run(self, args: list[str]) -> None:
        """Run a proposal using strategy-specific command-line arguments."""
```

The host resolves a strategy by name and passes the command-line tokens that
remain after host-level strategy selection directly to `run`. The base classes
do not initially define configuration models, input objects, result objects,
validation hooks, constructors, or internal component boundaries. Strategy
implementations own argument parsing and output behavior, and report failure by
raising an exception. This deliberately narrow contract allows us to put the
existing Insight implementation behind the strategy boundary without guessing
at abstractions that have not yet been demonstrated.

Strategies are discovered from Python package entry points, following the
existing Numeric Optimization backend registry. For example, a separately
installed package could register implementations like this:

```toml
[project.entry-points."nemo.eval_author.audit_strategies"]
cluster-coverage = "acme_eval_author.cluster:ClusterCoverageAudit"

[project.entry-points."nemo.eval_author.proposal_strategies"]
cluster-examples = "acme_eval_author.cluster:ClusterExampleProposal"
```

The Eval Author registry loads those entries, verifies that each is the
appropriate strategy type, and makes them selectable by name in the CLI or a
run configuration. The entry-point name supplies the strategy name; it does not
need to be repeated in the base class. First-party reference strategies register
through the same mechanism. A company can therefore package private strategies,
publish them to an internal Python index, install them alongside NeMo Platform,
and select them without modifying the Eval Author repository.

A strategy implementation is also the adapter boundary for third-party tools.
It may call a Python library, invoke a service, or execute a CLI installed by
its package. The wrapper parses the forwarded arguments, translates them into
the tool's native inputs, and manages the tool's outputs. This lets Eval Author
distribute and operate a technique without requiring that the technique itself
be rewritten for NeMo.

The identical initial shape of the two base classes is intentional: they are
separate semantic extension points and may evolve differently. We should add a
more specific intermediate abstraction only after multiple strategies share a
real contract. For example, if several clustering-based audit strategies
consume the same trace and evaluation inputs and produce the same coverage
findings, a future `ClusteringAuditStrategy` can define those shared types and
leave only the clustering algorithm to its subclasses. No such intermediate
class is required for the first implementation.

Initially, an `audit` or `propose` invocation should execute one selected
strategy. Having many installed strategies does not require arbitrary
composition of their outputs. An end-to-end `run` selects a named recipe that
knows which audit and proposal implementations are compatible; the first such
recipe is the Insight-driven workflow. Once multiple implementations expose a
real need for combining audit findings or chaining generation techniques, the
shared contracts for that composition can be designed from those concrete
cases.

### Outputs and Mutation

The evaluation snapshot is the first shared data contract because every audit
strategy needs a consistent description of the existing evaluation set. Audit
and proposal outputs may remain strategy-specific at first, beyond what is
needed for the CLI and a compatible run recipe to pass information between
them. We should not prescribe a universal audit report, run manifest, or
serialization format until there are multiple implementations that need one.

Discover and audit are read-only. Proposal operates on a working copy or output
location and must not silently modify the original evaluation set. Validation,
review, and permanent adoption of proposed evaluations remain explicit actions,
even if a particular strategy performs some validation while it runs.

### Relationship to Insights and Optimization

Analyst remains responsible for turning telemetry into persistent Insights;
Experimentalist and other optimizers remain responsible for changing agents.
Eval Author consumes Insights as one possible form of evidence and supplies the
evaluation sets needed to measure and optimize agents. The Insight-driven path
is the initial reference workflow: an audit strategy determines whether the
behavior represented by an Insight is covered, and a proposal strategy converts
uncovered behavior and its evidence traces into targeted evaluation tasks.
Other strategies can operate without Insights, and the shared infrastructure
should not assume that an Insight is always present.

### Insight-Driven Reference Implementation

The first target is the in-flight Insight-driven workflow used by agent
optimization. Analyst examines production and evaluation telemetry and persists
an Insight describing a recurring behavior or failure, the affected agent, and
the trace references that support it. Eval Author then discovers the existing
evaluation context, including the train and validation suites, task template,
agent source and specification, available execution metadata, and the Insight's
evidence traces. The Insight audit strategy compares that evidence with the
current evaluation set and reports whether the behavior and its intended
success criteria are already represented and measurable. The Insight proposal
strategy consumes uncovered findings, materializes representative traces as
targeted Harbor tasks, authors the required verifier metrics, validates the
candidate tasks and affected suites, and returns the proposed evaluation
changes. The Insight run recipe composes these stages before Experimentalist
begins optimizing the agent, allowing the new metrics to become optimization
objectives while existing quality measures remain regression constraints.

Much of the proposal behavior already exists in the reusable Eval Author
runner: it resolves a persistent Insight, retrieves the agent source, stages
the Harbor datasets and task template, creates one candidate task per selected
trace, analyzes the traces, authors Insight-specific metrics across the train,
validation, and generated suites, validates the results, and computes
deterministic content identities. The first architectural implementation should
preserve that working behavior while adding a separate audit step and moving
proposal changes behind the strategy abstraction. The standalone commands,
strategy registration, and explicit review and adoption of the generated
Insight suite remain to be wired.

#### Wiring the Insight Strategies

The first implementations can remain thin adapters around Insight-specific
functions. The following code is illustrative: `audit_insight_coverage` is the
new audit behavior to build, while `run_eval_author` is the existing proposal
runner. Parsing and persistence helpers belong to the Insight strategy package;
they are not part of the shared strategy API.

```python
class InsightAuditStrategy(AuditStrategy):
    async def run(self, args: list[str]) -> None:
        options = parse_insight_audit_args(args)
        snapshot = load_discovery(options.discovery)
        insight = await load_insight(options.insight)

        report = await audit_insight_coverage(
            snapshot=snapshot,
            insight=insight,
        )
        write_insight_audit(options.output, report)
```

The audit arguments would initially name the `discovery.md` snapshot, the
Insight to assess, and an output path. The strategy defines the contents of its
report. That report only needs to answer what this proposal implementation
requires—for example, whether the Insight is already covered and the evidence
supporting that decision.

```python
class InsightProposalStrategy(ProposalStrategy):
    async def run(self, args: list[str]) -> None:
        options = parse_insight_proposal_args(args)
        audit = load_insight_audit(options.audit)

        if audit.covered:
            write_noop_proposal(options.output, reason="Insight is already covered")
            return

        result = await run_eval_author(
            insight=options.insight,
            train_dataset=options.train_dataset,
            validation_dataset=options.validation_dataset,
            task_template=options.task_template,
            experiment_dir=options.experiment_dir,
            workspace=options.workspace,
            base_url=options.base_url,
            config=options.eval_author_config,
            agent=options.agent,
        )
        write_insight_proposal(options.output, result)
```

The proposal adapter owns the translation from its command-line arguments into
the existing runner's typed inputs. It also owns how `EvalAuthorResult` is
recorded for review. Neither `EvalAuthorResult` nor the Insight audit report
becomes part of `ProposalStrategy` merely because this implementation uses it.

Both implementations register under the same strategy name in their separate
registries:

```toml
[project.entry-points."nemo.eval_author.audit_strategies"]
insight = "nemo_eval_author_plugin.strategies.insight:InsightAuditStrategy"

[project.entry-points."nemo.eval_author.proposal_strategies"]
insight = "nemo_eval_author_plugin.strategies.insight:InsightProposalStrategy"
```

The host loads the registered class, constructs it, and verifies the expected
extension point. A shared generic loader can sit beneath two typed convenience
functions:

```python
StrategyT = TypeVar("StrategyT", AuditStrategy, ProposalStrategy)


def load_strategy(
    group: str,
    name: str,
    expected_type: type[StrategyT],
) -> StrategyT:
    entries = discover_entry_points(group)
    if name not in entries:
        raise UnknownStrategyError(group, name)

    implementation = entries[name].load()()
    if not isinstance(implementation, expected_type):
        raise InvalidStrategyError(group, name, expected_type)
    return implementation


def load_audit_strategy(name: str) -> AuditStrategy:
    return load_strategy(AUDIT_STRATEGY_GROUP, name, AuditStrategy)


def load_proposal_strategy(name: str) -> ProposalStrategy:
    return load_strategy(PROPOSAL_STRATEGY_GROUP, name, ProposalStrategy)
```

At the CLI boundary, Eval Author consumes only the strategy name. Typer leaves
all other tokens untouched for the selected implementation:

```python
@app.command(
    "audit",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def audit(ctx: typer.Context, strategy: str) -> None:
    implementation = load_audit_strategy(strategy)
    asyncio.run(implementation.run(list(ctx.args)))


@app.command(
    "propose",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def propose(ctx: typer.Context, strategy: str) -> None:
    implementation = load_proposal_strategy(strategy)
    asyncio.run(implementation.run(list(ctx.args)))
```

This yields standalone commands whose options are defined entirely by the
selected strategy:

```bash
nemo agents eval-author audit insight \
  --discovery discovery.md \
  --insight INSIGHT_ID \
  --output insight-audit.json

nemo agents eval-author propose insight \
  --audit insight-audit.json \
  --insight INSIGHT_ID \
  --train-dataset evals/train \
  --validation-dataset evals/validation \
  --task-template evals/task-template \
  --output proposed-evals
```

The initial Insight `run` recipe performs the same two dispatches
programmatically. It chooses the intermediate audit path, supplies compatible
arguments to each strategy, and passes the audit path to proposal. This recipe
knows the private contract between these two Insight implementations; the Eval
Author host does not.

```python
async def run_insight_recipe(options: InsightRunOptions) -> None:
    audit_path = options.work_dir / "insight-audit.json"

    await load_audit_strategy("insight").run(
        [
            "--discovery", str(options.discovery),
            "--insight", options.insight,
            "--output", str(audit_path),
        ]
    )
    await load_proposal_strategy("insight").run(
        [
            "--audit", str(audit_path),
            "--insight", options.insight,
            "--train-dataset", str(options.train_dataset),
            "--validation-dataset", str(options.validation_dataset),
            "--task-template", str(options.task_template),
            "--output", str(options.output),
        ]
    )
```

This is intentionally a first-step architecture. If later audit and proposal
strategies repeatedly exchange the same findings, that observed contract can be
promoted into shared typed inputs and results without changing the basic
strategy selection mechanism.

### Incremental Implementation

The initial implementation should establish only the seams needed to expose the
working Insight path:

1. Define the initial evaluation snapshot produced by `discover`.
2. Define minimal audit and proposal strategy abstractions and entry-point
   discovery.
3. Adapt the existing Insight-driven behavior into the first proposal strategy
   and add the corresponding audit strategy.
4. Define the Insight run recipe and wire the standalone commands to it.
5. Provide a small example or scaffold showing how an external package
   registers a strategy.

After a second and third strategy exist, compare their implementations and
extract the common integrations, result contracts, test fixtures, and internal
components that have proved useful. Those later abstractions should be treated
as the result of implementation experience, not prerequisites for beginning
the work.

## Open Questions

- What is the smallest evaluation snapshot required by the Insight audit?
- What is the minimum return contract the standalone `audit` and `propose`
  commands need before common result types have emerged?
- Should a run recipe name separate compatible audit and proposal strategies,
  or should the initial Insight recipe own both directly?
- What installation and scaffolding experience should Eval Author provide for
  private strategy packages?
