# Jobs-Backed Local Run UX And Progressive Start Spec

## Summary

This spec captures a separate long-term product and platform question:

- when local execution becomes jobs-backed, what should happen to today's `run_local(...)` user experience
- how does that transition relate to progressive service start

This is intentionally separate from provider resolution and subprocess-first-class work. The current execution-resolution proposal can preserve existing local behavior during migration, while this document defines the longer-term direction.

## Problem

Today, `run_local(...)` is an in-process execution path in [packages/nemo_platform_plugin/src/nemo_platform_plugin/scheduler.py](/Users/rsadler/src/nemo-platform/packages/nemo_platform_plugin/src/nemo_platform_plugin/scheduler.py:79).

That gives local execution a lightweight experience:

- spec validation happens locally
- `to_spec()` runs locally
- a local `JobContext` is constructed
- `job.run(...)` is invoked directly
- the command behaves like a simple synchronous local action

If local execution moves behind Jobs, the underlying architecture changes materially:

- local runs become jobs-backed
- subprocess becomes the local execution provider
- Jobs owns persistence, lifecycle, logs, and reconciliation

That creates a product question:

- should `run` continue to preserve the current lightweight local UX
- or should it eventually become a thin synchronous wrapper over jobs submission and waiting

## Current Direction

For the near-term migration, the platform should minimize disruption.

That means preserving existing local functionality and user expectations as much as possible while moving the underlying execution model toward Jobs.

However, that preservation should be treated as transitional compatibility, not the long-term architectural goal.

## Long-Term Direction

Long term, the platform should not preserve today's separate `run_local(...)` execution model.

Instead:

- local execution should become fully jobs-backed
- the old in-process local execution path should eventually be removed
- any remaining local UX sugar should be justified explicitly as product behavior, not as a separate execution architecture

The platform should not carry two fundamentally different local execution models forever.

## Why This Depends On Progressive Start

The main blocker to removing today's local-only behavior is startup and control-plane overhead.

If local execution becomes jobs-backed before the platform has a good progressive-start story, users may experience:

- slower startup
- more visible control-plane machinery
- more operational complexity for simple local runs

That would make the architecture cleaner internally while making the local user experience worse.

So the long-term removal of `run_local(...)` should be addressed together with progressive service start and related UX work, not inside the provider-resolution spec.

## Scope Of This Spec

This spec is about:

- local run UX during and after jobs-backing
- the long-term removal of the separate in-process local execution path
- how that interacts with progressive service start

This spec is not about:

- provider resolution
- runtime availability ownership
- capability-versus-provider modeling

## Recommendation

Treat today's local `run_local(...)` behavior as transitional compatibility during the migration to jobs-backed local execution.

Do not make preserving that behavior a requirement of the execution-resolution spec.

Instead:

- keep current local behavior intact in the short term to minimize migration impact
- plan to remove the separate in-process local execution path in the long term
- resolve the user-facing transition as part of progressive service start and local Jobs UX design
