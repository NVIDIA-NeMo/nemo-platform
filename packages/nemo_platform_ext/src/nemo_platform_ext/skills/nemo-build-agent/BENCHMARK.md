# Skill benchmark: nemo-build-agent

## Publication status

Not yet eligible for publication. The evaluation dataset is present, but the
required baseline and skill assisted NV ACES run has not been executed in this
checkout.

## Evaluation metadata

- Skill: `nemo-build-agent`
- Evaluation date: not run
- Evaluator version: not recorded
- Agents: Codex and Claude Code required
- Tasks: 6 application tasks
- Attempts: at least 2 per task required
- Environment: isolated sandbox with NeMo Fabric and Docker

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

## Informal baseline observation

On 2026-08-31, an independent planning agent was asked to handle the refund
agent scenario without reading the target skill. This was a qualitative
authoring check, not an NV ACES run and not publication evidence. The baseline
correctly selected MCP for custom code and proposed broad unhappy path coverage.
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
