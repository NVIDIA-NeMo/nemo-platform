# Agent-lifecycle skill routing — delivery plan

**Date:** 2026-05-21
**Author:** mdubrinsky (with Claude Code)
**Status:** Ready to implement
**Trigger:** Transcript `2026-05-21-101401-can-you-please-clean-up-the-agents-currently-depl.txt` — agent took 2m 25s to clean up three deployed agents, thrashing on localhost probes and `--help` discovery before landing on `nemo agents undeploy` / `delete`.

## Goals

1. Give "clean up my agents" (and per-agent CRUD generally) a clear skill home so future agents land there directly.
2. Eliminate the duplicated platform-discovery probe across skills.
3. Disambiguate the routing for "clean up" so it doesn't default to a platform teardown.

## Non-goals

- Adding a CLI healthcheck command (`nemo services healthcheck`). Out of scope for this change; the discovery skill will keep wrapping `lsof` + `curl` until/unless the CLI ships one.
- A routing-evaluation harness for Claude Code skills. Deferred — captured in bd memory `skill-routing-eval-fixture`.
- Scoping or excluding dev-focused `CLAUDE.md` files from agent auto-discovery. Deferred to a separate conversation with mstaats — captured in bd memory `claude-md-scope-discovery`.
- Adding hard "first action must be Read X" directives to repo `CLAUDE.md` / `AGENTS.md`. Dropped — if the existing DO/DO NOT block isn't enough, more imperatives won't help.

## Deliverables

### D1. `nemo-service-discovery` skill (foundation)

**Path:** `packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-service-discovery/SKILL.md`

**Owner of:** the canonical "is the platform up?" probe. Read-only. No state changes.

**Probe tiers:**

- **Tier 1** — `lsof -iTCP:8080 -sTCP:LISTEN`. Cheap, works under macOS sandbox, ground truth for "is something bound to the canonical port."
- **Tier 2** — `curl -fsS http://localhost:8080/v1/models -o /dev/null -w "%{http_code}\n"`. Functional check; `2xx`/`4xx` both mean "up." Only runs when tier 1 shows a listener.
- **Tier 3** — `ps`/`ls` conflict check for multiple platform processes or data dirs. Only runs when tiers 1 and 2 are both empty AND the user asserted the platform should be running.

**Interpretation table** (single source of truth — currently duplicated across `nemo-skill-selection`, `nemo-status`, `nemo-teardown`):

| Tier 1 | Tier 2 | Verdict |
|---|---|---|
| listener | 2xx/4xx | `PLATFORM_UP` |
| listener | no-response / 5xx | `PLATFORM_WEDGED` |
| empty | n/a (skipped) + tier 3 finds other procs/dirs | `MULTIPLE_INSTALLS` |
| empty | n/a (skipped) + tier 3 clean | `PLATFORM_DOWN` |

