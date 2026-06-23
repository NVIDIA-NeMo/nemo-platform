# Subprocess First-Class Execution Resolution Spec

## Summary

This spec defines how NeMo Platform should select execution for jobs when the same logical workload may be able to run as:

- a host subprocess
- a CPU container job
- a GPU container job
- a distributed GPU container job

The key architectural change is:

- `subprocess` becomes a first-class execution provider rather than a compatibility rewrite target
- plugin and service compilers declare which providers they support
- a shared resolution algorithm selects the provider and profile before the final `PlatformJobSpec` is compiled
- the Jobs service validates and dispatches an honest execution contract; it does not silently reinterpret one provider as another

This spec assumes that local and remote execution should converge on a single jobs-backed architecture. It defines the execution-selection contract needed to make that architecture predictable across plugins.

The guiding product principle is a single deterministic and well-documented platform mechanism for execution selection. The mechanism may be non-trivial, but it must be consistent across plugins, explainable, and free of plugin-specific surprises.

A user submitting a job to one plugin should be able to expect the same execution-selection behavior they would get from another plugin unless that plugin has a clear, documented reason to behave differently.

## Problem

Today the repo mixes multiple architectural layers.

### Current State

At the plugin layer, many jobs compile directly to container-oriented providers such as `cpu`, `gpu`, or `gpu_distributed`.

At the Jobs API ingress layer, some CPU container steps are silently rewritten into subprocess steps when a subprocess profile is configured. The rewrite currently lives in:

- [services/core/jobs/src/nmp/core/jobs/api/v2/jobs/endpoints.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/api/v2/jobs/endpoints.py:105)

At the plugin CLI layer, `run_local(...)` still executes jobs in-process while `submit_remote(...)` posts to Jobs. That means local and remote still use materially different execution paths.

### Why This Is A Problem

The current behavior creates ambiguity in several places.

- The same submitted `cpu` step may mean a real CPU container job in one environment and a host subprocess in another.
- The Jobs service is doing semantic translation, not just validation and dispatch.
- Plugins do not have a shared, explicit convention for how to choose among subprocess, CPU, GPU, and distributed GPU execution, so each plugin is pushed toward implementing its own fallback and selection logic.
- Submitters cannot reliably predict whether a plugin will run locally, in a container, or on a cluster.
- Resolution and validation logic are split across plugin compile logic, Jobs API validation, and backend-specific assumptions, which invites behavior drift across plugins instead of one consistent platform mechanism.

This makes execution behavior harder to explain and less consistent for plugin authors, operators, and submitters because the same logical workload may be compiled, validated, and reinterpreted differently depending on the plugin and deployment configuration. Even if execution selection remains a non-trivial mechanism, it should still be one deterministic and well-documented platform behavior rather than something that drifts across plugins.

## Goals

- Make `subprocess` a first-class execution provider.
- Remove the dishonest CPU-to-subprocess rewrite from the Jobs service.
- Define a shared execution resolution process that all plugins use.
- Let plugins describe which providers they support without each plugin inventing its own fallback logic.
- Let callers optionally constrain or override execution choice, without forcing them to understand container-vs-subprocess details in the common case.
- Fast-fail before job creation when no compatible execution target exists.
- Preserve a single jobs-backed architecture for both local and remote execution.
- Move the platform toward eliminating the separate `run_local(...)` execution path in favor of one jobs-backed execution model, even if that full transition lands beyond the scope of this spec.
- Keep backend routing responsibility in Jobs while moving execution-selection policy above Jobs.
- Make execution selection deterministic, documented, and consistent across plugins so that it is a core platform feature rather than a per-plugin convention.

## Non-Goals

- This spec does not define platform startup, control-plane lifecycle, or service-loading behavior.
- This spec does not define how Jobs determines runtime execution availability. That remains a separate concern; this spec only assumes that Jobs is the authority for reporting what is available.
- This spec does not define arbitrary plugin-defined execution providers. It standardizes the built-in providers first.
- This spec does not attempt to preserve backward compatibility for the current silent rewrite as a permanent architectural feature.
- This spec does not change the current implementation of `run_local(...)` or the current local `run` command behavior. In scope, those remain the existing scheduler-managed in-process path; their eventual replacement belongs to separate follow-on work.

## Terminology

This area has accumulated overlapping terms. This spec standardizes them.

### Provider

