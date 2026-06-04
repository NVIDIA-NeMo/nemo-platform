# RFC: Migrate off Stainless

**Status:** Draft  
**Author:** Max Dubrinsky  
**Linear:** AALGO-216

## Why now

Two forcing functions converged:
- Stainless is going source-available + unmaintained.
- The closed-services / open-SDK split that originally required client-side type duplication has dissolved (services and SDK now ship together; plugins already import server-side types directly).

The first forces us off Stainless. The second changes what replaces it.

## Today

~270 server-side `BaseModel` classes in `services/core/*/api/` and `nmp_common` are the source of truth. Stainless produced a parallel client-side copy to bridge the closed-services / open-SDK boundary. That bridge is no longer load-bearing — clients can import the server-side types directly.

The generated SDK contains 1,268 unique classes, but only ~130 (~10%) are imported anywhere in the codebase, and ~220 (~17%) have zero imports. The real consumer surface is dominated by hand-maintained vendored extensions (`nemo_platform_ext`, `nemo_evaluator_sdk`, `safe_synthesizer_sdk`), not generator output.

CLI auto-generation depends on the generated `*Resource` classes via `inspect`. Plugins inconsistently use the SDK: some go through it, some hit HTTP directly, some bypass via NAT.

## Cutover

During the migration window we run the frozen Stainless artifact as a no-op holdover for any un-migrated domains. This isn't an end state — APIs change and a frozen client decays — but it costs nothing and lets each domain peel off at its own pace.

## Options

### B. Open-source OpenAPI generator

Switch to `openapi-generator` or `openapi-python-client`. Keep the monolithic shape short-term while plugins peel off.
- **Day-1 cost:** non-trivial (template tuning + ongoing bug ownership)
- **Risk:** quality is reliably worse than Stainless; long tail of generator bugs we own
- **Best when:** we need a usable monolithic client during migration and don't trust ourselves to maintain a small thin-core generator

### C. New paid provider (Fern, Speakeasy)

Replace Stainless with a competitor. Same shape, different vendor.
- **Day-1 cost:** non-trivial (vendor onboarding + config re-mapping)
- **Risk:** identical lock-in trade we're trying to undo
- **Best when:** we don't trust ourselves to maintain a small thin-core generator and prefer a vendor to own that

### D. Reuse existing assets

Drop Stainless. Publish the server-side Pydantic models as a client-importable package. Apply the existing plugin SDK pattern (proven in 6 plugins) to thin-core resources.
- **Day-1 cost:** small
- **Risk:** establishing the boundary between "server-side type" and "client-importable type" needs care (avoid leaking server-only fields/validators)
- **Best when:** we want one source of truth for types from day one

## Open questions

- **Consumer inventory.** Required pre-flip work. Until we know who imports `nemo_platform.*` and from where, we can't safely freeze the generator for cutover.
- **What's in the thin core?** The RFC assumes auth, workspace, base HTTP, IAM/projects/workspaces, but we should confirm the exact boundary (e.g., do `secrets`, `entities`, `models` belong?).

## Tentative recommendation

**D.** Publish the server-side Pydantic models as a client-importable package. Apply the existing plugin SDK pattern to thin-core resources. Run the frozen Stainless artifact as a cutover holdover until each domain is migrated.

B and C are explicit rejections: they regenerate a parallel client-side type tree that was necessary under the old constraints but is now optional cost.