**Sandbox handling:** explicit note that under macOS sandbox, `curl` to `localhost:8080` fails with exit 7 / "Couldn't connect after 0 ms" even when the platform is up. If a runtime can disable the sandbox (Claude Code's `dangerouslyDisableSandbox: true`), retry. If not, trust tier 1 and skip tier 2.

**Frontmatter:** marked `user-invocable: false` — this is a building-block skill, not a user-facing one. `allowed-tools: [Bash, Read]`.

**Verification:** runs end-to-end in three states: cold machine (returns `PLATFORM_DOWN`), running platform (returns `PLATFORM_UP`), running platform under sandbox (returns `PLATFORM_UP` via tier 1 fallback).

---

### D2. `agents-manage` skill (user-facing)

**Path:** `plugins/nemo-agents/src/nemo_agents_plugin/skills/agents-manage/SKILL.md`

**Why plugin-owned:** the `nemo agents` CLI surface (`list`, `get`, `delete`, `undeploy`, `deployments`, etc.) is implemented by the `nemo-agents` plugin (`plugins/nemo-agents/src/nemo_agents_plugin/cli.py`). The plugin already hosts skills for `agents-optimize`, `agents-secure`, `skills-optimization`. `agents-manage` is the natural fourth peer.

**Scope:**

- Listing agents and deployments (`nemo agents list`, `nemo agents deployments list`)
- Inspecting one (`nemo agents get <name>`, `nemo agents logs <name>`)
- Undeploying — specific deployment, or all deployments for an agent (`nemo agents undeploy --agent <name>`)
- Deleting agent registrations (`nemo agents delete <name>`)
- Bulk variants ("remove all failed deployments," "delete all agents") with snapshot-then-confirm, matching `nemo-teardown`'s pattern

**Explicitly out of scope:**

- `deploy` and `create`. Initial deployment requires the workflow YAML context — that stays with `nemo-build-agent`. Re-deploy of an existing agent is also build-agent's territory.
- Platform teardown. That stays with `nemo-teardown`.

**Pre-flight:** `Read` on `nemo-service-discovery/SKILL.md`, invoke tier 1 only. If `PLATFORM_DOWN`, route to `setup` and stop.

**Enforced invariants:**

- Undeploy-before-delete order. The skill states this as a rule, not an accident.
- On bulk operations: snapshot what will be deleted, present the count to the user, require explicit confirmation before action.
- Verification: re-run `nemo agents list` and `nemo agents deployments list` after action, report the actual delta.

**Disambiguation question:** when the user says "clean up" without specifics, the skill asks once: "all agents and deployments / specific agent(s) / only failed deployments / dry-run snapshot?" No silent assumption about scope.

**Frontmatter triggers:** `clean up agents`, `delete agent`, `remove deployment(s)`, `undeploy`, `list my agents`, `what agents do I have`, `wipe deployments`.

**Frontmatter:** `user-invocable: true`, `allowed-tools: [Bash, Read]`.

---

### D3. Update `nemo-skill-selection` decision table

**Path:** `packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-skill-selection/SKILL.md` (and the installed mirror under `.agents/skills/nemo-nemo-skill-selection/SKILL.md` if it doesn't auto-regenerate).

**Replace the over-broad row** —

```
| "shut down", "stop NeMo", "tear down", "clean up" | nemo-teardown |
```

— **with two rows**:

```
| "clean up the platform", "shut down NeMo", "tear down", "nemo down"     | nemo-teardown    |
| "clean up agents", "delete agent X", "remove deployment(s)", "undeploy", | agents-manage    |
|   "list my agents", "what agents do I have"                              | (plugin-owned)   |
```

**Tie-breaker rule** added under the table:

> If two rows match, prefer the more specific noun. `clean up X` where `X` ∈ {agent, agents, deployment, deployments} → `agents-manage`. `clean up` where the noun is {platform, NeMo, everything} or absent → `nemo-teardown`. If the noun is genuinely ambiguous, ask one disambiguating question before picking.

**Catalog block update** ("If nothing matches" section): add `agents-manage` to the list of plugin-owned skills alongside `agents-optimize`, `agents-secure`, `guardrails`, `evaluator`, `auditor`, `data-designer`, `anonymizer`.

**Pre-flight section update:** replace the inline tiered probe with a `Read` of `nemo-service-discovery/SKILL.md`, invoke tier 1, branch on the verdict. (Same change reduces from ~10 lines of duplicated bash to ~2 lines of skill dispatch.)

---

### D4. Refactor `nemo-status` and `nemo-teardown` to consume `nemo-service-discovery`

**Paths:**

- `packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-status/SKILL.md`
- `packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-teardown/SKILL.md`

**Change:** replace inline `lsof` + `curl` blocks with a `Read` of `nemo-service-discovery/SKILL.md`. `nemo-status` invokes the full sequence (that's its job). `nemo-teardown` invokes tier 1 only as its idempotency gate.

**Critical caveat to preserve:** the existing prose about "don't trust `nemo services status` or `nemo services ls`" needs to migrate into `nemo-service-discovery`. That gotcha must not get lost in the refactor.

## Sequencing

```
D1 (service-discovery)
  ├── D3 (skill-selection update — depends on D1 existing to Read)
  ├── D4 (status + teardown refactor — depends on D1 existing)
  └── D2 (agents-manage — depends on D1 for its pre-flight)
        └── D3 (skill-selection adds the agents-manage route — depends on D2 existing)
```

Critical path: D1 → D2 → D3. D4 can land in parallel with D2 once D1 is in.

## Verification

Per-deliverable verification is encoded in each skill's own verification section. Plan-level verification:

1. **Manual transcript replay.** Run a fresh agent against `"clean up the agents currently deployed in my local nemo instance"` and confirm:
   - First action is reading `nemo-skill-selection` (or directly routing to `agents-manage`).
   - No `--help` discovery loop.
   - No repeated `curl` retries.
   - Asks the disambiguation question if scope is unclear.
2. **Negative case.** Run against `"shut down nemo"` and confirm the agent still routes to `nemo-teardown`, not `agents-manage`.
3. **Cold-platform case.** Stop the platform, then run `"list my agents"` and confirm the agent routes through service-discovery and surfaces `PLATFORM_DOWN` before attempting any CLI call.

## Risks and open questions

- **Two-tier skill layout drift.** Sources at `packages/.../skills/<name>/SKILL.md` vs. installed mirrors at `.agents/skills/nemo-<name>/SKILL.md` already differ in metadata. This plan adds two new skills to the source tree; whichever process syncs to `.agents/` needs to pick them up. **Action:** verify the install/sync path mirrors new skills before declaring D1 and D2 done.
- **CLI healthcheck command** would shrink `nemo-service-discovery` to ~10 lines. Out of scope here but worth tracking — if/when shipped, D1 becomes a thin wrapper.
- **Plugin-owned skill discoverability.** `agents-manage` lives in the plugin tree; verify the harness's skill catalog actually advertises plugin-owned skills on equal footing with `nemo_platform_ext` skills. If not, file separately.

## Deferred items (tracked elsewhere)

| Item | Where | Why deferred |
|---|---|---|
| Routing-eval harness using `## Examples` blocks in skills | bd memory `skill-routing-eval-fixture` (in `~/.beads-planning`) | Infra investment not justified by a 3-row table change; revisit when there are more routing changes to validate |
| Dev-focused `CLAUDE.md` auto-loading into agent context | bd memory `claude-md-scope-discovery` (in `~/.beads-planning`) | Larger problem about discovery scope; needs conversation with mstaats |
| Hard "first action must be Read X" directives in repo `CLAUDE.md` | Dropped | If existing DO/DO NOT block is ignored, more imperatives won't help; lean on agent reasoning + better skills |

## References

- Transcript: `2026-05-21-101401-can-you-please-clean-up-the-agents-currently-depl.txt`
- `nemo-agents` plugin CLI: `plugins/nemo-agents/src/nemo_agents_plugin/cli.py`
- Existing plugin-owned skills: `plugins/nemo-agents/src/nemo_agents_plugin/skills/{agents-optimize,agents-secure,skills-optimization}/`
- Source skills tree: `packages/nemo_platform_ext/src/nemo_platform_ext/skills/`
- Installed skills mirror: `.agents/skills/`