A small, platform-owned set of execution shapes that a plugin can target during compilation and encode into the final `PlatformJobSpec`.

Initial providers:

- `subprocess`
- `cpu`
- `gpu`
- `gpu_distributed`

These are the choices made by the shared resolver and plugin compiler.

### Profile

A named operator-configured execution profile, selected in combination with a provider.

Examples:

- `subprocess/default`
- `cpu/default`
- `gpu/research`
- `gpu_distributed/slurm-a100`

Profiles are how operator policy is surfaced into compilation and dispatch.

### Backend

The implementation that ultimately runs the job after a provider/profile pair is resolved.

Examples:

- `subprocess`
- `docker`
- `kubernetes_job`
- `volcano_job`

Backends remain a Jobs concern.

## Architectural Principle

The single most important architectural rule in this spec is that Jobs dispatches the chosen execution contract; it does not reinterpret it after the plugin has compiled the final `PlatformJobSpec`.

The point of this rule is to protect a few specific properties:

- one selected provider and profile for the job or step
- one honest final `PlatformJobSpec` that reflects that choice
- provider-specific compilation and validation in the plugin or shared plugin-layer logic
- no late semantic rewrite where one provider shape is submitted and another provider shape is actually run

In practice, a plugin may still have an earlier provider-agnostic phase that canonicalizes user input into a job-specific spec. What this rule forbids is compiling a final provider-specific step shape and then having Jobs reinterpret it as something else later.

That implies the following responsibility split.

### Caller Responsibility

The caller may provide:

- an explicit profile
- an execution preference or constraint, if surfaced by the plugin API
- no execution hint at all

The caller should not need to know whether the workload will run as a subprocess or in a container in the common case.

### Plugin Responsibility

The plugin or service compiler is responsible for:

- declaring which providers a job supports
- declaring provider preference order for the canonical spec where applicable
- providing compilation logic for each supported provider
- expressing workload-specific constraints, such as whether a job can run only on GPU or only as a host subprocess

Plugins do not need to implement every built-in provider. A job may support any subset of providers that makes sense for its workload, but it must support at least one provider in order to be executable.

Provider preference is dynamic by design. A plugin may determine its preferred provider order as a function of the canonical spec rather than as one static list for the entire job type.

### Shared Resolver Responsibility

A single deterministic resolver in the plugin/platform layer is responsible for applying the same execution-selection algorithm across all plugins.

That shared resolver is responsible for:

- reading caller intent
- reading plugin-supported providers
- reading the available execution profiles exposed by Jobs
- selecting a compatible provider and profile according to a shared convention
- producing a fast failure when no compatible choice exists

### Jobs Responsibility

The Jobs service is responsible for:

- exposing configured execution profiles
- validating that the submitted `PlatformJobSpec` references valid provider/profile combinations
- routing the selected provider/profile to the configured backend
- dispatching, reconciling, logging, and lifecycle management

Jobs must not silently change `cpu` into `subprocess`, or any equivalent semantic rewrite.

## Container Ownership

This spec makes container ownership explicit.

### Container-Oriented Providers

The following providers are container-oriented:

- `cpu`
- `gpu`
- `gpu_distributed`

For these providers, the plugin compiler is responsible for defining:

- the container image
- the entrypoint and command
- resource requests and limits
- any family-specific environment or storage requirements

The container field is part of the plugin-authored execution contract for these providers.

### Subprocess Provider

The `subprocess` provider is host-command-oriented.

Like every provider in this spec, `subprocess` is optional at the plugin level. Jobs that can run as host commands may implement it; jobs that cannot or should not run that way do not need to support it.

For this provider, the plugin compiler is responsible for defining:

- the host command to run
- any required environment variables, secrets, and path validation rules

The `subprocess` provider does not carry a container field.

If a subprocess backend implementation later chooses to invoke Docker, Podman, a wrapper script, or a prepared virtual environment internally, that is backend configuration, not plugin-authored step semantics.

This distinction is important because it keeps the submitted execution contract honest.

## Shared Resolution Model

The platform should standardize one resolution process across plugins.

### Inputs To Resolution

Resolution takes three categories of input.

#### 1. Caller Intent

Possible caller intent includes:

- explicit profile selection
- explicit provider preference, if the plugin exposes one
- no preference

Explicit caller choices take precedence over automatic fallback.

#### 2. Plugin Support

Each job type declares:

- supported providers
- optional dynamic preference order among supported providers
- any workload-specific constraints

