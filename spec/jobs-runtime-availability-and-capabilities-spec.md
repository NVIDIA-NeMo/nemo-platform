# Jobs Runtime Availability Spec

## Summary

This spec defines how NeMo Platform should determine which job execution providers and profiles are actually available at runtime, and how that information should be exposed to other services and plugins.

The key architectural change is:

- the Jobs service becomes the authoritative source of truth for execution availability
- availability is determined dynamically from both configuration and runtime checks
- plugins and other services query Jobs for the available providers and profiles instead of inferring them independently

This spec is intentionally separate from execution-selection and subprocess-first-class work. Its purpose is to define how the platform knows what is actually available to select from.

## Problem

Today the platform does not have one clear, runtime-authoritative source of truth for execution availability.

### What Happens Today

Today, availability is inferred indirectly rather than owned explicitly by Jobs.

- platform config expresses intended runtime and configured executors
- startup-time config validation may mutate that view based on runtime checks
- Jobs derives its default profiles mostly from runtime and config
- some plugins still perform their own direct availability checks before compile or submit

Examples in committed code:

- platform config can downgrade `platform.runtime: docker` to `Runtime.NONE` if Docker is unreachable in [packages/nemo_platform_plugin/src/nemo_platform_plugin/config.py](/Users/rsadler/src/nemo-platform/packages/nemo_platform_plugin/src/nemo_platform_plugin/config.py:605)
- Docker reachability is checked by `validate_docker_available()` in [packages/nemo_platform_plugin/src/nemo_platform_plugin/config.py](/Users/rsadler/src/nemo-platform/packages/nemo_platform_plugin/src/nemo_platform_plugin/config.py:344)
- Jobs builds its `profiles` list from runtime and config in [services/core/jobs/src/nmp/core/jobs/config.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/config.py:64)
- default Jobs profiles are selected from runtime in [services/core/jobs/src/nmp/core/jobs/controllers/backends/config.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/controllers/backends/config.py:44)
- customization code independently checks Docker runtime and reachability in [packages/nmp_customization_common/src/nmp/customization_common/contributor/jobs.py](/Users/rsadler/src/nemo-platform/packages/nmp_customization_common/src/nmp/customization_common/contributor/jobs.py:17)

### Why This Is A Problem

This creates a few structural problems.

- static configuration is treated as if it were the same thing as actual runtime availability
- plugin behavior can drift because plugins are pushed to implement their own reachability and environment checks
- other services cannot reliably know what Jobs can actually execute without reproducing Jobs assumptions
- in a microservice deployment, only Jobs is in the right position to know which execution backends are actually usable

Configuration describes intent. It does not necessarily describe reality.

A profile may be configured but unusable because:

- Docker is not reachable
- the process is not running in the expected runtime environment
- a backend dependency is missing
- a control surface exists in config but is not actually available

The platform needs one place where those questions are answered definitively.

## Goals

- Make Jobs the authoritative source of truth for execution availability.
- Distinguish configured execution profiles from actually available execution profiles.
- Perform dynamic runtime checks in Jobs so availability reflects the real execution environment.
- Expose a Jobs-owned API that other services and plugins can query once and then use as the basis for shared resolution.
- Eliminate plugin-specific availability detection logic over time.
- Keep availability determination centralized even when Jobs runs as a separate service.
- Make availability reporting explicit enough to support diagnostics and fast failure.

## Non-Goals

- This spec does not define the provider/profile resolution algorithm itself.
- This spec does not define how plugins compile jobs once a provider/profile has been selected.
- This spec does not define platform startup or service-loading behavior beyond what is necessary to explain availability ownership.
- This spec does not define long-term capability-versus-provider data modeling.

## Architectural Principle

The key rule in this spec is:

- Jobs owns runtime execution availability because Jobs is the service that actually dispatches execution

Other services and plugins may cache or consume Jobs-reported availability, but they should not be the authority for deciding what execution backends are truly usable.

This matters especially in a microservice architecture.

If Jobs is a separate service, then:

- plugin processes do not necessarily run in the same runtime environment as Jobs
- plugin processes may not have direct visibility into Docker reachability, local subprocess enablement, or backend control surfaces available to Jobs
- reproducing Jobs environment checks in each plugin would be both brittle and inconsistent

For those reasons, Jobs should own availability detection and publish the result.

## Terminology

### Configured Profile

A provider/profile pair that exists in platform or Jobs configuration.

This expresses intended support, not guaranteed runtime usability.

### Available Profile

A configured profile that Jobs has determined is actually usable in the current environment.

