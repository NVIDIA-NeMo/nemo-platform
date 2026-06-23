# Provider And Backend Extensibility Spec

## Summary

This spec captures a long-term design question about how NeMo Platform should evolve its execution model as new backends are introduced.

The key question is:

- when should a new backend fit under an existing provider
- and when should it require a new provider with a new execution contract

This is intentionally separate from the near-term subprocess and execution-resolution work. The current platform can move forward with built-in providers such as `subprocess`, `cpu`, `gpu`, and `gpu_distributed` without settling every future backend mapping question up front.

## Problem

The platform needs a rule for future backend growth.

Today it is easy to talk about:

- `subprocess`
- `cpu`
- `gpu`
- `gpu_distributed`

But future backends may not fit cleanly into those existing categories.

Examples include:

- Slurm
- future distributed batch systems
- alternative cluster schedulers
- backend-specific runtimes with specialized submission contracts

Some of these may preserve an existing provider contract. Others may require a materially different contract.

The platform needs a clean extensibility rule so that provider vocabulary does not become either:

- too broad to be meaningful
- or too specific and backend-leaky

## Core Principle

Providers should represent meaningful execution contracts, not just implementation names.

Backends may vary underneath a provider, but only as long as they preserve the same contract from the plugin and resolver point of view.

That leads to a simple rule:

- if a new backend preserves the same execution contract as an existing provider, it should map to that provider
- if a new backend requires a materially different execution contract, it should introduce a new provider

## What Counts As The Same Contract

Two backends can reasonably share a provider if they preserve the same high-level semantics that matter to plugins and resolution logic.

Examples of contract-level behavior include:

- what kind of command or container shape the plugin compiles
- what kinds of resources and topology the job requests
- what assumptions exist around storage, environment, and execution model
- what lifecycle and validation expectations are visible at compile time

If those things remain meaningfully the same, the backend difference can stay below the provider layer.

If those things diverge enough that plugins would need different compilation rules or different mental models, the platform probably needs a new provider.

## Example: `gpu_distributed`

`gpu_distributed` is a good example of a provider that may have multiple possible backend implementations.

If several distributed GPU schedulers all preserve roughly the same execution contract, then they can all remain under `gpu_distributed`, with backend-specific differences expressed through:

- profile
- backend mapping
- backend configuration

That would keep the provider stable while allowing multiple implementations underneath it.

## Example: Slurm

Slurm is intentionally unresolved.

There are two plausible futures:

1. Slurm fits the existing `gpu_distributed` contract.

   In that case:

   - Slurm should remain a backend under `gpu_distributed`
   - provider selection stays simple
   - profile and backend mapping carry the backend-specific detail

2. Slurm requires a materially different contract.

   In that case:

   - Slurm should become a new provider
   - plugins and resolver logic should treat it as a distinct execution contract

The platform should not force a decision before the actual Slurm design exists.

## Why This Should Stay Separate

This question is important, but it is not required to finish the current provider-resolution cleanup.

The near-term work only needs:

- a clear built-in provider set
- a shared resolution mechanism
- explicit subprocess support
- removal of the dishonest rewrite behavior

Future backend extensibility can be addressed later once there is a concrete design for backends such as Slurm.

## Recommendation

Do not resolve speculative backend mappings in the current execution-resolution spec.

Instead, adopt this rule for future work:

- preserve an existing provider when a new backend preserves the same execution contract
- create a new provider when the backend introduces a materially different contract

That gives the platform a clean long-term extensibility rule without forcing premature decisions about backends that do not yet have a defined runtime model.
