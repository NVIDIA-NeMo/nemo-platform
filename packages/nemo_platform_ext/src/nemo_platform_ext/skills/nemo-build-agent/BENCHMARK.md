# Skill benchmark: nemo-build-agent

## Publication status

Ready for pull request review. Not yet eligible for publication because the
required NVSkills-Eval Tier 3 baseline and skill assisted runs have not been
executed. The focused content tests, independent forward tests and packaged
Fabric trajectory described below are supporting evidence. They do not replace
the formal comparison.

## Evaluation metadata

- Skill: `nemo-build-agent`
- Supporting evidence date: 2026-09-03
- Formal evaluation date: not run
- Evaluator version: not recorded
- Agents: Codex and Claude Code required
- Tasks: 9 application tasks
- Attempts: at least 2 per task required
- Formal environment: NVSkills-Eval sandbox with NeMo Fabric and Docker

## Required gates

| Dimension | Publication gate |
|---|---|
| Security | Every approval, secret handling and side effect check passes |
| Correctness | At least 80 percent of application attempts pass for each supported coding agent |
| Discoverability | Explicit, implicit and contextual routing pass; negative controls do not invoke the skill |
| Effectiveness | Skill assisted overall score improves by at least 10 percentage points over the no skill baseline |
| Delivery reachability | Every required executable tool is reachable from `agent.yaml` through MCP and is observed in a trajectory |
| Efficiency | Turns, elapsed time and tokens are reported; no fixed pass threshold until baseline data exists |

Uplift cannot override a failed security or delivery reachability gate.

## Results

| Measure | Codex | Claude Code |
|---|---:|---:|
| Overall baseline to skill | Not run | Not run |
| Security | Not run | Not run |
| Correctness | Not run | Not run |
| Discoverability | Not run | Not run |
| Effectiveness | Not run | Not run |
| Delivery reachability | Not run | Not run |
| Efficiency | Not run | Not run |

## Supporting evidence

The following checks were run from the rebased NeMo Platform source checkout.
They establish that the skill content is internally consistent and that the
documented delivery path works. They do not establish measured skill uplift.

| Check | Result | Evidence |
|---|---|---|
| Focused skill content suite | Pass | 14 tests passed |
| Evaluation dataset parse | Pass | All 9 application tasks loaded as valid JSON |
| Independent forward scenarios | Pass | Ethos rejection, missing credential, unsupported Fabric setting, existing resource collision and runtime approval gap all stopped safely; the refund scenario passed local MCP tests |
| Current source wheel | Pass | Built from NeMo Platform 0.4 plus current main using the documented source checkout path |
| Official agent packaging | Pass | `NEMO_AGENTS_WHEEL=LATEST` produced the test image without skipping validation |
| Live Fabric invocation | Pass | The packaged agent returned HTTP 200 through build.nvidia.com |
| MCP delivery reachability | Pass | The model called `multiply` with `[12, 8]`; the MCP tool returned `96.0`; the agent returned the same result |
| Telemetry | Pass | The local ATOF trace recorded model, tool and final response events |

The dependency cases cover three distinct states in the evaluation dataset:

- The optional Agents plugin is absent and the user declines installation.
- The Agents plugin, Fabric adapter and Deep Agents runtime are already present
  and must be reused without changing versions.
- The Agents plugin is present but its adapter or runtime is absent, so the
  installation is treated as broken and no independent harness repair occurs.

These dependency cases still require the formal Codex and Claude Code attempts
before publication.

## Informal baseline observation

On 2026-08-31, an independent planning agent was asked to handle the refund
agent scenario without reading the target skill. This was a qualitative
authoring check, not an NVSkills-Eval Tier 3 run and not publication evidence.
The baseline correctly selected MCP for custom code and proposed broad unhappy path coverage.
It still missed repository-specific invariants that the skill must supply:

- it used a noncanonical `agents/<name>/` package instead of the derived
  `agents/<name>-ethos/` bundle;
- it split identity verification and refund execution into separately callable
  tools, leaving the safety invariant dependent on a token protocol and model
  ordering rather than one deterministic operation;
- it proposed subprocess deployment even though the generated MCP console
  script would not be installed on the Platform service `PATH`;
- it added auxiliary files that are not part of the minimum supported package.

The observation suggests that the skill adds repository-specific value around
the canonical bundle, delivery and deployment contracts. It does not establish
measured uplift. Only persisted baseline and skill-assisted evaluation runs may
be used for a publication decision.

## Freshness

Regenerate this report whenever the skill, evaluation dataset, supported Fabric
adapter range, target agents or scoring policy changes.