This is the profile set that other services should resolve against.

### Runtime Availability Check

A check performed by Jobs to determine whether a configured backend/profile is actually usable.

Examples include:

- Docker reachability
- runtime environment compatibility
- presence of required backend dependencies
- availability of required control surfaces

## Proposed Model

Jobs should maintain two distinct views:

- configured execution profiles
- available execution profiles

Configured profiles come from platform config and Jobs config.

Available profiles are the subset that survive Jobs-owned runtime checks.

Only the available set should be published as the source of truth for plugin resolution.

## Availability Determination

Jobs availability should be determined from two inputs.

### 1. Configuration

Configuration determines what is intended to be enabled.

Examples:

- whether subprocess execution is enabled
- which explicit provider/profile entries exist
- which backend defaults are enabled for the platform runtime

Configuration answers:

- what could exist if the environment is healthy

### 2. Runtime Checks

Runtime checks determine what is actually usable right now.

Examples:

- whether Docker is reachable
- whether the runtime environment matches the configured backend type
- whether backend-specific dependencies are present
- whether the required control plane or control surface is available

Runtime checks answer:

- what Jobs can actually dispatch right now

### Combined Rule

Jobs should expose only the intersection:

- configured and enabled
- runtime-validated and usable

That combined set is the availability contract.

## Proposed Jobs API

Jobs should expose an API for runtime execution availability.

The exact path and schema can be decided later, but the API should be able to answer at least:

- which providers exist
- which profiles are available for each provider
- which backend each available profile maps to
- optionally, why a configured profile is unavailable

A minimal shape might include entries like:

- provider
- profile
- backend
- available: true/false
- reason, when unavailable

The key architectural requirement is not the exact JSON schema. It is that Jobs owns and publishes the availability result.

## Client Usage Model

Plugins and other services should query Jobs once for availability, then run their shared deterministic resolver against that returned set.

That means the typical flow becomes:

1. plugin/service obtains available profiles from Jobs
2. plugin/service runs shared provider/profile resolution locally using that availability set
3. plugin compiles the final job spec for the selected provider/profile
4. Jobs validates and dispatches the same provider/profile that was resolved

This preserves a shared deterministic algorithm while keeping availability ownership centralized in Jobs.

## Why This Should Be Owned By Jobs

Jobs is the correct owner for three reasons.

### Jobs Dispatches Execution

Jobs is the service that ultimately routes provider/profile selections to real backends. It is therefore the service most qualified to say whether those backends are usable.

### Jobs Sees The Real Runtime Context

Jobs runs in the environment that matters for dispatch.

That environment may differ from:

- the CLI process
- a plugin service process
- a code-generation or planning context

If Jobs is remote, only Jobs truly knows what its own runtime can access.

### Central Ownership Prevents Drift

If plugins each decide for themselves whether Docker, subprocess, or another backend is available, drift is inevitable.

Centralizing availability in Jobs means:

- one check implementation
- one source of truth
- one observable contract for the rest of the platform

## What Changes Relative To Today

Today:

- availability is inferred indirectly from runtime/config
- some checks happen outside Jobs
- plugins may perform their own validation

Proposed:

- Jobs performs or owns the runtime availability checks
- Jobs distinguishes configured profiles from available profiles
- Jobs exposes availability through an API or equivalent service boundary
- plugins stop inventing their own availability logic and consume the Jobs result instead

## Fast-Fail Implications

A Jobs-owned availability API improves fast failure.

Instead of plugins guessing from static config or partial runtime assumptions, they can fail using one explicit source of truth.

That allows clearer failures such as:

- profile configured but currently unavailable because Docker is unreachable
- provider unsupported in this deployment because it is not enabled
- no available profile satisfies the requested provider

This is better than asking every plugin to construct these messages independently.

## Open Questions

- Should Jobs expose only available profiles, or both configured and available profiles?
- Should unavailability reasons be part of the public API, or just internal diagnostics?
- Should availability be computed once at Jobs startup, periodically refreshed, or both?
- How should Jobs represent transient availability loss after startup?
- Should clients be expected to cache availability for the duration of a request, process, or longer?
- What is the right API surface: direct Jobs HTTP endpoint, SDK call, or both?

## Recommendation

Adopt a Jobs-owned runtime availability model.

The platform should stop treating static configuration as the authoritative source of truth for execution availability.

Instead:

- Jobs should determine what is actually usable
- Jobs should publish that result
- plugins and other services should consume it once and resolve against it

That keeps availability centralized in the only service that can truly know what execution backends are usable, especially in a multi-service deployment.
