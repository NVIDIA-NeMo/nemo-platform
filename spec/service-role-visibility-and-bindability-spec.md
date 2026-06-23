# Service Role Visibility And Bindability Spec

## Summary

This spec explores whether service-defined roles should carry metadata controlling whether they are visible and bindable.

This is intentionally separate from `plugin-service-authz-spec.md`.

The plugin service authz spec stays focused on:

- permissions
- service-scoped roles
- path rules

It does not require role visibility/bindability metadata in the first iteration.

## Current Assumption

For the initial plugin authz design, the implicit default assumption is:

- roles are visible
- roles are bindable

This spec explores whether the platform should later make those properties explicit.

## Problem

Some service-defined roles may be appropriate as normal user/admin-assigned roles.

Examples:

- `agents.Reviewer`
- `customization.Approver`

Other roles may be useful in policy but should not necessarily be exposed or directly granted.

Examples:

- `agents.SystemWorker`
- `guardrails.BackgroundSync`
- `customization.InternalRunner`

Without explicit metadata, the platform may treat all service-defined roles as equally visible and equally assignable.

## Goals

- Explore whether service-defined roles need explicit metadata for visibility and bindability.
- Determine whether these concepts should affect IAM, UI, CLI, and docs behavior.
- Keep the main plugin authz redesign unblocked.

## Non-Goals

- Changing the first iteration of `plugin-service-authz-spec.md`.
- Redesigning the core role model.

## Concepts

### Visibility

Visibility answers:

- should this role be shown in UI/CLI/docs/IAM listing surfaces?

Possible values:

- visible
- hidden

### Bindability

Bindability answers:

- may this role be directly granted to principals through normal role-binding APIs?

Possible values:

- bindable
- non-bindable

These are separate concerns:

- a role could be hidden but bindable
- a role could be visible but non-bindable
- a role could be both hidden and non-bindable

## Options

### Option 1: Keep Roles As Simple Definitions Only

Roles contain only:

- name
- description
- permissions

Pros:

- simplest model
- no additional IAM/UI complexity

Cons:

- no way to distinguish customer-facing roles from internal policy roles

### Option 2: Add Explicit Visibility And Bindability Flags

Conceptual example:

```python
RoleDef(
    name="agents.SystemWorker",
    description="Internal worker role",
    permissions=[...],
    visible=False,
    bindable=False,
)
```

Pros:

- explicit
- clear platform behavior for UI/CLI/IAM/doc surfaces
- supports internal-only roles cleanly

Cons:

- adds more surface area to role definitions
- more implementation work across APIs and presentation layers

### Option 3: Add Bindability Only

Only define whether a role can be bound directly.

Visibility is handled by conventions or presentation-layer heuristics.

Pros:

- smaller change
- addresses the more security-sensitive concern first

Cons:

- still leaves UI/docs ambiguity

## Recommendation

Defer this from the initial plugin authz redesign.

Do not block `plugin-service-authz-spec.md` on solving role visibility/bindability metadata.

If the platform later needs internal-only service roles, Option 3 or Option 2 can be added as follow-up work.

## Relationship To Plugin Service Authz

`plugin-service-authz-spec.md` should assume the simple model for now and avoid taking on extra role metadata concerns in its first version.

This spec exists so the question is captured for follow-up work without complicating the core decorator/path-rule redesign.
