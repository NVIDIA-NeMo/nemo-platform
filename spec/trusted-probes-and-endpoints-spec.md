# Trusted Probes And Endpoints Spec

## Summary

This spec explores whether NeMo Platform should add a first-class concept for trusted probes and other trusted endpoint access patterns.

This is intentionally separate from `plugin-service-authz-spec.md`.

The plugin service authz spec stays close to the current implementation and does not introduce a new probe or trusted-endpoint abstraction.

## Current State

The current repo does not appear to have a first-class platform concept for:

- probe caller
- trusted internal endpoint
- mesh-authenticated internal audience

What exists today is much closer to:

- no principal present
- principal present
- service principal identified by `service:` prefix

Some routes are handled through special-case policy logic, but there is no general route-level abstraction for unauthenticated trusted probes or trusted internal callers.

## Problem

Some endpoints, especially health/readiness/operational endpoints, may need semantics different from normal user-facing authorization.

Examples:

- Kubernetes health probes that do not present a principal
- internal services calling operational APIs through mTLS or trusted service identity
- infrastructure components that should be allowed to reach a narrow set of endpoints without following normal user-facing authorization rules

The current authorization model does not provide a clear first-class way to describe these cases.

## Goals

- Explore whether trusted probes should become a platform concept.
- Explore whether trusted internal endpoint access should become a platform concept.
- Determine whether these concepts belong in plugin route policy or in separate transport/network configuration.

## Non-Goals

- Changing `plugin-service-authz-spec.md` in the first iteration.
- Defining the final decorator/path-rule shape for trusted probes.

## Key Question

Should NeMo Platform represent trusted probes and trusted internal endpoint access inside the authorization model, or should those concerns remain outside route policy and be enforced at the transport/network layer?

## Constraints

### Constraint 1: Probes Often Have No Principal

Kubernetes-style probes often look like plain HTTP calls with no NeMo principal attached.

That means they do not naturally fit the current principal-based auth model.

### Constraint 2: Trust May Come From Transport Or Topology

Some "trusted" access may rely on:

- separate port binding
- private network reachability
- service mesh identity
- ingress restrictions
- loopback-only access

Those are not the same thing as route-level principal authorization.

### Constraint 3: Trusted Access Should Not Accidentally Become Public Access

If the platform adds a trusted probe concept, it must fail safely and avoid broadening access unintentionally.

## Options

### Option 1: Keep Probes Outside The Plugin Authz Model

Trusted probes are handled through:

- separate port
- separate listener
- ingress/network policy
- platform-specific operational route exposure

Pros:

- aligns with how many platforms handle health probes
- avoids mixing transport trust with route authorization
- keeps plugin authz simpler

Cons:

- plugin/service authors cannot describe trusted probe behavior directly in route metadata
- requires more deployment/runtime coordination

### Option 2: Add A First-Class Probe Caller Concept

Add a normalized caller concept for something like:

- `PROBE`

Pros:

- route policy can describe probe access explicitly
- easier to reason about from endpoint definitions alone

Cons:

- not obvious how probe identity is established when no principal exists
- may create false confidence if enforcement really depends on network topology

### Option 3: Add A Trusted Endpoint Classification Separate From Callers

Instead of treating probes as callers, endpoints could be classified as:

- normal API endpoint
- operational/probe endpoint

The platform would then apply different serving/exposure rules to those endpoints.

Pros:

- better matches the idea that trust may come from deployment/network shape
- avoids pretending probes are authenticated principals

Cons:

- creates another endpoint dimension
- still needs clear runtime enforcement

## Recommendation

Do not add trusted probes or trusted internal endpoint abstractions to the first plugin authz redesign.

Keep the initial spec focused on:

- callers
- permissions
- roles
- explicit path rules

Explore probes and trusted endpoints separately here.

Option 1 or Option 3 is more likely to fit the current platform model than inventing a principal-like `PROBE` caller immediately.

## Relationship To Plugin Service Authz

`plugin-service-authz-spec.md` should remain fail-closed and require explicit path rules, but it should not attempt to solve trusted probe semantics in its first version.

If the platform later introduces a trusted-probe or trusted-endpoint model, it should be designed and implemented as a focused follow-up using this spec.
