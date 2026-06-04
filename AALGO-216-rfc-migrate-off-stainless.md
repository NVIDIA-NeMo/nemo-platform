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

Generated SDK: 1,268 unique classes; 130 (~10%) imported anywhere; 220 (~17%) have zero imports.
Real consumer surface is dominated by hand-maintained vendored extensions (`nemo_platform_ext`, `nemo_evaluator_sdk`, `safe_synthesizer_sdk`) — not generator output.
CLI auto-generation depends on the generated `*Resource` classes via `inspect`.
Plugins inconsistently use the SDK: some go through it, some hit HTTP directly, some bypass via NAT.

~270 server-side `BaseModel` classes in `services/core/*/api/` and `nmp_common` are the source of truth. Stainless produced a parallel client-side copy to bridge the closed-services / open-SDK boundary. That bridge is no longer load-bearing — clients can import the server-side types directly.

## Options

We commit to the plugin-shaped end state: each plugin owns its CLI commands, library surface, and middleware; a thin core handles auth, workspace, base HTTP, IAM/projects/workspaces.

### B. Open-source OpenAPI generator
Switch to `openapi-generator` or `openapi-python-client`.
- **Day-1 cost:** non-trivial (template tuning + ongoing bug ownership)
- **Thin core source:** OSS-generated
- **Holdover during migration:** OSS-generated
- **Best when:** plugin-shaped migration takes an extended period and we need a usable monolithic client in the interim
- **Note:** Re-introduces optional duplication that's no longer necessary under the current structure.

### C. New paid provider (Fern, Speakeasy)
Replace Stainless with a competitor.
- **Day-1 cost:** non-trivial (vendor onboarding + config re-mapping)
- **Thin core source:** provider-generated
- **Holdover during migration:** provider-generated
- **Best when:** we don't trust ourselves to maintain a small thin-core generator and prefer a vendor to own that
- **Note:** Identical lock-in trade we're trying to undo; generates optional duplication.

### D. Reuse existing assets
Drop Stainless. Publish the server-side Pydantic models as a client-importable package. Apply the existing plugin SDK pattern (proven in 6 plugins) to thin-core resources.
- **Day-1 cost:** small
- **Risk:** establishing the boundary between "server-side type" and "client-importable type" needs care (avoid leaking server-only fields/validators)
- **Best when:** we want one source of truth for types from day one

## Migration profile

Plugin-shaped migration is a multi-quarter effort regardless of generator choice. The options differ in day-1 cost and what fills the gap until each domain peels off.

| Option | Day-1 cost | Thin core source | Holdover during migration |
|---|---|---|---|
| B. OSS gen | non-trivial | OSS-generated | OSS-generated |
| C. New provider | non-trivial | provider-generated | provider-generated |
| D. Roll our own | small | hand-written + small gen | mix |

## Cutover

During the migration window we run the frozen Stainless artifact as a no-op holdover for any un-migrated domains. This isn't an end state — APIs change and a frozen client decays — but it costs nothing and lets each domain peel off at its own pace.

## Tentative recommendation

**D then cutover.** Publish the server-side Pydantic models as a client-importable package. Apply the existing plugin SDK pattern to thin-core resources. Run the frozen Stainless artifact as a cutover holdover until each domain is migrated. B is a worse generator for a shape we're leaving; C is paid lock-in for a thin core small enough to hand-maintain.

## Open questions

- **Consumer inventory.** Required pre-flip work. Until we know who imports `nemo_platform.*` and from where, we can't safely freeze.
- **Thin-core boundary.** Exactly which resources belong in the thin core (auth, workspace, base client, pagination, IAM/projects/workspaces/members/secrets/entities/etc.)?
- **Type boundary discipline.** How do we mark server-side types as safe for client consumption (avoid leaking server-only validators or heavy dependencies)?