Examples:

- `evaluate-suite`: supports only `subprocess`
- evaluator: supports `subprocess` and `cpu`
- customization training: supports `gpu` and possibly `gpu_distributed`

#### 3. Host Availability

Availability comes from the execution profiles that Jobs reports as available.

For the purposes of this spec, the important contract is simple:

- Jobs is the authority for provider/profile availability
- plugins and other services resolve against what Jobs reports as available
- plugins should not implement their own ad hoc availability logic

How Jobs determines that availability is intentionally out of scope for this document. Today that area is fragmented and partly inferred from configuration and plugin-specific checks, but this spec assumes a cleaner future state where Jobs publishes the authoritative availability set and the shared resolver consumes it.

Examples:

- local dev host: `subprocess/default`, maybe `cpu/default`
- Docker deployment: `cpu/default`, `gpu/default`, maybe `subprocess/default`
- Kubernetes production: `cpu/default`, `gpu/default`, `gpu_distributed/default`, no subprocess

The plugin should not need to infer this indirectly from labels like "local" or "production" when Jobs can expose the actual configured capabilities.

## Resolution Algorithm

The shared resolver should use the following algorithm.

### Step 1: Validate Explicit Caller Constraints

If the caller explicitly selected a profile:

- determine that profile's provider
- verify that the plugin supports that provider for this job
- verify that the profile is actually available on the host
- fail immediately if either check fails

If the caller explicitly selected a provider or mode:

- verify that the plugin supports it
- intersect it with available profiles for that provider
- fail immediately if none are available

### Step 2: Build Candidate Providers

If no explicit caller constraint exists:

- read the plugin's supported providers for the job
- order them according to the plugin's declared preference list for the canonical spec, or a shared default convention when no plugin-specific order is provided

### Step 3: Intersect With Available Profiles

For each candidate provider in order:

- find the available execution profiles for that provider
- discard providers with zero compatible profiles
- keep providers with at least one compatible profile

### Step 4: Select Provider And Profile

Select the first compatible provider according to the shared ordering rules.

Then select the profile according to one of the following:

- explicit caller profile if given
- plugin-selected preferred profile if declared
- shared default profile selection rule, typically `default`

### Step 5: Fast Fail On Empty Intersection

If the final candidate set is empty, fail before job creation.

The error should state:

- what the caller requested, if anything
- what providers the plugin supports
- what profiles are available on the host
- why no intersection exists

### Step 6: Compile For The Selected Provider

Only after provider/profile resolution succeeds should the plugin run the provider-specific compiler.

The plugin compiles once for the chosen target.

This is intentionally different from compiling multiple variants and letting Jobs decide later.

## Shared Default Convention

To keep behavior uniform across plugins, the resolver should provide a platform-wide default convention.

A reasonable initial convention is:

- GPU-distributed workloads: require `gpu_distributed`
- GPU-only workloads: prefer `gpu`
- CPU-capable workloads: prefer `subprocess`, then `cpu`
- Host-only workloads: require `subprocess`

Plugins may narrow this based on job semantics, but they should not invent new fallback rules unless the shared resolver supports them.

The point of the convention is not to eliminate plugin intent. The point is to make the common case predictable.

## Why Subprocess Must Be First-Class

Raising `subprocess` to a first-class provider is not just an implementation cleanup. It fixes a correctness issue.

### Honest Contracts

A `cpu` step should mean a CPU container-oriented job.

A `subprocess` step should mean a host subprocess job.

Those two contracts have different semantics around:

- working directory
- container image ownership
- command interpretation
- environment inheritance
- filesystem expectations
- runtime dependencies

Treating one as a hidden rewrite of the other makes the contract dishonest.

### Better Validation

When `subprocess` is explicit, plugins can validate subprocess-specific invariants during compilation.

Examples:

- absolute path requirements
- required host-side tools
- command shape validation
- environment/secret injection needs

The `evaluate-suite` job already demonstrates this pattern by compiling directly to subprocess and validating path assumptions at compile time.

### Better Local/Remote Unification

If local execution is supposed to be jobs-backed, then `subprocess` is the natural first-class local execution provider.

This lets the platform unify local and remote around one jobs architecture without pretending that a host process is a CPU container.

## Local Versus Production

This spec intentionally avoids making plugins branch directly on a vague "local vs production" flag unless absolutely necessary.

