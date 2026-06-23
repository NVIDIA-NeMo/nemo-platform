# Daemon-Group Local Jobs Follow-On Spec

## Summary

This document captures what is currently known about a future `daemon-group` backend for local jobs.

It is intentionally separate from `jobs-local-remote-unification-spec.md`.

The local/remote unification spec standardizes only the local daemon control plane plus the `subprocess` backend.

`daemon-group` remains follow-on work because it introduces a substantially larger lifecycle and control-surface design.

## Why This Is Separate

`daemon-group` is not just another way to launch a local process.

It implies that the managed daemons themselves need a durable control interface and runtime contract.

That adds complexity well beyond the scope of the core jobs local/remote unification work.

In Orchard, this was a substantial design and implementation surface.

The same is likely true here.

## What Daemon-Group Means

`daemon-group` would be a backend for long-lived, supervised local processes where simple child-process execution is not enough.

The intended value is:

- durable local process ownership
- discovery across CLI invocations
- restart and recovery behavior
- better support for long-lived local workloads than one-shot subprocess execution

## What Makes It Hard

The main complexity is that daemon-managed processes need their own contract.

That likely includes:

- daemon identity
- process-group identity
- status and health
- readiness
- control operations
- logs
- recovery state

This is different from the simpler subprocess model where the local jobs daemon can own lifecycle directly without another daemon-facing API layer.

## Relationship To The Local Daemon

The local daemon from the jobs local/remote unification spec would remain the top-level control plane.

If `daemon-group` is added later, the likely shape is:

- CLI talks to the local jobs daemon
- local jobs daemon schedules a job onto the `daemon-group` backend
- `daemon-group` then talks to one or more managed process daemons or daemon wrappers

That means `daemon-group` likely introduces a second control interface below the local jobs daemon.

That extra layer is the main reason it is deferred.

## What Should Stay True

Even if `daemon-group` is added later, the following rules from the main jobs spec should remain true:

- `run` and `submit` are interaction modes only
- all execution still flows through the jobs service contract
- backend choice is explicit and honest
- local log and status access should still go through daemon interfaces rather than direct file inspection from the CLI

## Likely Design Questions

- What exact control interface should daemon-managed processes expose?
- Should that interface also use HTTP/REST over UDS, or a different transport?
- How should readiness and health propagate from managed daemons up to the local jobs daemon?
- How should job logs be streamed through the local jobs daemon when the underlying runtime is daemon-managed?
- How should restart, shutdown, and orphan recovery work?
- How should version and capability checks work between the local jobs daemon and daemon-managed runtimes?
- How should daemon-group state surface through existing jobs APIs?

## Recommendation

Keep `daemon-group` out of the first local/remote jobs unification implementation.

Ship the simpler architecture first:

- local daemon control plane
- REST over UDS local daemon interface
- subprocess as the first-class local backend

Then design `daemon-group` as a dedicated follow-on backend with its own explicit runtime contract.
