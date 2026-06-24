# Caller Execution Hints And Profile Plumbing Spec

## Summary

This spec captures a separate platform problem from provider resolution itself:

- how caller-supplied execution preferences are represented
- how those preferences are transported through plugin APIs
- how consistently those preferences are honored today

The immediate focus is profile plumbing, but this document also provides a place to discuss whether caller-visible APIs should eventually expose more explicit execution hints such as provider or mode preferences.

## Problem

Today, caller-facing execution controls are inconsistent across layers.

At a high level:

- plugin-facing submit surfaces are largely profile-oriented
- the lower-level Jobs API is provider-and-profile oriented through `platform_spec`
- some plugin routes do not yet consistently honor caller-supplied `profile` and `options`

This makes it unclear what a caller can actually control and how reliably those controls propagate through the stack.

## Current Behavior

### Plugin-Facing Submission

The plugin CLI and scheduler expose caller-facing inputs such as:

- `--profile`
- `-o` / `--options-file`

The submit path sends `spec`, `profile`, `options`, and metadata in [packages/nemo_platform_plugin/src/nemo_platform_plugin/scheduler.py](/Users/rsadler/src/nemo-platform/packages/nemo_platform_plugin/src/nemo_platform_plugin/scheduler.py:143).

However, the newer `add_job_routes(...)` path explicitly notes that `profile` and `options` are not yet fully threaded through the request model and may currently be silently dropped server-side in [packages/nemo_platform_plugin/src/nemo_platform_plugin/jobs/routes.py](/Users/rsadler/src/nemo-platform/packages/nemo_platform_plugin/src/nemo_platform_plugin/jobs/routes.py:30).

So today, even the simpler profile-oriented contract is not fully consistent.

### Jobs Service Submission

The lower-level Jobs API accepts a `platform_spec` directly in [services/core/jobs/src/nmp/core/jobs/api/v2/jobs/schemas.py](/Users/rsadler/src/nemo-platform/services/core/jobs/src/nmp/core/jobs/api/v2/jobs/schemas.py:121).

At that level, the caller can effectively control both:

- provider
- profile

because each step executor in `platform_spec` carries those fields explicitly.

This means the plugin-facing and Jobs-facing caller models are not the same.

## Why This Is A Problem

- callers do not have one clearly documented execution-control contract
- profile plumbing is not consistent across plugin submission paths
- the platform does not have a settled answer for whether caller-visible APIs should remain profile-only or allow more explicit execution hints
- this ambiguity makes it harder to reason about what should be resolved automatically versus what should be caller-directed

## Goals

- Define one clear caller-facing execution-control contract for plugin submission APIs.
- Make caller-supplied `profile` handling consistent across plugin routes.
- Decide whether caller-visible APIs should remain profile-oriented or also support explicit provider or mode hints.
- Separate caller intent from plugin/provider resolution in a way that remains understandable to users.

## Non-Goals

- This spec does not define the provider/profile resolution algorithm itself.
- This spec does not define runtime availability detection or the Jobs-owned availability API.
- This spec does not define long-term capability-versus-provider data modeling.

## Key Questions

- Should plugin-facing APIs expose only `profile`?
- Should plugin-facing APIs also expose provider hints?
- Should plugin-facing APIs expose execution-mode hints such as host subprocess versus container preference?
- How should caller hints interact with plugin-supported providers and Jobs-reported availability?
- Which caller controls are required for advanced use cases, and which should remain internal platform details?

## Recommendation

Treat this as a separate design problem from execution resolution itself.

The current execution-resolution proposal should assume only that caller intent may exist. This document should decide:

- what exact caller-visible controls exist
- how they are transported
- how they are validated
- how they interact with plugin and Jobs behavior