The preferred rule is capability-driven selection.

- if subprocess profiles are available, jobs that support subprocess may choose them according to the shared resolver
- if subprocess profiles are absent, those jobs fall back to their other supported providers or fail

This means production policy is expressed by profile availability.

- local deployments may expose `subprocess/default`
- production deployments should typically not expose subprocess profiles at all

The plugin remains mostly environment-agnostic because it chooses from actual available capabilities.

A platform runtime or deployment label may still be useful for diagnostics or edge cases, but it should not be the primary selector when profile availability already captures the real execution options.

## Proposed Plugin API Shape

The current repo uses a single `compile(...)` path per job. This spec proposes splitting the decision from the compilation.

Conceptually, a job should provide:

- supported providers
- optional provider preference order for a given spec
- one compiler per supported provider, or one dispatching compiler that compiles based on a selected provider

The shared resolver then:

- resolves the provider and profile
- passes that selection into the plugin compile path

This can be represented in several concrete APIs. The exact method names are implementation detail. The architectural requirement is:

- plugins express support and provider-specific compilation
- shared code performs selection
- Jobs receives only the final, already-honest `PlatformJobSpec`

## Fast-Fail Requirements

Fast failure is a core requirement of this spec.

The system must fail before job creation when:

- the caller selected a profile unsupported by the plugin
- the caller selected a profile not configured on the host
- the plugin supports only providers that are unavailable on the host
- the selected provider requires compile-time invariants that are not satisfied

Failure messages should be structured enough to answer these questions immediately:

- what did the caller ask for
- what does the plugin support
- what is available on this host
- what should the user or operator change to make it work

This avoids partially compiled jobs and opaque runtime failures.

## Migration Plan

This spec can be adopted incrementally.

### Phase 1: Standardize Resolver Inputs

- define the built-in providers
- add shared plugin-layer helpers for declaring supported providers and preference order
- expose Jobs execution profiles as the source of host availability

### Phase 2: Introduce Provider-Specific Compilation

- update plugin jobs to compile explicitly for subprocess, CPU, GPU, or distributed GPU as appropriate
- allow plugins that support multiple providers to branch after shared resolution, not before

### Phase 3: Remove Jobs Rewrite

- delete the CPU-to-subprocess translation at Jobs API ingress
- require subprocess jobs to be compiled explicitly as subprocess

### Phase 4: Unify Local Execution Through Jobs

- migrate local `run_local(...)` flows toward a jobs-backed subprocess path
- keep synchronous vs asynchronous interaction mode separate from execution placement

## Consequences For Existing Job Types

### Evaluate-Suite Style Jobs

Jobs like `evaluate-suite` are already close to the target architecture.

They explicitly compile to `subprocess`, validate subprocess-specific assumptions up front, and do not rely on the Jobs API to reinterpret a container step.

### Evaluator / Data-Designer Style Jobs

Jobs that currently compile to `cpu` should either:

- remain honest CPU container jobs, or
- gain explicit subprocess compilation support and let the shared resolver choose between subprocess and CPU

They should not rely on Jobs to decide that a CPU job is actually subprocess.

### Customization / Training Jobs

GPU and distributed GPU training jobs should continue to compile explicitly for the appropriate GPU providers.

If they do not support subprocess, they simply declare that they do not support it. The resolver will then fail or fall back accordingly.

## Acceptance Criteria

This spec should be considered successful only if all of the following are true.

- `subprocess` is represented as an explicit first-class provider in plugin compilation and Jobs validation.
- The Jobs service no longer rewrites `cpu` container steps into subprocess steps.
- Plugins use a shared resolution algorithm rather than per-plugin ad hoc heuristics.
- Execution selection uses caller intent, plugin support, and host-available profiles as its inputs.
- Incompatibility produces a fast failure before job creation.
- The same logical resolution rules apply across plugins unless a plugin explicitly narrows its supported providers.
- Container ownership is explicit for `cpu`, `gpu`, and `gpu_distributed`, and absent from `subprocess`.
- Local jobs unification can treat subprocess as the normal first-class local execution provider.

## Open Questions

A few detailed decisions remain for implementation.

## Recommendation

- make `subprocess` explicit
- resolve execution before compile
- compile once for the selected provider
- let Jobs validate and dispatch, not reinterpret

That provides a shared convention across plugins, honest execution semantics, fast failure, and a cleaner path toward full local/remote jobs unification.
