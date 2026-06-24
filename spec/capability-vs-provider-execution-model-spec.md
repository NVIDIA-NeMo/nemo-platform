# Capability Versus Provider Execution Model Spec

## Summary

This spec captures a future architectural question that is intentionally out of scope for the current execution-resolution proposal:

- are `cpu`, `gpu`, and `gpu_distributed` best modeled as providers
- or are they more accurately modeled as capabilities that can be satisfied by different providers and backends

The current repository often treats `subprocess`, `cpu`, `gpu`, and `gpu_distributed` as peers in one selection space. That is useful for near-term cleanup, but it may not be the correct long-term data model.

This document records the follow-up design problem so the platform can return to it later without blocking the current work.

## Problem

There is a modeling mismatch in the current terminology.

- `subprocess` describes an execution mechanism
- `docker` and `kubernetes_job` describe backend implementations
- `cpu`, `gpu`, and `gpu_distributed` often read more like workload requirements or capabilities than execution mechanisms

That mismatch becomes more obvious when a single backend instance may be able to satisfy multiple capabilities.

Examples:

- a host subprocess executor may satisfy `cpu`
- that same host subprocess executor may satisfy `gpu` if the host has GPU access
- a cluster backend may satisfy `cpu`, `gpu`, and `gpu_distributed`
- one backend controller may manage all three without implying three different controllers

If that is the real architecture, then `cpu`, `gpu`, and `gpu_distributed` should not necessarily be modeled as the same kind of thing as `subprocess`.

## Why This Matters

If capabilities and providers are conflated, several problems follow.

- the resolver has to treat requirements and mechanisms as if they were interchangeable
- the platform may appear to need separate controllers for each top-level category when one backend instance can satisfy several of them
- plugin intent becomes harder to express precisely
- it becomes harder to represent cases like \"GPU required, subprocess acceptable if the host has GPU capability\"

The immediate example is:

- a job requires GPU capability
- Docker is unavailable
- the host can still run GPU work directly
- a subprocess-based executor with GPU capability should be able to satisfy the requirement
- if no available executor satisfies GPU capability, the job should fail immediately

That is easier to express if GPU is modeled as a capability requirement rather than as the executor type itself.

## Candidate Model

A more explicit long-term model may separate at least four concepts.

### Capability

What the workload requires.

Examples:

- `cpu`
- `gpu`
- `gpu_distributed`

### Provider Or Execution Mode

How the workload is meant to run.

Examples:

- `subprocess`
- `container`
- `batch`

The exact vocabulary is open. The important thing is separating mechanism from requirement.

### Backend

The implementation that actually runs the job.

Examples:

- host subprocess launcher
- Docker runtime
- Kubernetes job controller
- Volcano or Slurm batch backend

### Profile

A named configured instance or policy that binds the above concepts to concrete runtime configuration.

Examples:

- a local subprocess profile with GPU access
- a Docker CPU profile
- a Kubernetes GPU profile
- a distributed batch profile

## Resolver Implications

Under a capability-oriented model, resolution becomes a match across:

- caller constraints
- workload capability requirements
- execution-mode preferences
- available profiles
- backend capability advertisements

That would allow the platform to express cases such as:

- require GPU capability
- prefer subprocess if available
- otherwise use a containerized backend
- fail if no executor with GPU capability exists

This is different from the current simpler model, where top-level selection is done directly among `subprocess`, `cpu`, `gpu`, and `gpu_distributed`.

## Controller Implications

This modeling question also affects controller design.

If one backend instance can satisfy multiple capabilities, then the platform should not be forced into a one-controller-per-capability shape.

A more natural model may be:

- one backend instance
- one controller
- multiple advertised capabilities
- multiple profiles or policies bound to that backend

This would avoid duplicating control surfaces when the runtime is actually shared.

## Scope Of This Spec

This spec is exploratory and intentionally separate from the current execution-resolution cleanup.

It does not propose immediate code changes.

It exists to preserve an important architectural question:

- whether the long-term model should separate capability, provider, backend, and profile more explicitly than the current repository does

## Recommendation

Keep this question out of the near-term subprocess-resolution work so that the current cleanup can stay focused.

Return to it later when the platform is ready to revisit:

- execution data modeling
- controller ownership
- backend capability advertisement
- profile semantics

At that point, the platform can decide whether `cpu`, `gpu`, and `gpu_distributed` should remain top-level providers or become capability classes matched against more general execution providers and backends.
