# Memory triage proposals — `pi-hermes:CONSOLIDATED:user`

## Run

- **council:** `azure-anthropic-claude-sonnet-4-5`, `nvidia-nvidia-nemotron-3-nano-30b-a3b`, `nvidia-moonshotai-kimi-k2-6`
- **started:** 2026-06-02T20:42:08.663025+00:00
- **finished:** 2026-06-02T21:11:11.094795+00:00
- **elapsed:** 1742.4s
- **proposals:** 71
- **errors:** 0
- **skipped entries:** 0

## Summary

| verdict | count | % of proposals |
| --- | ---: | ---: |
| `drop` | 1 | 1.4% |
| `merge` | 0 | 0.0% |
| `refine` | 28 | 39.4% |
| `promote_to_prompt` | 0 | 0.0% |
| `keep` | 42 | 59.2% |

## `drop` (1)

### `3ebdcd9b6c4913b5`

- **verdict:** `drop` (confidence 0.67)
- **scores:** quality=0.40, necessity=0.20

**Original entry:**

> Comfortable with uncertainty and explicit about unknowns. Will say "I genuinely don't know" rather than guessing. Values honesty about knowledge gaps in decision-making.

**Justification:** This entry describes general epistemic virtue (admitting unknowns, honesty about limits) that should already be part of any competent AI agent's base behavior. It lacks specific retrievable details about the user's preferences or context, and appears to restate default assistant behavior rather than capture meaningful user-specific information.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `drop` (quality=0.20, necessity=0.10, 4.4s)
  - This entry describes general epistemic virtue (admitting unknowns, honesty about limits) that should already be part of any competent AI agent's base behavior. It lacks specific retrievable details about the user's preferences or context, and appears to restate default assistant behavior rather than capture meaningful user-specific information.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.9s)
  - The statement is a useful guideline but could be more specific and actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `drop` (quality=0.50, necessity=0.00, 23.3s)
  - Admitting uncertainty rather than guessing is default behavior already enforced by standard system prompts; the entry restates a universal baseline without adding a user-specific preference or phrasing requirement that would change outcomes.

## `refine` (28)

### `a2904a90b343a7bf`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.65, necessity=0.72

**Original entry:**

> Strongly dislikes adding imperatives/directives in front of existing DO/DO NOT blocks in AGENTS.md. "If an agent isn't obeying [the DO/DO NOT block], then I don't know what will." Don't stack ceremony in front of existing instructions. 
> 
> ## Communication style and output preferences
> 
> Prefers terse output, ≲ one terminal screen. Wants response lengths kept shorter — feedback that output "just longer than my screen" was too long.

**Refined text proposed:**

> ## Documentation philosophy
> 
> Strongly dislikes adding imperatives/directives in front of existing DO/DO NOT blocks in AGENTS.md. Direct quote: "If an agent isn't obeying [the DO/DO NOT block], then I don't know what will." Don't stack ceremony in front of existing instructions.
> 
> ## Output preferences
> 
> Prefers terse output, ≲ one terminal screen. Keep response lengths shorter — feedback that output "just longer than my screen" was too long.

**Justification:** Entry contains specific, actionable preferences about AGENTS.md structure and output length that would directly change agent behavior. However, it mixes two distinct topics (documentation philosophy and output length) that should be separated for better retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.85, 5.1s)
  - Entry contains specific, actionable preferences about AGENTS.md structure and output length that would directly change agent behavior. However, it mixes two distinct topics (documentation philosophy and output length) that should be separated for better retrieval.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 3.5s)
  - The entry expresses a clear style preference but is not fully concrete or unambiguously retrievable, and removing it would affect tone rather than essential behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `refine` (quality=0.70, necessity=0.80, 28.3s)
  - Entry contains two distinct, high-signal preferences—AGENTS.md editing style and output length bounds—that should be atomic for accurate retrieval, though both are specific and actionable.

### `0cf94a88d9bf510e`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.68

**Original entry:**

> Prefers deep "under the hood" explanations that connect abstract mechanisms to familiar experiences ("you've used this without realizing"). Appreciates bridging theory to practice rather than surface-level how-to guides. 
> 
> ## Time estimates and planning
> 
> Dislikes time estimates in agentic development contexts: "I don't care about estimates and they only serve to muddy the waters. We're all doing agentic development, so engineering days means very little." "Estimates muddy the waters." Considers them subjective and unlikely to influence decisions unless something will take a year. Prefers categorical scales (none/small/non-trivial) over specific durations. What matters is whether a slice depends on hard design calls, not calendar-day framing.

**Refined text proposed:**

> ## Explanation style
> 
> Prefers deep "under the hood" explanations that connect abstract mechanisms to familiar experiences ("you've used this without realizing"). Appreciates bridging theory to practice rather than surface-level how-to guides.
> 
> ## Time estimates and planning
> 
> Dislikes time estimates in agentic development contexts. Direct quotes: "I don't care about estimates and they only serve to muddy the waters. We're all doing agentic development, so engineering days means very little." "Estimates muddy the waters."
> 
> Considers time estimates subjective and unlikely to influence decisions unless something will take a year. Prefers categorical scales (none/small/non-trivial) over specific durations. What matters is whether a slice depends on hard design calls, not calendar-day framing.

**Justification:** Entry contains specific, verifiable preferences with direct quotes about time estimates and categorical scales. However, it awkwardly combines two distinct topics (explanation style and planning preferences) that should be separated for better retrievability.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.80, 8.1s)
  - Entry contains specific, verifiable preferences with direct quotes about time estimates and categorical scales. However, it awkwardly combines two distinct topics (explanation style and planning preferences) that should be separated for better retrievability.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.80, necessity=0.40, 4.4s)
  - The entry captures clear preferences about deep explanations and aversion to time estimates, but could be sharpened for precision.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.85, 17.6s)
  - The entry includes verbatim quotes and specific categorical alternatives (none/small/non-trivial) that make it verifiable and highly actionable; removing it would change both explanation depth and planning framing.

### `1b1ef746cf511fe9`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.65

**Original entry:**

> Prefers planning sessions before implementation when tackling complex fixes. When asked "do you have enough information to get started or would you like a planning session?", explicitly requested a plan before coding. 
> 
> ## Technical preferences — code quality and style
> 
> "I'm always in favor of more static typing, dynamic typing is a bug in potentia." Uses EntityClient as reference for preferred typing style.

**Refined text proposed:**

> ## Workflow preferences
> 
> Prefers explicit planning sessions before implementation when tackling complex fixes. When offered the choice "do you have enough information to get started or would you like a planning session?", explicitly requested a plan before coding.
> 
> ## Code quality preferences — type safety
> 
> Strongly prefers static typing over dynamic typing: "I'm always in favor of more static typing, dynamic typing is a bug in potentia." References EntityClient as example of preferred typing style.

**Justification:** The entry contains specific preferences (planning before implementation, static typing advocacy with a memorable quote) but mixes two distinct topics that should be separated. The planning preference and typing philosophy are both actionable but would be more retrievable as separate focused entries.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.70, 5.7s)
  - The entry contains specific preferences (planning before implementation, static typing advocacy with a memorable quote) but mixes two distinct topics that should be separated. The planning preference and typing philosophy are both actionable but would be more retrievable as separate focused entries.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.80, necessity=0.50, 6.3s)
  - The entry captures specific planning and typing preferences but could be clearer and more concise.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.75, 105.1s)
  - Contains a precise user quote about static typing and references EntityClient as a concrete style anchor, alongside a specific workflow preference for planning complex fixes. Removing it would change concrete code-generation and task-planning decisions not covered by a generic system prompt.

### `225dfc15f4624267`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.70, necessity=0.85

**Original entry:**

> When monitoring PRs for code review feedback: Apply good CodeRabbit suggestions automatically, but justify and reply to unhelpful ones before resolving. Team member feedback carries more weight — flag those for user review instead of fixing automatically.

**Refined text proposed:**

> For PR code review feedback: (1) CodeRabbit suggestions: apply good ones automatically, but reply with justification before resolving unhelpful ones. (2) Team member feedback: always flag for user review rather than applying automatically, as human feedback carries more weight than automated tools.

**Justification:** The entry contains specific, actionable workflow guidance about handling different types of PR feedback (CodeRabbit vs team members), which would change agent behavior. However, it conflates two distinct rules and could be clearer about the decision tree.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.65, necessity=0.75, 5.8s)
  - The entry contains specific, actionable workflow guidance about handling different types of PR feedback (CodeRabbit vs team members), which would change agent behavior. However, it conflates two distinct rules and could be clearer about the decision tree.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.75, necessity=1.00, 6.2s)
  - The entry provides clear procedural guidance on handling PR feedback with CodeRabbit, but could be sharpened for unambiguous execution. It is specific enough to retain but benefits from tighter wording.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 7.7s)
  - Specific operational preference that names CodeRabbit and distinguishes automated versus human review handling, which would change concrete agent decisions during PR monitoring.

### `2b3f32758b063f73`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.60, necessity=0.63

**Original entry:**

> When reviewing council/multi-reviewer feedback, user wants balanced reasoning that doesn't overweight obvious mechanical fixes (e.g., "vendoring would of course have been fixed"). Focus on substantive issues that require judgment.

**Refined text proposed:**

> When synthesizing multi-reviewer or council feedback for the user, prioritize substantive issues requiring judgment over obvious mechanical fixes. The user considers mechanical issues (like missing vendoring, basic syntax errors) as trivially fixable and wants analysis focused on architectural decisions, design tradeoffs, and non-obvious problems.

**Justification:** The entry captures a specific user preference about how to weight different types of feedback in multi-reviewer scenarios, which would change agent behavior. However, it lacks clarity about what 'council/multi-reviewer feedback' refers to and could be more precise about the desired behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.70, 9.2s)
  - The entry captures a specific user preference about how to weight different types of feedback in multi-reviewer scenarios, which would change agent behavior. However, it lacks clarity about what 'council/multi-reviewer feedback' refers to and could be more precise about the desired behavior.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 6.0s)
  - General guidance on handling council feedback; useful but can be clearer and more specific.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.70, 10.4s)
  - Specific preference for synthesizing council feedback with a concrete example quote; would materially change agent prioritization if removed.

### `2d5005c7ea8c6a13`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.68, necessity=0.72

**Original entry:**

> Values critical thinking and evidence-based pushback. "If there is anything said above that you take issue with, please push back. Think critically!" Expects substantive engagement over deference. When presenting architectural proposals or recommendations, wants validation with concrete evidence from codebase/docs and grounded reasoning. Will explicitly ask "push back on this read and verify this claim" before bringing ideas to coworkers.

**Refined text proposed:**

> Expects critical thinking and evidence-based pushback from the agent. Direct quote: "If there is anything said above that you take issue with, please push back. Think critically!" Prefers substantive engagement over deference. For architectural proposals or recommendations, requires validation with concrete evidence from codebase/documentation and grounded reasoning—not speculation. Before presenting technical ideas to coworkers, will explicitly request: "push back on this read and verify this claim" to ensure claims are validated.

**Justification:** The entry captures a genuine behavioral preference with direct quotes and specific collaborative patterns, but mixes multiple related concepts (critical thinking expectation, evidence validation, pre-stakeholder verification) that could be more clearly structured. The high corroboration (6 sessions) confirms this is a stable preference worth preserving.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.65, necessity=0.75, 24.4s)
  - The entry captures a genuine behavioral preference with direct quotes and specific collaborative patterns, but mixes multiple related concepts (critical thinking expectation, evidence validation, pre-stakeholder verification) that could be more clearly structured. The high corroboration (6 sessions) confirms this is a stable preference worth preserving.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.2s)
  - The instruction is useful but somewhat generic; it could be clarified to explicitly require evidence-based pushback.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 10.5s)
  - Contains verbatim quotes and a highly specific, actionable meta-preference about evidence-based pushback during architectural proposals that is strongly corroborated and clearly distinguishes this user's expectations from default deferential behavior.

### `3a4f5eb974a14f65`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.70

**Original entry:**

> Challenges assumptions and expects evidence-based verification. When told something about code or workflow (e.g., "the rebase didn't change anything"), user will question it ("That cannot be right") and expects concrete proof (git range-diff, patch-ids, byte-level diffs) rather than accepting claims at face value. Provide verifiable evidence, not assertions.

**Refined text proposed:**

> User requires concrete evidence over claims. Example: when told "the rebase didn't change anything," user questioned this and requested verification via git range-diff, patch-ids, and byte-level diffs. Always provide verifiable proof (command outputs, diffs, logs) rather than assertions about code or workflow outcomes.

**Justification:** The entry captures a valuable behavioral pattern about evidence-based verification with specific examples (git range-diff, patch-ids), but the phrasing 'Challenges assumptions and expects evidence-based verification' is somewhat generic. The concrete examples elevate it above generic guidance, but it could be more concise and action-oriented.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.70, 8.4s)
  - The entry captures a valuable behavioral pattern about evidence-based verification with specific examples (git range-diff, patch-ids), but the phrasing 'Challenges assumptions and expects evidence-based verification' is somewhat generic. The concrete examples elevate it above generic guidance, but it could be more concise and action-oriented.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 5.8s)
  - It is a useful guideline but vague; it could be made clearer and more actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 11.4s)
  - Entry captures a distinct, actionable user preference with concrete verification standards (git range-diff, patch-ids, byte-level diffs) and example behaviors; removing it would cause the agent to issue unsupported assertions rather than evidence-based responses.

### `3b633c1de36c5c76`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.60

**Original entry:**

> When user provides explicit design decisions or answers to questions, proceed with those answers rather than continuing extensive exploration. Values efficiency when decisions are already made. When scoping work, prefers to clarify intent if the request is ambiguous rather than having agent guess. Often refines scope or clarifies intent rather than picking from menus. Prefers narrow, well-scoped iterations over committing to large sweeps upfront.

**Refined text proposed:**

> User prefers efficiency: when explicit design decisions or answers are provided, proceed with those rather than continuing exploration. When requests are ambiguous, user prefers the agent clarify intent rather than guess. User favors narrow, well-scoped iterations over committing to large changes upfront.

**Justification:** The entry captures legitimate user preferences around decision-making and scoping that would affect agent behavior, but it conflates multiple distinct preferences into one run-on entry. Breaking it into clearer, more retrievable statements would improve precision.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.50, necessity=0.60, 5.1s)
  - The entry captures legitimate user preferences around decision-making and scoping that would affect agent behavior, but it conflates multiple distinct preferences into one run-on entry. Breaking it into clearer, more retrievable statements would improve precision.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 6.7s)
  - The entry provides useful general guidance but is overly generic and could be phrased more concretely.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 17.6s)
  - Multi-session corroboration confirms durable workflow preferences—especially favoring narrow iterations and clarifying questions over menus or broad sweeps—that would change concrete scoping decisions if removed. The entry is behaviorally specific and actionable, though abstract enough to sit below hard-fact clarity.

### `41503ab4453d0474`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.63

**Original entry:**

> When reviewing PRs that have been open for a while: wants thorough audit across the codebase, not just quick fixes. Appreciates being asked to "be discerning and fan out your team as necessary" when investigating scope/completeness. Values comprehensive investigation of what the PR might have missed or what main has changed since the merge base.

**Refined text proposed:**

> For PR reviews: prefers thorough codebase audits over quick fixes. When PRs have diverged from main, wants comprehensive investigation of what the PR might have missed and what has changed in main since the merge base. Values being prompted to 'be discerning and fan out' to check scope and completeness.

**Justification:** The entry captures a specific behavioral preference for PR reviews (thoroughness over quick fixes, comprehensive scope checking), but uses vague language like 'for a while' and embeds too much context. The core signal—preferring thorough audits and scope investigation for stale PRs—is actionable and would affect agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.70, 5.5s)
  - The entry captures a specific behavioral preference for PR reviews (thoroughness over quick fixes, comprehensive scope checking), but uses vague language like 'for a while' and embeds too much context. The core signal—preferring thorough audits and scope investigation for stale PRs—is actionable and would affect agent behavior.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.6s)
  - Provides valuable guidance but is somewhat generic; clearer phrasing would improve specificity and utility.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 12.8s)
  - Contains a precise user quote and a specific, actionable preference for handling stale PRs that would change the agent's review depth and scope.

### `44321d2304e81f90`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.67

**Original entry:**

> Comfortable with "YOLO" approaches for small changes vs. rigid testing. Pragmatic about testing — willing to YOLO small changes and defer test infrastructure until it's genuinely needed. 
> 
> ## Named people, tools, and projects
> 
> User is Max Dubrinsky (mdubrinsky@nvidia.com, GitHub: maxdubrinsky).

**Refined text proposed:**

> Prefers pragmatic "YOLO" approach for small changes rather than rigid testing requirements. Willing to deploy small changes without tests and defer test infrastructure until genuinely needed rather than building it upfront.

**Justification:** The entry captures a specific user preference about development workflow that would influence agent suggestions around testing, but mixes user identity information (which belongs in a separate structured field) with behavioral preferences. The signal is valuable but presentation needs improvement.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.70, 4.5s)
  - The entry captures a specific user preference about development workflow that would influence agent suggestions around testing, but mixes user identity information (which belongs in a separate structured field) with behavioral preferences. The signal is valuable but presentation needs improvement.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.80, necessity=0.60, 9.1s)
  - The entry captures a specific testing philosophy and mentions a named user, but could be clearer about the scope of 'small changes' and the criteria for deferring test infrastructure.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 16.0s)
  - Captures a distinct, actionable preference about testing pragmatism and willingness to YOLO small changes that would concretely change agent recommendations on when to require tests versus shipping quickly.

### `4c3b54653e36b0a0`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.70

**Original entry:**

> When macOS sandbox causes permission errors with local services, user wants commands run without sandbox immediately (no need to ask first).

**Refined text proposed:**

> When macOS sandbox restrictions cause permission errors with local services (e.g., Docker, databases), user prefers commands to be run with sandbox bypass flags (--no-sandbox or equivalent) immediately without asking for confirmation first.

**Justification:** The entry captures a specific behavioral preference (no need to ask permission) for a concrete scenario (macOS sandbox permission errors with local services), which would change agent behavior. However, it lacks specificity about which local services or what constitutes 'without sandbox' commands.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.80, 5.5s)
  - The entry captures a specific behavioral preference (no need to ask permission) for a concrete scenario (macOS sandbox permission errors with local services), which would change agent behavior. However, it lacks specificity about which local services or what constitutes 'without sandbox' commands.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 6.0s)
  - It is a useful general guideline but lacks concrete specificity; refining will make it clearer and more actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.80, 8.1s)
  - Captures a concrete user preference that changes agent behavior when macOS sandbox errors occur; specific enough to guide retrieval and action without being overly vague.

### `5312e5c7aaf8d182`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.60

**Original entry:**

> Evaluates code review findings critically with justification. Expects "FIX" vs "DON'T FIX" decisions with clear reasoning, not blind acceptance of all suggestions. Uses cost/benefit analysis for proposed changes. Expects critical evaluation with justification for every decision — prefers seeing reasoning for both what gets applied and what gets rejected.

**Refined text proposed:**

> Require agents to critically evaluate code review suggestions, explicitly distinguish between "FIX" and "DON'T FIX" decisions, provide justification, and perform cost/benefit analysis; document reasoning for accepted and rejected changes.

**Justification:** The entry offers useful guidance but remains vague; it can be made more concrete and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.60, necessity=0.80, 4.7s)
  - This entry captures a specific behavioral preference for code review evaluation that would meaningfully change agent behavior (requiring justified FIX/DON'T FIX decisions with cost/benefit analysis). However, it's a general methodological principle that should apply to all code review contexts, making it better suited for the system prompt than retrieval-based memory.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.9s)
  - The entry offers useful guidance but remains vague; it can be made more concrete and actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `refine` (quality=0.50, necessity=0.50, 20.3s)
  - The entry captures a real, corroborated preference for explicit FIX/DON'T FIX reasoning during code reviews, but the text is highly redundant. A concise rewrite will improve retrieval precision without losing signal.

### `55a644cd8f6ff2c0`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.63

**Original entry:**

> Action-oriented when path is clear. "Don't have time to dawdle" — wants implementation over extended discussion when requirements are understood and context is available. Trusts recommended paths when offered choices during complex operations. Will choose autonomous completion of git workflows when given the choice. But: "If you have any questions/concerns, stop and ask." Values getting it right over getting it done fast.

**Refined text proposed:**

> Prefers action over extended discussion when requirements are clear. Direct quote: "Don't have time to dawdle" and "If you have any questions/concerns, stop and ask." Will choose autonomous completion of workflows (e.g., git operations) when offered, and trusts recommended paths during complex operations. Priority hierarchy: getting it right > getting it done fast.

**Justification:** The entry captures valuable behavioral preferences with a direct quote, but mixes multiple concepts (action-orientation, trust in recommendations, git workflow preferences, quality-first mindset) in a way that reduces retrievability. The core signal about balancing speed with correctness is strong and would influence agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.65, necessity=0.75, 6.0s)
  - The entry captures valuable behavioral preferences with a direct quote, but mixes multiple concepts (action-orientation, trust in recommendations, git workflow preferences, quality-first mindset) in a way that reduces retrievability. The core signal about balancing speed with correctness is strong and would influence agent behavior.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.75, necessity=0.35, 8.4s)
  - Specific directives are present but wording is abstract and could be clarified.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 13.9s)
  - Contains precise user quotes and a concrete operational preference (autonomous git workflows) that directly guides when to act vs. when to ask. Three-session corroboration confirms it as a durable, decision-relevant trait.

### `6935e3c6fc1098b3`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.78, necessity=0.73

**Original entry:**

> Has deepagents-cli configured with internal model provider access to many interesting models. Plans to use deepagents as the interface where prompt-tuned models will eventually be exposed. Prefers to do most writing/authoring in Claude Code (Opus-4.7 as best coding model) but run execution in deepagents. Watching token spend — cost-conscious when evaluating multi-model approaches.

**Refined text proposed:**

> Uses deepagents-cli configured with internal model provider access. Plans to expose prompt-tuned models through the deepagents interface. Workflow preference: author code in Claude Code (considers Opus-4.7 the best coding model), then execute in deepagents. Cost-conscious about token spend when evaluating multi-model approaches.

**Justification:** Contains specific, actionable preferences about tooling (deepagents-cli, Claude Code, Opus-4.7) and workflow patterns that would meaningfully affect agent recommendations. However, the entry mixes several distinct facts that could be separated for better retrievability.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.80, 5.6s)
  - Contains specific, actionable preferences about tooling (deepagents-cli, Claude Code, Opus-4.7) and workflow patterns that would meaningfully affect agent recommendations. However, the entry mixes several distinct facts that could be separated for better retrievability.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.80, necessity=0.60, 8.8s)
  - The entry provides concrete details about deepagents-cli usage and token‑cost awareness, but could be clarified and tightened.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.80, 7.1s)
  - Contains specific toolchain preferences (deepagents-cli, Claude Code, Opus-4.7) and a concrete workflow split (author in Claude Code, execute in deepagents) plus cost constraints that would directly shape multi-step coding and planning recommendations.

### `7350bebdc6f86fbf`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.40, necessity=0.43

**Original entry:**

> Proponent of good module separation in code organization, even when it differs from existing patterns in the codebase.

**Refined text proposed:**

> Advocate for clean module separation in code structure, even when it conflicts with existing codebase conventions.

**Justification:** The entry offers a general principle but lacks concrete details or verifiable specifics, making it overly vague.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `drop` (quality=0.20, necessity=0.10, 3.4s)
  - This entry is too vague and could apply to any competent software engineer. It lacks specificity about what constitutes 'good module separation' for this particular user, what patterns they prefer, or concrete examples of when they've advocated for this. Without actionable detail, it won't meaningfully change agent behavior.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 2.6s)
  - The entry offers a general principle but lacks concrete details or verifiable specifics, making it overly vague.
- `nvidia-moonshotai-kimi-k2-6` -> `refine` (quality=0.50, necessity=0.70, 140.8s)
  - The entry conveys a durable preference that overrides the default mimicry of existing patterns, but the indirect 'proponent of' phrasing makes it less retrievable and actionable. Rewriting it as a direct preference sharpens the signal without loss of meaning.

### `7bb47dba9a7be92c`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.60

**Original entry:**

> Prefers proper tool/API usage over guessing: "please use your skills/mcp server (don't just randomly set stuff)" when working with external systems like NVBugs.

**Refined text proposed:**

> When working with external systems (e.g., NVBugs), user expects the agent to use available tools/MCP servers properly rather than guessing or making assumptions. Direct quote: 'please use your skills/mcp server (don't just randomly set stuff)'.

**Justification:** The entry captures a specific user preference about tool usage with NVBugs as a concrete example, and includes a direct quote. However, the phrasing is awkward and could be clearer about what constitutes 'proper' usage versus 'guessing'.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.70, 4.2s)
  - The entry captures a specific user preference about tool usage with NVBugs as a concrete example, and includes a direct quote. However, the phrasing is awkward and could be clearer about what constitutes 'proper' usage versus 'guessing'.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.80, necessity=0.40, 7.9s)
  - The instruction is specific but could be clarified to explicitly define the tool usage and avoid ambiguous phrasing.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 134.9s)
  - Contains a named external system (NVBugs), a specific MCP server reference, and a precise user quote, making it highly retrievable. Removing it could lead the agent to manually guess or set values rather than using the proper integration.

### `84d3ccff688a9114`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.60, necessity=0.60

**Original entry:**

> Tighten text in prompts/instructions — "more text is sometimes less impactful." Values distilled, essential content over verbose explanations. Prefers condensed, to-the-point communication. "Don't try to explain the world" when asking for summaries — wants informative but focused content.

**Refined text proposed:**

> User prefers concise, distilled communication. When creating prompts or instructions, favor brief, essential content over verbose explanations ("more text is sometimes less impactful"). When generating summaries, provide informative but focused content without attempting comprehensive world-building or exhaustive context.

**Justification:** The entry captures a genuine user preference for concise communication with 3-session corroboration, but it combines multiple related points that could be stated more precisely. The advice affects both prompt creation and summary generation behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.70, 5.3s)
  - The entry captures a genuine user preference for concise communication with 3-session corroboration, but it combines multiple related points that could be stated more precisely. The advice affects both prompt creation and summary generation behavior.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 46.1s)
  - General guidance on brevity is clear but could be more specific and verifiable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.60, 14.6s)
  - Entry captures a specific, corroborated user communication preference with direct quotes and clear contexts (prompts/instructions, summaries); removing it would risk verbose outputs the user explicitly dislikes.

### `8f83115f4850f5ef`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.60

**Original entry:**

> Prefers accepting Python tracebacks for rare edge cases (e.g., stat-able but not list-able directories) over defensive TOCTOU permission checks. Values clean error paths for expected failures, tolerates crashes for truly exceptional conditions.

**Refined text proposed:**

> When handling filesystem operations: prefers letting Python raise natural exceptions (e.g., PermissionError, FileNotFoundError) for edge cases rather than adding defensive permission checks that introduce TOCTOU race conditions. Example: accepts that stat-able but not list-able directories will traceback rather than pre-checking permissions. Philosophy: clean error paths for expected failures, tolerate crashes for truly exceptional conditions.

**Justification:** The entry captures a specific technical preference about error handling philosophy (TOCTOU vs exception-based approaches) that would guide implementation decisions. However, it uses jargon without clear context and could be more concrete about what scenarios this applies to.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.65, necessity=0.70, 5.3s)
  - The entry captures a specific technical preference about error handling philosophy (TOCTOU vs exception-based approaches) that would guide implementation decisions. However, it uses jargon without clear context and could be more concrete about what scenarios this applies to.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.50, 5.0s)
  - The entry is fairly specific but could be clarified to better capture the intended error-handling behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.60, 14.7s)
  - The entry captures a specific, technical coding preference anchored by a concrete Python edge-case example and precise terminology (TOCTOU), making it retrievable and actionable for filesystem-related code generation, though it remains a single-observation philosophical stance.

### `b287eaa965ce9712`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.55, necessity=0.53

**Original entry:**

> When evaluating review feedback (like coderabbit comments), prefers to "fan out and get multiple opinions" — have multiple independent reviewers assess each point with different lenses, then synthesize their consensus.

**Refined text proposed:**

> When receiving code review feedback (e.g., from CodeRabbit), prefers to solicit multiple independent opinions: have 2-3 reviewers assess each substantive point independently, asking each to apply different evaluation criteria (correctness, maintainability, performance, user impact), then synthesize their consensus before deciding on action.

**Justification:** The entry captures a specific workflow preference (multiple independent reviewers with different perspectives) but uses vague framing ('fan out', 'different lenses'). It describes a concrete collaborative pattern but lacks precision about when/how to apply it.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.55, necessity=0.60, 5.7s)
  - The entry captures a specific workflow preference (multiple independent reviewers with different perspectives) but uses vague framing ('fan out', 'different lenses'). It describes a concrete collaborative pattern but lacks precision about when/how to apply it.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.8s)
  - The guidance is useful but could be clearer and more precise.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.50, 18.0s)
  - Specific preference tied to a named tool (CodeRabbit) and a concrete methodology with a direct quote, though as an uncorroborated single observation it lacks confirming evidence.

### `c14577e2c749b6a5`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.78, necessity=0.85

**Original entry:**

> Prefers reading long-form documents in Linear rather than in terminal/files. When drafting decision docs or substantial write-ups, post to Linear for easier reading and commenting. 
> 
> ## Code review — council-of-elders pattern
> 
> Uses "council review" pattern for code reviews: multiple independent reviewers examine same diff separately. Review quality bar: "Would the author be glad I flagged this?" (not "technically correct"). Expects 3-8 substantive findings distributed unevenly (anti-checklist rule). Must-fix requires: verbatim quote, named consumer, reproduction path (file:line → trigger → symptom). Prefers precision over quantity; values specific, consequential findings over comprehensive checklists. The point is consensus signal — one reviewer's opinion is noise, two+ reviewers flagging the same thing is signal worth acting on.

**Refined text proposed:**

> ## Document reading preference
> Prefers reading long-form documents (decision docs, substantial write-ups) in Linear rather than terminal/files for easier reading and commenting.
> 
> ## Code review — council-of-elders pattern
> Uses "council review" pattern: multiple independent reviewers examine same diff separately. Review quality bar: "Would the author be glad I flagged this?" (not "technically correct"). Expects 3-8 substantive findings distributed unevenly (anti-checklist rule). Must-fix format requires: verbatim quote, named consumer, reproduction path (file:line → trigger → symptom). Values precision over quantity; prefers specific, consequential findings over comprehensive checklists. Core principle: consensus signal matters—one reviewer's opinion is noise, two+ reviewers flagging the same issue is actionable signal.

**Justification:** Contains highly specific, actionable patterns (council-of-elders review, 3-8 findings, must-fix requirements with file:line format) that would meaningfully change agent behavior. However, the entry conflates two distinct preferences: Linear document reading and code review methodology. Should be split for better retrieval precision.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.85, 8.1s)
  - Contains highly specific, actionable patterns (council-of-elders review, 3-8 findings, must-fix requirements with file:line format) that would meaningfully change agent behavior. However, the entry conflates two distinct preferences: Linear document reading and code review methodology. Should be split for better retrieval precision.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.80, necessity=0.90, 10.2s)
  - The entry is relatively specific and actionable, but could be tightened to improve clarity and retrieval. It provides concrete guidance on review processes that influence the agent's decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 18.0s)
  - High-signal, user-specific workflow preferences with precise thresholds, named patterns (Linear, council-of-elders), and exact quality-bar phrasing; removing it would materially change code-review and document-drafting behavior.

### `cd59e47469ff3772`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.47, necessity=0.50

**Original entry:**

> Thinks architecturally before implementing — considers whether ideas are "in step with project direction" and evaluates second-order implications. Prefers to ground discussions in actual code before reasoning about design.

**Refined text proposed:**

> Prefers concrete, code-grounded design discussions over abstract architectural debates. When evaluating new ideas, explicitly considers alignment with project direction and second-order implications before implementing.

**Justification:** The entry captures useful behavioral patterns but uses vague language ('thinks architecturally', 'prefers to ground') that lacks specificity. The core insight about code-first design discussion is valuable but needs sharper articulation.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.40, necessity=0.50, 4.2s)
  - The entry captures useful behavioral patterns but uses vague language ('thinks architecturally', 'prefers to ground') that lacks specificity. The core insight about code-first design discussion is valuable but needs sharper articulation.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 3.1s)
  - The description is generic and could be sharpened for clarity and retrieval.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.50, 22.0s)
  - Captures a distinct user preference for grounding design discussions in concrete code and evaluating architectural fit, which would guide how the agent structures proposals. However, it is a general behavioral pattern without project-specific anchors, making it typical of single-observation profile entries.

### `d79b57fd26ea50c1`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.50, necessity=0.57

**Original entry:**

> Prefers critical evaluation of automated suggestions (CodeRabbit, linters) — willing to reject suggestions that don't align with actual project config or that introduce unnecessary complexity, even when they come from automated tools.

**Refined text proposed:**

> Critically evaluates automated tool suggestions (CodeRabbit, linters) before accepting — rejects suggestions that conflict with actual project configuration or introduce unnecessary complexity, even from automated sources. Prefers explicit verification over blindly accepting automated recommendations.

**Justification:** The entry captures a valuable preference about critically evaluating automated tools, but it's too vague with generic examples. It would benefit from concrete specifics about which tools, what kinds of suggestions to reject, or examples of rejected suggestions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.40, necessity=0.60, 6.2s)
  - The entry captures a valuable preference about critically evaluating automated tools, but it's too vague with generic examples. It would benefit from concrete specifics about which tools, what kinds of suggestions to reject, or examples of rejected suggestions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 6.4s)
  - The entry captures a useful preference but is somewhat vague; a clearer formulation would make it more actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.60, 12.5s)
  - Names a specific tool (CodeRabbit) and establishes a clear behavioral preference around rejecting automated suggestions that conflict with project config or add complexity. This would change how the agent filters or presents such suggestions, making it retrievable and useful despite being single-observation.

### `e626e4bbb2861be3`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.73

**Original entry:**

> Shell startup performance matters, especially in Python repos where multiple chpwd hooks fire (autoswitch_virtualenv, mise, direnv). Seconds-long shell startup is "workable but not ideal." Async prompts and deferred loading are valued optimizations. 
> 
> ## Tools and workflows — beads
> 
> Prefers beads (`bd remember`) for persistent memory storage over file-based MEMORY.md. Memories should use kebab-case keys and load via `bd prime` at session start. 
> 
> ## Tools and workflows — other
> 
> Prefers to watch parallel agents work via tmux sessions for real-time visibility. When dispatching multiple agents for tasks like code review, create a team setup that allows observing each agent's work in separate panes. When spawning team sessions for background work, prefers tmux-visible sessions so they can monitor progress ("if you can be sure to use a team so sessions launch in tmux that would be helpful").

**Refined text proposed:**

> ## Shell performance sensitivity
> 
> Shell startup performance matters, especially in Python repos where multiple chpwd hooks fire (autoswitch_virtualenv, mise, direnv). Seconds-long shell startup is "workable but not ideal." Values async prompts and deferred loading optimizations.
> 
> ## Memory storage preference: beads over files
> 
> Prefers beads (`bd remember`) for persistent memory storage over file-based MEMORY.md. Memories should use kebab-case keys and load via `bd prime` at session start.
> 
> ## Team monitoring preference: tmux visibility
> 
> Prefers to watch parallel agents work via tmux sessions for real-time visibility. When dispatching multiple agents (e.g., code review tasks), create team setups with separate panes for each agent. When spawning team sessions for background work, use tmux-visible sessions to enable progress monitoring ("if you can be sure to use a team so sessions launch in tmux that would be helpful").

**Justification:** Entry contains specific, actionable preferences (bd remember, bd prime, kebab-case keys, tmux team sessions) that would clearly change agent behavior. However, it conflates three distinct topics (shell performance, beads workflow, tmux monitoring) that should be separated for better retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.85, 6.4s)
  - Entry contains specific, actionable preferences (bd remember, bd prime, kebab-case keys, tmux team sessions) that would clearly change agent behavior. However, it conflates three distinct topics (shell performance, beads workflow, tmux monitoring) that should be separated for better retrieval.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.55, necessity=0.45, 8.3s)
  - The entry offers useful workflow guidance but lacks concrete specifics and could be clarified.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 10.9s)
  - Contains specific, actionable tooling preferences—including named commands (`bd remember`, `bd prime`, `tmux`), exact utilities (`mise`, `direnv`), and a direct quote—that would materially change how the agent sets up environments and dispatches parallel work.

### `ecbfeb8c7243fb9d`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.62

**Original entry:**

> Skills are "capabilities and conventions the agent draws on, not scripts it executes" — avoid making skills overly rigid. Every rigid rule added is future maintenance cost. Prefers to "rely on larger skill routing and context, not rigid skills."

**Refined text proposed:**

> When designing agent skills: treat them as flexible capabilities and conventions, not rigid scripts. Avoid adding strict rules to skills as each one increases future maintenance cost. Instead, rely on skill routing logic and contextual judgment rather than encoding rigid procedures within individual skills.

**Justification:** The entry captures a valuable philosophy about skill design that would affect implementation decisions, but uses vague language ('overly rigid', 'larger skill routing') that reduces retrievability. The core insight about avoiding rigid rules and maintenance cost is actionable but needs clearer expression.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.40, necessity=0.60, 9.4s)
  - The entry captures a valuable philosophy about skill design that would affect implementation decisions, but uses vague language ('overly rigid', 'larger skill routing') that reduces retrievability. The core insight about avoiding rigid rules and maintenance cost is actionable but needs clearer expression.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.7s)
  - The entry conveys an important design principle but is somewhat wordy and could be clearer.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.75, 17.0s)
  - Corroborated user preference containing exact quotes about skill architecture; removing it would alter concrete decisions between rigid scripts and flexible capability-based skills.

### `f5632decb7fda7e1`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.50, necessity=0.50

**Original entry:**

> Prefers "easy stuff first" when tackling problems. Will explicitly call out this approach when breaking down work.

**Refined text proposed:**

> Prefers to sequence work by tackling easier or lower-risk items first when breaking down problems, and explicitly states this prioritization approach (e.g., 'let's start with the easy stuff') when planning task order.

**Justification:** The entry captures a genuine behavioral pattern but is too vague to be reliably retrievable. 'Easy stuff first' lacks specificity about what constitutes 'easy' or how this manifests in problem-solving, and 'explicitly call out' is ambiguous about whether this is a communication preference or just observed behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.40, necessity=0.30, 5.4s)
  - The entry captures a genuine behavioral pattern but is too vague to be reliably retrievable. 'Easy stuff first' lacks specificity about what constitutes 'easy' or how this manifests in problem-solving, and 'explicitly call out' is ambiguous about whether this is a communication preference or just observed behavior.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 33.2s)
  - Moderately specific behavior preference; not a concrete fact but guides tone.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 11.3s)
  - Identifies a specific, actionable user preference for task sequencing that directly changes how the agent should propose breaking down work.

### `fa248bb8026a7f3e`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.63

**Original entry:**

> Prefers interactive, incremental onboarding when exploring new codebases. Wants information "fed" in chunks rather than large reports. Starts exploration by examining types and contracts first to understand how data is structured and used.

**Refined text proposed:**

> When exploring new codebases, prefers incremental onboarding with information delivered in digestible chunks rather than comprehensive reports. Exploration pattern: starts by examining type definitions and interfaces/contracts to understand data structures and usage patterns before diving into implementation details.

**Justification:** The entry captures meaningful behavioral preferences about how the user wants to explore code, which would guide agent responses. However, it could be more specific about what 'types and contracts' means and what 'chunks' looks like in practice.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.60, necessity=0.70, 5.1s)
  - The entry captures meaningful behavioral preferences about how the user wants to explore code, which would guide agent responses. However, it could be more specific about what 'types and contracts' means and what 'chunks' looks like in practice.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 5.4s)
  - Useful general guidance but lacks concrete specifics; can be made clearer.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 10.0s)
  - Captures a specific, actionable workflow preference—chunked onboarding and types-first exploration—that would change how the agent presents unfamiliar codebases. It is semantically retrievable and not obviously covered by a system prompt or another entry.

### `fb1a3473bef6711a`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.50

**Original entry:**

> Treats RFC review feedback as peer input to evaluate, not gospel: "view it through the lens of a peer with whom you might not agree on everything."

**Refined text proposed:**

> When receiving RFC review feedback, evaluates comments critically rather than accepting them unconditionally - treats reviewers as peers whose suggestions should be considered but may not always align with the author's technical judgment.

**Justification:** The entry captures a specific philosophical stance about RFC review feedback that could influence tone and approach, but the current phrasing is somewhat vague. The quote lacks context about who said it or when, and 'treats as peer input' could be made more actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.40, necessity=0.50, 5.9s)
  - The entry captures a specific philosophical stance about RFC review feedback that could influence tone and approach, but the current phrasing is somewhat vague. The quote lacks context about who said it or when, and 'treats as peer input' could be made more actionable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.50, 8.3s)
  - The entry offers useful guidance but could be phrased more clearly and specifically.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.50, 20.1s)
  - Specific behavioral stance with a precise, retrievable quote about RFC review; captures a non-obvious preference for critically weighing feedback that would alter agent output.

### `ffccf834cf1224a4`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.57

**Original entry:**

> Prefers minimal, deliberate solutions over adding configuration mechanisms — "don't want to add that mechanism" when rejecting a sidecar config approach. Favors starting small with explicit overrides and iterating from there.

**Refined text proposed:**

> Design philosophy: prefers minimal, deliberate solutions over adding configuration mechanisms. In a specific discussion, rejected a sidecar config approach saying 'don't want to add that mechanism,' favoring explicit overrides and iteration instead. Applies this 'start small' principle when evaluating architectural choices.

**Justification:** The entry captures a useful design philosophy but lacks context about what domain or type of solution this applies to. The quote is specific but orphaned without knowing what 'sidecar config approach' refers to.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.40, necessity=0.50, 5.0s)
  - The entry captures a useful design philosophy but lacks context about what domain or type of solution this applies to. The quote is specific but orphaned without knowing what 'sidecar config approach' refers to.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 5.9s)
  - The entry captures a useful design principle but is phrased vaguely and could be expressed more precisely.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.70, 15.2s)
  - The entry is anchored by a concrete partial quote and a specific rejected approach (sidecar config), making it both verifiable and retrievable. It encodes a distinct design heuristic that would change the agent's concrete architectural recommendations if removed.

## `keep` (42)

### `27ab19ee42afc820`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.83, necessity=0.83

**Original entry:**

> Prefers condensed, action-oriented UIs. Asked to remove verbose descriptions from skill previews and replace Y/n confirmations with clear multi-choice menus (e.g., "1. Install all 2. Select which 3. Skip"). Likes hierarchical multiselect UIs with sublabels showing structure (plugin name > skill names).

**Justification:** This entry contains specific, actionable UI/UX preferences with concrete examples (Y/n → numbered menus, hierarchical multiselect with sublabels). These are behavioral instructions that would directly change how the agent designs interfaces for this user, making it both high-quality and necessary.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 4.5s)
  - This entry contains specific, actionable UI/UX preferences with concrete examples (Y/n → numbered menus, hierarchical multiselect with sublabels). These are behavioral instructions that would directly change how the agent designs interfaces for this user, making it both high-quality and necessary.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.85, necessity=0.80, 9.4s)
  - High-quality, specific user preference that directly informs UI design decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 15.4s)
  - The entry contains actionable, specific UI preferences with concrete examples (e.g., exact multi-choice menu format and hierarchical sublabel patterns) that would directly change how the agent designs interfaces for this user. It is not generic advice and is unlikely to be duplicated in the system prompt or other memories.

### `3362ba488cf7a744`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.75

**Original entry:**

> When selecting LLM models for configurations, user prefers "frontier chat across all providers" — comprehensive coverage of high-quality chat models from multiple providers (Anthropic, OpenAI, Google, DeepSeek, Qwen, etc.).

**Justification:** This entry captures a specific user preference for LLM model selection strategy with concrete provider names and a clear directive ('frontier chat across all providers'). It would directly influence agent behavior when configuring or recommending models, making it both retrievable and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 4.2s)
  - This entry captures a specific user preference for LLM model selection strategy with concrete provider names and a clear directive ('frontier chat across all providers'). It would directly influence agent behavior when configuring or recommending models, making it both retrievable and actionable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 6.4s)
  - Specific user preference with named providers that could affect configuration decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.80, 7.8s)
  - The entry captures a specific, actionable preference for model selection that would change concrete recommendations, naming multiple distinct providers and a clear coverage principle.

### `7d5cfef6e3046c40`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.92, necessity=0.85

**Original entry:**

> Branch naming convention: `md/<issue-number>-<short-description>`. Prefers `/md` as branch suffix when creating worktrees (not `+md` or other variants).

**Justification:** Highly specific technical preference with concrete details: exact branch naming pattern with issue numbers, explicit preference for `/md` suffix over alternatives like `+md`. This would directly influence decisions when creating branches and worktrees, and the specificity makes it easily retrievable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.85, 4.2s)
  - Highly specific technical preference with concrete details: exact branch naming pattern with issue numbers, explicit preference for `/md` suffix over alternatives like `+md`. This would directly influence decisions when creating branches and worktrees, and the specificity makes it easily retrievable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.80, 6.1s)
  - Specific naming rule that guides concrete branch creation decisions; removal would affect how worktrees are named.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 12.6s)
  - Captures a specific, corroborated user preference for branch naming and worktree suffixes that directly changes generated git commands; removing it would cause the agent to use an unwanted convention.

### `e37c64430111426a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.83, necessity=0.77

**Original entry:**

> When drafting technical content for the user to share with others (team messages, announcements), provide plain editable text rather than trying to match their voice. User explicitly asked for "a couple lines of text that I can edit to sound like me."

**Justification:** This entry captures a specific user preference with a direct quote about providing editable plain text rather than voice-matched content for team communications. It would change concrete agent behavior in drafting scenarios, preventing the agent from attempting to mimic the user's style when they explicitly want raw text to customize themselves.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 4.4s)
  - This entry captures a specific user preference with a direct quote about providing editable plain text rather than voice-matched content for team communications. It would change concrete agent behavior in drafting scenarios, preventing the agent from attempting to mimic the user's style when they explicitly want raw text to customize themselves.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.85, necessity=0.70, 5.5s)
  - Specific user request to output plain editable text for technical content rather than mimic voice.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.80, 7.8s)
  - Contains a precise user quote and specific context (team messages, announcements); removing it would change the agent's output from plain editable drafts to potentially polished, voice-matched text.

### `ef4733acc96c530e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.73, necessity=0.67

**Original entry:**

> Manages dotfiles with GNU Stow for both work and personal machines. Spins up new machines rarely. Prefers declarative, in-repo configuration over implicit machine-local setup. Values shell startup performance, especially in Python repos.

**Justification:** Entry contains specific, actionable preferences (GNU Stow for dotfiles, declarative in-repo config, shell startup performance concerns in Python repos) that would meaningfully influence agent recommendations about development environment setup and tooling choices. While not maximally concrete, it provides clear behavioral guidance.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.70, 6.3s)
  - Entry contains specific, actionable preferences (GNU Stow for dotfiles, declarative in-repo config, shell startup performance concerns in Python repos) that would meaningfully influence agent recommendations about development environment setup and tooling choices. While not maximally concrete, it provides clear behavioral guidance.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.50, 42.0s)
  - The entry gives a clear, specific preference for Stow‑based declarative dotfile management and shell startup performance, making it both retrievable and behavior‑relevant.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.80, 8.4s)
  - Entry names specific tooling (GNU Stow) and actionable preferences (declarative in-repo configuration, optimizing shell startup in Python repos) that would directly change the agent's setup recommendations if removed.

### `09d03f0713454d63`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.87, necessity=0.62

**Original entry:**

> Dislikes overly clinical/medical language in documentation headings — rejected "Anatomy of an Agent" in favor of "Agent Definition" when drafting public docs for the NeMo Platform agents page.

**Justification:** This entry captures a specific, verifiable preference with concrete examples (rejected 'Anatomy of an Agent' for 'Agent Definition'). It represents a documented stylistic decision that could influence future documentation choices, though its impact is limited to tone and word choice rather than functional outcomes.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.65, 3.8s)
  - This entry captures a specific, verifiable preference with concrete examples (rejected 'Anatomy of an Agent' for 'Agent Definition'). It represents a documented stylistic decision that could influence future documentation choices, though its impact is limited to tone and word choice rather than functional outcomes.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.90, necessity=0.50, 6.1s)
  - The entry records a clear stylistic preference, but it could be phrased more precisely to capture the rule.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.70, 17.6s)
  - Concrete stylistic preference backed by exact rejected and accepted headings and the named NeMo Platform project; removing it would risk repeating the disliked clinical phrasing in future documentation tasks.

### `0f7fb9245ec9337d`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.72

**Original entry:**

> Dislikes "techno-jargon" (e.g., "forcing function," "load-bearing") and em-dashes in written docs — these make text sound AI-generated. Wants their own voice to shine through in RFCs and technical writing.

**Justification:** This entry contains specific, actionable writing preferences with concrete examples ("forcing function," "load-bearing," em-dashes) that would directly influence how the agent drafts technical documents. The specificity of disliked terms and punctuation makes it highly retrievable and likely to change agent behavior when writing RFCs or documentation.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 3.3s)
  - This entry contains specific, actionable writing preferences with concrete examples ("forcing function," "load-bearing," em-dashes) that would directly influence how the agent drafts technical documents. The specificity of disliked terms and punctuation makes it highly retrievable and likely to change agent behavior when writing RFCs or documentation.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 5.1s)
  - The entry expresses a clear stylistic preference but is somewhat generic, needing clearer articulation.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 6.8s)
  - The entry gives concrete examples of disliked jargon and punctuation, tied to specific document types (RFCs, technical writing), making it actionable and retrievable. Without it, the agent would likely use those exact phrasings and stylistic choices.

### `1afa1e62e8955f70`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.57

**Original entry:**

> Prefers interactive sessions with think-out-loud reasoning. Wants to be included in the reasoning process, not just presented with conclusions. Values collaborative decision-making over being handed finished answers.

**Justification:** This entry captures a specific interaction preference that would materially affect agent behavior (showing reasoning vs. hiding it). While not maximally concrete, it's actionable enough to change how responses are structured. The preference for collaborative decision-making is verifiable through interaction style.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.60, necessity=0.70, 7.6s)
  - This entry captures a specific interaction preference that would materially affect agent behavior (showing reasoning vs. hiding it). While not maximally concrete, it's actionable enough to change how responses are structured. The preference for collaborative decision-making is verifiable through interaction style.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 5.0s)
  - The entry expresses a clear but generic preference for interactive, collaborative reasoning and should be refined for precision.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.50, 28.0s)
  - Captures a distinct interaction preference that would meaningfully shift agent style toward collaborative, expository reasoning. Reasonably retrievable though it lacks domain or situational specificity.

### `1f841c1e54060e46`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.70

**Original entry:**

> When filing GitHub issues, user prefers to "leave the labeling for someone else" — apply only obviously correct labels, leave discretionary labels to human reviewers.

**Justification:** This is a specific, actionable preference about GitHub workflow behavior that would directly change how the agent labels issues. The preference is clear and verifiable, though it could be slightly more precise about what constitutes 'obviously correct' vs 'discretionary' labels.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 3.0s)
  - This is a specific, actionable preference about GitHub workflow behavior that would directly change how the agent labels issues. The preference is clear and verifiable, though it could be slightly more precise about what constitutes 'obviously correct' vs 'discretionary' labels.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 6.3s)
  - The entry captures a useful user preference but is vague and could be clarified.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 16.0s)
  - This is a specific, behavioral preference about GitHub issue labeling that would change concrete decisions the agent makes. It is clearly scoped and retrievable.

### `2071e206646832a9`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.85, necessity=0.65

**Original entry:**

> When syncing between local and remote document mirrors (e.g., in-repo RFC and Linear doc): update whichever is more current. If both are the same, start with the local copy then push that up. 
> 
> ## Tools and workflows — shell and dotfiles
> 
> Uses zsh with oh-my-zsh. ZDOTDIR is `~/.config/zsh`. Has `.zshrc.local` symlinked to `.config/zsh/locals/.zshrc.work`. Prefers cached completion approach for shell startup performance.

**Justification:** Specific details about sync strategy and zsh configuration, but not critical enough to warrant promotion or removal.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.85, necessity=0.75, 5.8s)
  - Entry contains highly specific, verifiable details (ZDOTDIR path, symlink structure, oh-my-zsh) that would change agent behavior when working with this user's shell configuration. However, it combines two unrelated topics (document syncing and shell setup) which should be separated for better retrieval.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.30, 7.9s)
  - Specific details about sync strategy and zsh configuration, but not critical enough to warrant promotion or removal.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 24.2s)
  - Contains concrete, personal setup details (exact ZDOTDIR paths, symlinks, shell tools) and a specific document-sync workflow rule that would directly change agent behavior; not generic knowledge.

### `24883461872a7245`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.65

**Original entry:**

> Prefers explicit credential mapping between services. Does not want automatic substitution of credentials meant for one API provider as fallback credentials for a different provider, even when upstream code has such fallback chains.

**Justification:** This entry captures a specific architectural preference about credential handling that would directly influence agent behavior when configuring API integrations. It's concrete enough to guide decisions (no automatic credential fallback chains) and has sufficient detail to be actionable, though it could be slightly more specific with examples.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 3.3s)
  - This entry captures a specific architectural preference about credential handling that would directly influence agent behavior when configuring API integrations. It's concrete enough to guide decisions (no automatic credential fallback chains) and has sufficient detail to be actionable, though it could be slightly more specific with examples.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 7.7s)
  - The entry expresses a useful design principle but is somewhat generic; refining it will clarify the required credential mapping behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.60, 19.6s)
  - Captures a specific, non-obvious engineering preference about credential isolation across API providers that would affect concrete decisions when working with multi-provider authentication or fallback logic.

### `2b7aab650de6b343`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.78, necessity=0.70

**Original entry:**

> Finds hour markers in progress indicators "demoralizing" and prefers MM:SS format over H:MM:SS for elapsed time displays, even when duration exceeds 60 minutes (shows 73:21 instead of 1:13:21).

**Justification:** This is a highly specific UI preference with concrete examples (73:21 vs 1:13:21) that would directly change how the agent formats time displays in progress indicators. The preference is verifiable and actionable, with clear emotional context ('demoralizing') that explains the rationale.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 4.1s)
  - This is a highly specific UI preference with concrete examples (73:21 vs 1:13:21) that would directly change how the agent formats time displays in progress indicators. The preference is verifiable and actionable, with clear emotional context ('demoralizing') that explains the rationale.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.30, 6.1s)
  - The observation is specific enough to be meaningful but could be clearer in phrasing and formatting.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 12.7s)
  - The entry records a precise, actionable display preference tied to a specific emotional trigger ('demoralizing') and includes an exact formatting example, making it highly retrievable and behavior-changing when the agent renders elapsed time.

### `33490df8bf4790b5`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.72, necessity=0.65

**Original entry:**

> For bug reports, user wants diagnostic findings without fix recommendations ("avoid making fix recommendations since this is a bug"). Keep bug issues descriptive of the problem, not prescriptive of the solution.

**Justification:** This entry captures a specific, actionable user preference about bug report formatting with a direct quote. It would materially change agent behavior by preventing solution suggestions in bug contexts, which differs from general problem-solving instructions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 3.9s)
  - This entry captures a specific, actionable user preference about bug report formatting with a direct quote. It would materially change agent behavior by preventing solution suggestions in bug contexts, which differs from general problem-solving instructions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.30, 4.6s)
  - The instruction is useful but somewhat generic and could be clarified for consistent application.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 11.1s)
  - Entry captures a precise, quoted user instruction about bug-report style that would directly change agent output if removed; it is concrete and not obviously duplicated.

### `3adf210f1341a445`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.68

**Original entry:**

> When asking about architecture decisions, user wants concrete reusability analysis ("who is consumer #3") rather than speculative abstraction. Values YAGNI principle and practical justification for shared libraries.

**Justification:** This entry captures a specific user preference about architecture discussions - demanding concrete evidence for abstraction decisions rather than theoretical benefits. The YAGNI reference and concrete example ('who is consumer #3') make it actionable enough to influence how the agent frames architectural recommendations, though it could be slightly more specific about contexts where this applies.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.65, necessity=0.75, 4.3s)
  - This entry captures a specific user preference about architecture discussions - demanding concrete evidence for abstraction decisions rather than theoretical benefits. The YAGNI reference and concrete example ('who is consumer #3') make it actionable enough to influence how the agent frames architectural recommendations, though it could be slightly more specific about contexts where this applies.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 3.8s)
  - The entry conveys a useful user intent but is phrased generally; refining it will make the requirement clearer for retrieval and application.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 12.2s)
  - The entry contains a precise user quote ('who is consumer #3') and explicitly names the YAGNI principle, making it specific and retrievable, while its removal would change concrete architecture decisions regarding shared libraries.

### `4fe0da7c8b7f985f`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.80, necessity=0.73

**Original entry:**

> When CodeRabbit suggests a Ruff rule violation, check the project's ruff.toml first — if the rule isn't enabled, the suggestion may be unhelpful. Justify by noting the rule isn't enforced and that fixing creates inconsistency with existing production patterns. Check project lint config before applying style/rule suggestions.

**Justification:** The entry gives a concrete, verifiable instruction about checking ruff.toml before applying Ruff suggestions, which would affect agent decisions if removed.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.65, necessity=0.70, 5.5s)
  - The entry captures a specific, actionable pattern (check ruff.toml before accepting CodeRabbit suggestions) with clear justification logic. However, it's somewhat verbose and could be more concise while retaining the key procedural insight.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=0.90, 6.0s)
  - The entry gives a concrete, verifiable instruction about checking ruff.toml before applying Ruff suggestions, which would affect agent decisions if removed.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.60, 20.0s)
  - Contains specific named tools (CodeRabbit, Ruff, ruff.toml) and an actionable conditional workflow that would change how the agent handles automated lint suggestions, distinguishing it from generic linting advice.

### `552517c9122f43f4`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.63

**Original entry:**

> When resolving conflicts between openshell-sdk refactors and upstream changes: prefer extending the SDK to accept new parameters rather than falling back to inline implementations in consumers like openshell-cli. Keep shared logic in the SDK.

**Justification:** This entry provides specific architectural guidance for a concrete codebase (openshell-sdk and openshell-cli) with a clear decision rule: extend the SDK rather than implement inline in consumers. It's retrievable when working on these specific projects and would meaningfully change design decisions if absent.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 3.8s)
  - This entry provides specific architectural guidance for a concrete codebase (openshell-sdk and openshell-cli) with a clear decision rule: extend the SDK rather than implement inline in consumers. It's retrievable when working on these specific projects and would meaningfully change design decisions if absent.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.50, 4.4s)
  - The guidance is specific to extending the SDK rather than inlining logic, but it could be clearer and more precise.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.65, necessity=0.55, 11.2s)
  - Specific project-level architectural rule tied to named entities (openshell-sdk, openshell-cli) that would steer concrete conflict-resolution decisions, yet it is prescriptive guidance rather than an unambiguous fact.

### `59c8938da3dfc3dc`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.57

**Original entry:**

> Prefers all project outputs in consistent locations under REPO_ROOT (e.g., nat-jobs/, eval-out/, optimizer_results/). When adding new output directories, check existing stages first to match the pattern.

**Justification:** Entry provides specific, actionable guidance with concrete examples (nat-jobs/, eval-out/, optimizer_results/) that establishes a verifiable project organization pattern. This would directly influence the agent's decision about where to place new output directories, making it necessary to retain.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.70, 3.6s)
  - Entry provides specific, actionable guidance with concrete examples (nat-jobs/, eval-out/, optimizer_results/) that establishes a verifiable project organization pattern. This would directly influence the agent's decision about where to place new output directories, making it necessary to retain.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.40, 9.3s)
  - General guidance on output directory placement; specific enough to be useful but could be made more concrete.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.60, 18.5s)
  - Provides specific, retrievable directory patterns (nat-jobs/, eval-out/, optimizer_results/) and actionable guidance for output placement that would change concrete file organization decisions.

### `5e218e8023703797`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.87, necessity=0.83

**Original entry:**

> When filing bugs, user prefers minimal investigation — capture the repro and symptoms, don't deep-dive into root cause. User said "Don't work too hard, the person fixing it can dig" when asked not to over-investigate code during bug filing.

**Justification:** This entry captures a specific, actionable workflow preference with a direct quote that would change agent behavior during bug filing. The concrete instruction to avoid deep investigation and the supporting quote make it highly retrievable and behaviorally significant.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 4.4s)
  - This entry captures a specific, actionable workflow preference with a direct quote that would change agent behavior during bug filing. The concrete instruction to avoid deep investigation and the supporting quote make it highly retrievable and behaviorally significant.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.85, necessity=0.70, 7.4s)
  - The entry provides a clear, actionable guideline with a representative user quote, but the phrasing could be tightened for precision. It is worth retaining after refinement.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 10.5s)
  - The entry includes a precise user quote and a clear directive about bug-filing depth, making it highly specific and actionable. Removing it would change whether the agent performs deep root-cause analysis when drafting bugs, and there is no obvious duplicate or system-prompt overlap.

### `777f85f2c2a6580f`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.68

**Original entry:**

> Framework distinction: **skills are primitives** (single-invocation, single deliverable, no session state), **agents are sessions** (multi-round, collaborative, durable state across turns). Council-of-elders is a primitive so should stay a skill. 
> 
> ## Documentation and writing style
> 
> For RFC and design docs: wants concise text, avoids "puff language," not looking for word count. Prefers "broad strokes" to iterate on rather than deep detail up front.

**Justification:** Entry contains specific architectural distinctions (skills vs agents, council-of-elders classification) and concrete documentation preferences (concise text, no puff language, broad strokes). These are actionable guidance that would affect design decisions and writing style, not generic preferences.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 6.1s)
  - Entry contains specific architectural distinctions (skills vs agents, council-of-elders classification) and concrete documentation preferences (concise text, no puff language, broad strokes). These are actionable guidance that would affect design decisions and writing style, not generic preferences.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.60, 5.7s)
  - Clear conceptual distinction but could be expressed more concisely and without markup.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.60, 20.6s)
  - Contains two specific, actionable signals—an architectural distinction with named entity 'Council-of-elders' and distinctive writing-style preferences ('puff language,' 'broad strokes')—that would measurably change agent output if removed.

### `8936920730d38570`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.75

**Original entry:**

> Uses dotfiles across multiple platforms (macOS, Ubuntu, Debian, Arch, CentOS). Cannot rely on consistent package managers like homebrew. Prefers cross-platform solutions using shell scripts and git clone over package-manager-specific approaches.

**Justification:** This entry contains specific, actionable constraints (multiple named platforms, explicit preference for shell scripts and git clone over package managers) that would directly influence tool recommendations and implementation approaches. The cross-platform requirement and package manager limitation are concrete facts that would change agent behavior when suggesting dotfile management solutions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 4.1s)
  - This entry contains specific, actionable constraints (multiple named platforms, explicit preference for shell scripts and git clone over package managers) that would directly influence tool recommendations and implementation approaches. The cross-platform requirement and package manager limitation are concrete facts that would change agent behavior when suggesting dotfile management solutions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.60, 6.9s)
  - The entry gives useful cross‑platform advice but is vague and could be made more concrete.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 16.9s)
  - Captures specific cross-platform constraints and explicit toolchain preferences that would change concrete installation and setup recommendations across macOS, Ubuntu, Debian, Arch, and CentOS.

### `aa59a8b701389ed4`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.75, necessity=0.65

**Original entry:**

> Has extensive experience writing OpenAPI parsers/utils. Previously worked at Gretel where he used OpenAPI Generator and had to hack internals to get good bindings. This background informs his skepticism about off-the-shelf OpenAPI generators.

**Justification:** Entry contains specific, verifiable information about the user's professional experience (worked at Gretel, used OpenAPI Generator, hacked internals) that directly explains their technical perspective and skepticism. This context could influence how an agent frames recommendations about OpenAPI tooling or interprets the user's technical opinions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 4.8s)
  - Entry contains specific, verifiable information about the user's professional experience (worked at Gretel, used OpenAPI Generator, hacked internals) that directly explains their technical perspective and skepticism. This context could influence how an agent frames recommendations about OpenAPI tooling or interprets the user's technical opinions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.50, 5.7s)
  - The entry provides useful background but could be clearer and more specific.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 9.0s)
  - Specific, verifiable professional background at Gretel with concrete technical detail (hacking OpenAPI Generator internals) that directly shapes tooling recommendations and avoids generic suggestions.

### `afee580c9feb00bf`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.72, necessity=0.70

**Original entry:**

> When writing docstrings and comments, avoid leaking development details: no references to "earlier code", "existing implementations", "coverage gaps", meta-commentary on test suite state, or vestigial wording from removed features. Documentation should describe current behavior cleanly, not expose how it evolved. User will ask to "audit docstrings for leakage" and expects patterns like "the existing X tests" or "closes a coverage gap" to be removed.

**Justification:** This entry captures a specific, actionable user preference with concrete examples of patterns to avoid ('earlier code', 'existing implementations', 'coverage gaps', 'closes a coverage gap') and includes a retrieval trigger phrase ('audit docstrings for leakage'). It describes behavior that would not be obvious from general engineering principles and would likely change the agent's concrete editing decisions when reviewing documentation.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 5.1s)
  - This entry captures a specific, actionable user preference with concrete examples of patterns to avoid ('earlier code', 'existing implementations', 'coverage gaps', 'closes a coverage gap') and includes a retrieval trigger phrase ('audit docstrings for leakage'). It describes behavior that would not be obvious from general engineering principles and would likely change the agent's concrete editing decisions when reviewing documentation.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.50, 5.1s)
  - Provides useful guidance on avoiding docstring leakage but is somewhat generic; a clearer formulation will improve compliance.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.75, 13.3s)
  - Captures a specific user workflow with a concrete trigger phrase ('audit docstrings for leakage') and precise examples of prohibited patterns ('closes a coverage gap', 'existing X tests'), making it highly actionable and retrievable.

### `b6d1a2581c4fd3b3`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.75, necessity=0.68

**Original entry:**

> For NVIDIA/OpenShell issues/PRs, user prefers casual, conversational, first-person tone over formal third-person language. Example: "I'm thinking we just add the command" rather than "Adding the command is the better fix." Avoid referring to "maintainers" in third person since the user is part of that group — use inclusive language like "we" or direct proposals. Prefers tight, conversational prose over verbose academic/formal writing. User replaced a 4-paragraph feature-request body with ~3 sentences in first-person. Avoid walls of text in issue/PR drafts — show the minimal viable version first.

**Justification:** Highly specific guidance for NVIDIA/OpenShell context with concrete examples of preferred tone ('I'm thinking we just add' vs 'Adding the command is the better fix'), actionable rules (avoid 'maintainers' in third person, use 'we'), and verifiable behavioral change (replacing 4-paragraph text with ~3 sentences). This would meaningfully alter agent output in this specific repository context.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 4.8s)
  - Highly specific guidance for NVIDIA/OpenShell context with concrete examples of preferred tone ('I'm thinking we just add' vs 'Adding the command is the better fix'), actionable rules (avoid 'maintainers' in third person, use 'we'), and verifiable behavioral change (replacing 4-paragraph text with ~3 sentences). This would meaningfully alter agent output in this specific repository context.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 9.5s)
  - The entry offers useful style guidance but is wordy and could be clarified.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.80, 11.2s)
  - Contains named repository context, precise preferred/dispreferred language examples, and concrete drafting behavior; removing it would cause the agent to revert to a more formal, verbose default style for issues/PRs.

### `bb0d40fa9755379b`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.72, necessity=0.92

**Original entry:**

> When asked to investigate refactoring opportunities (fixtures/parameterization), user wants thoughtful analysis with clear recommendations of what to apply vs skip, not automatic application. Prefers to understand trade-offs ("merging would be more bytes, not fewer") before proceeding. 
> 
> ## Tools and workflows — Linear
> 
> Works in Linear desktop app. Rewrite URLs from `https://linear.app/...` to `linear://...` in all outputs (chat, commits, PR/issue bodies, dev journals, and links returned by Linear MCP tools). `linear://` opens directly in desktop app; `https://` forces a browser detour. 
> 
> ## Tools and workflows — git
> 
> Prefers clean git workflow with feature branches even when personally "play fast and loose on main" — explicitly requested dev branch instead of committing to main for SDK work.

**Justification:** Specific user preferences about analysis, URL rewriting, and git workflow that affect agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.85, 10.8s)
  - The entry contains specific, actionable preferences (Linear URL rewriting, git workflow) and a concrete quote demonstrating analytical preference. However, it combines three distinct topics under unclear headings that should be separated for better retrievability.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=1.00, 8.2s)
  - Specific user preferences about analysis, URL rewriting, and git workflow that affect agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 22.4s)
  - Entry contains three distinct, high-signal preferences with named tools, specific URL protocols, and exact quotes that would change concrete agent decisions if removed.

### `bd67f4f43e9c9694`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.68, necessity=0.63

**Original entry:**

> Identity-shaped prompts ("you are a deliberate collaborator who...") belong at the very top of CLAUDE.md/AGENTS.md, not buried in bullet lists. They set the lens through which all other rules are read. Placement matters: framing at the top establishes character; the same content as rule #7 just gets weighted alongside everything else.

**Justification:** Entry provides specific, actionable guidance about document structure: identity-shaped prompts belong at the top of CLAUDE.md/AGENTS.md, not in bullet lists. This is concrete enough to guide document organization decisions and explains the 'why' (framing vs. rule-weighting), making it retrievable and behaviorally relevant for agent configuration work.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.70, 4.4s)
  - Entry provides specific, actionable guidance about document structure: identity-shaped prompts belong at the top of CLAUDE.md/AGENTS.md, not in bullet lists. This is concrete enough to guide document organization decisions and explains the 'why' (framing vs. rule-weighting), making it retrievable and behaviorally relevant for agent configuration work.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.7s)
  - The entry offers useful guidance on positioning identity‑shaped prompts but lacks precise wording and could be clarified.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 13.1s)
  - Entry gives specific structural guidance tied to named files (CLAUDE.md/AGENTS.md) with a clear rationale for top-of-file placement of identity prompts. Its removal would change concrete formatting decisions when the agent authors or edits these documents.

### `c39e32157fe70312`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.92, necessity=0.65

**Original entry:**

> Assigns Tyler Bray (GitHub: tylersbray, email: tbray@nvidia.com) as reviewer for CLI and agent-related work on NeMo Platform.

**Justification:** Highly specific entry with concrete named entities (Tyler Bray), verifiable contact information (GitHub handle, email), and clear scope (CLI and agent-related work on NeMo Platform). This would directly influence reviewer assignment decisions and is appropriately narrow for retrieval-based memory rather than system prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.85, 4.5s)
  - Highly specific entry with concrete named entities (Tyler Bray), verifiable contact information (GitHub handle, email), and clear scope (CLI and agent-related work on NeMo Platform). This would directly influence reviewer assignment decisions and is appropriately narrow for retrieval-based memory rather than system prompt.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.90, necessity=0.20, 11.5s)
  - The entry is specific but could be clearer about the scope of the reviewer role and platform version.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 13.1s)
  - The entry contains concrete named entities, a GitHub handle, email, and precise scope (CLI and agent-related work on NeMo Platform), making it highly retrievable and directly actionable for reviewer-assignment decisions.

### `c793c6c82dacdb5e`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.95, necessity=0.72

**Original entry:**

> Uses marker file pattern for machine-specific config: `touch ~/.config/zsh/.work` on work machines, then conditionally source work config with `[[ -f $ZDOTDIR/.work ]] && source ...`. Prefers this over hostname matching or untracked machine-local files because it's explicit and visible in the repo flow.

**Justification:** Highly specific technical detail with concrete commands, file paths, and a clear pattern preference. This describes a non-obvious configuration choice that would directly influence how the agent helps configure shell environments for multi-machine setups.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.85, 4.0s)
  - Highly specific technical detail with concrete commands, file paths, and a clear pattern preference. This describes a non-obvious configuration choice that would directly influence how the agent helps configure shell environments for multi-machine setups.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=1.00, necessity=0.50, 8.8s)
  - The entry gives a concrete, retrievable technique but could be clearer and more explicit about the preferred pattern.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.80, 11.3s)
  - Contains exact commands, paths, and rationale for a specific dotfiles workflow; losing it would lead the agent to suggest hostname matching or other alternatives instead.

### `cc2763c3925d2b64`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.80, necessity=0.53

**Original entry:**

> Max Dubrinsky (GitHub: maxdubrinsky) is a maintainer of NVIDIA/OpenShell. Has personal connections to NVIDIA/OpenShell maintainers but contributes via fork (not direct push access).

**Justification:** Entry contains specific, verifiable facts (named person, GitHub handle, specific repository, contribution model) that would meaningfully inform interactions about NVIDIA/OpenShell project structure and contribution workflows. The corroboration across 2 sessions suggests this is reliable information worth preserving.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.70, 4.2s)
  - Entry contains specific, verifiable facts (named person, GitHub handle, specific repository, contribution model) that would meaningfully inform interactions about NVIDIA/OpenShell project structure and contribution workflows. The corroboration across 2 sessions suggests this is reliable information worth preserving.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.80, necessity=0.30, 7.7s)
  - The entry is fairly specific but could be phrased more clearly to improve retrievability and precision.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.60, 144.2s)
  - Specific named entities, GitHub handle, and repository access details with multi-session corroboration; knowing he lacks direct push access prevents incorrect workflow assumptions.

### `da5498e4affca2a0`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.72, necessity=0.78

**Original entry:**

> Expects verification of claims before making breaking changes. Will ask "can you make sure of that" and wants downstream impact checked (e.g., grepping for field usage before removing from public schema). 
> 
> ## Technical preferences — architecture and design
> 
> Data model evolution: prefer to omit fields until there's a concrete consumer. "Easier to add a field than remove one." Keep surface area small in initial implementations rather than pre-emptively adding fields that might be useful later.

**Justification:** The entry gives a specific, actionable guideline for verifying claims and managing schema changes, which is not redundant.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.65, necessity=0.75, 6.4s)
  - The entry captures concrete behavioral preferences (verification before breaking changes, omitting fields until needed) with a specific quote and example action (grepping for usage). However, the structure mixes two related but distinct concepts that would be clearer if separated and more precisely stated.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.90, 6.1s)
  - The entry gives a specific, actionable guideline for verifying claims and managing schema changes, which is not redundant.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 14.2s)
  - Contains specific behavioral quotes and concrete examples (e.g., grepping for field usage) that would steer schema design and breaking-change recommendations; worth keeping as a retrievable preference.

### `e85750de7b7fc4fa`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.67

**Original entry:**

> Prefers canonical specifications to live in language-agnostic artifacts (reviewer prompts, synthesis templates, shell scripts) with each runtime (Claude Code, deepagents-cli) wrapping them with runtime-specific dispatch glue. Reason: keeps substance in one place and isolates runtime quirks, avoiding drift when maintaining parallel implementations in different systems.

**Justification:** This entry captures a specific architectural pattern with concrete examples (reviewer prompts, synthesis templates, shell scripts) and named runtimes (Claude Code, deepagents-cli). It would directly influence decisions about where to place specifications and how to structure multi-runtime systems, making it actionable and necessary.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 3.2s)
  - This entry captures a specific architectural pattern with concrete examples (reviewer prompts, synthesis templates, shell scripts) and named runtimes (Claude Code, deepagents-cli). It would directly influence decisions about where to place specifications and how to structure multi-runtime systems, making it actionable and necessary.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 1.4s)
  - Provides useful architectural guidance but is ambiguous and could affect several implementations, so we need clarification.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.65, 10.9s)
  - It names specific runtimes (Claude Code, deepagents-cli) and artifact types, capturing a concrete architectural preference with rationale that would steer how the agent organizes specifications across multiple systems.

### `eb06022f0c6cec7a`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.57

**Original entry:**

> When blocked on unmerged dependencies (PRs, branches), prefers to check out the branch in a worktree and start iterating rather than waiting. Wants action over planning delays.

**Justification:** This entry captures a specific behavioral preference about handling blocked work - using worktrees to work on unmerged dependencies rather than waiting. It's actionable and would influence concrete decisions about workflow when encountering blocked PRs/branches. The mention of 'worktree' as the specific solution makes it retrievable and verifiable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.75, 5.8s)
  - This entry captures a specific behavioral preference about handling blocked work - using worktrees to work on unmerged dependencies rather than waiting. It's actionable and would influence concrete decisions about workflow when encountering blocked PRs/branches. The mention of 'worktree' as the specific solution makes it retrievable and verifiable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.55, necessity=0.35, 6.0s)
  - Specific enough for retrieval but can be phrased more succinctly for broader use.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.60, 37.6s)
  - Captures a specific workflow preference for using git worktrees when blocked on dependencies, which would change the agent's concrete recommendation rather than defaulting to waiting, though it lacks specific commands or project context.

### `f06b7cf3228f3384`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.60

**Original entry:**

> When evaluating architectural decisions or migration costs, prefers concrete data: LOC counts, file counts, time estimates broken down by work area. Wants "how many can we delete?" answered with measurements, not speculation.

**Justification:** This entry captures a specific, actionable preference for data-driven decision-making with concrete examples (LOC counts, file counts, time estimates). It's retrievable when architectural or migration discussions arise and would meaningfully change agent behavior by prompting quantitative analysis rather than qualitative speculation.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.80, 4.3s)
  - This entry captures a specific, actionable preference for data-driven decision-making with concrete examples (LOC counts, file counts, time estimates). It's retrievable when architectural or migration discussions arise and would meaningfully change agent behavior by prompting quantitative analysis rather than qualitative speculation.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.30, 6.5s)
  - The guidance is useful but somewhat vague and not uniquely retrievable. It can be sharpened to be more actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.70, 13.4s)
  - Captures a distinct, domain-specific preference for quantitative metrics in architectural and migration discussions with concrete examples, making it actionable and retrievable.

### `f4a359b3859edf3d`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.85, necessity=0.80

**Original entry:**

> Prefers Python-style pseudocode over LaTeX/mathematical notation for expressing formulas and algorithms. "Prefer python to math since it's been 15 years since I've used LaTeX."

**Justification:** This entry contains a specific, actionable preference with concrete context (Python vs LaTeX, 15-year gap in LaTeX usage) and a direct quote. It would materially change how the agent presents technical content—choosing Python code examples over mathematical notation—which directly impacts user comprehension and satisfaction.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 4.8s)
  - This entry contains a specific, actionable preference with concrete context (Python vs LaTeX, 15-year gap in LaTeX usage) and a direct quote. It would materially change how the agent presents technical content—choosing Python code examples over mathematical notation—which directly impacts user comprehension and satisfaction.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.80, necessity=0.60, 4.9s)
  - Clear preference for Python pseudocode over LaTeX, specific to output style and would affect agent behavior if removed.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 15.2s)
  - Contains a concrete, actionable presentation preference backed by a direct quote; removing it would likely cause the agent to default to LaTeX/mathematical notation when explaining algorithms or formulas.

### `fe3b38f60055f95f`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.85, necessity=0.83

**Original entry:**

> When reviewing PRs, user wants to distinguish between issues caused by the PR (net-new) vs issues that were pre-existing on main. Asked explicitly: "Are there any issues created by this PR or are these problems present on the current implementation?"

**Justification:** This entry captures a specific, actionable preference for PR review methodology with an exact quote demonstrating the user's concern. It will materially affect how the agent structures PR analysis by ensuring it explicitly distinguishes new issues from pre-existing ones, rather than presenting all findings without context.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 4.3s)
  - This entry captures a specific, actionable preference for PR review methodology with an exact quote demonstrating the user's concern. It will materially affect how the agent structures PR analysis by ensuring it explicitly distinguishes new issues from pre-existing ones, rather than presenting all findings without context.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.90, necessity=0.90, 8.0s)
  - The entry captures a precise user instruction for distinguishing net‑new from pre‑existing issues in PR reviews, making it both specific and valuable enough to be part of the system prompt. Removing it would cause the agent to miss this explicit line of questioning.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.80, 16.8s)
  - Contains a direct, verifiable quote and describes a concrete workflow preference for PR reviews that would change how the agent categorizes and reports issues.

### `ffebf77904896ae7`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.70

**Original entry:**

> Works with NVIDIA projects (NeMo, Studio, Omnipush, etc.) and tests cmux integration. Has access to NVIDIA Omnistations. Working on NeMo Platform agentic-use benchmarking. Has access to NVIDIA NGC/inference API keys.

**Justification:** Entry contains specific named entities (NVIDIA NeMo, Studio, Omnipush, cmux, Omnistations, NGC, NeMo Platform) and concrete access credentials that would change agent behavior when discussing NVIDIA-related work or available resources. The specificity of projects and infrastructure access makes this highly retrievable and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 5.4s)
  - Entry contains specific named entities (NVIDIA NeMo, Studio, Omnipush, cmux, Omnistations, NGC, NeMo Platform) and concrete access credentials that would change agent behavior when discussing NVIDIA-related work or available resources. The specificity of projects and infrastructure access makes this highly retrievable and actionable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.50, 7.1s)
  - The entry mentions several concrete NVIDIA projects and resources but is slightly vague on specifics.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.70, 10.9s)
  - Entry contains specific named entities (NeMo, cmux, NGC, Studio) and concrete access details that directly shape technical suggestions, making it retrievable and behavior-changing.

### `07b56fbdcc233913`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.63, necessity=0.67

**Original entry:**

> Prefers distilled, compact memories over verbose ones. When memories accumulate specific implementation details (file paths, class names, line numbers), wants them trimmed to essential decisions/principles and pointers to canonical sources. Asks for memory cleanup proactively to reduce context load.

**Justification:** Captures a specific meta-preference about memory compaction and proactive cleanup that would concretely change how the agent records and maintains memories, though it lacks a verbatim example or named entity.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 5.9s)
  - This entry describes a clear, actionable preference about memory management style that should inform all agent interactions. It's specific enough to guide behavior (trim implementation details, keep principles, reduce context load) and applies broadly enough that it belongs in the system prompt rather than being retrieved situationally.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.50, 4.8s)
  - The entry captures a useful heuristic but is phrased loosely and lacks concrete triggers.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 14.8s)
  - Captures a specific meta-preference about memory compaction and proactive cleanup that would concretely change how the agent records and maintains memories, though it lacks a verbatim example or named entity.

### `2c52e8806ac9ede6`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.70, necessity=0.77

**Original entry:**

> ## Collaboration style
> 
> Keeps user in the development loop — "Be vocal if you are missing information or could use another set of eyes from me." Wants gaps and uncertainties surfaced explicitly rather than having the agent make assumptions. When uncertain, do less not more — pause before spawning ceremony. Values being asked questions when the path is unclear.

**Justification:** Highly corroborated across 8 sessions with specific behavioral guidance and a direct quote; removing it would change concrete decisions about when to pause, ask questions, or spawn ceremony.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.90, 4.4s)
  - This entry captures specific, actionable behavioral guidance with high corroboration (8 sessions). It defines concrete interaction patterns: surface gaps explicitly, ask questions when unclear, do less when uncertain, and avoid assumptions. The high session count and behavioral specificity suggest this is a core interaction principle that should apply universally rather than being retrieved contextually.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 3.5s)
  - Provides useful guidance but is vague and could be clearer.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 8.0s)
  - Highly corroborated across 8 sessions with specific behavioral guidance and a direct quote; removing it would change concrete decisions about when to pause, ask questions, or spawn ceremony.

### `81d7a0d390ee897d`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.73, necessity=0.73

**Original entry:**

> Uses @filename syntax to reference files (e.g., "@RFC-migrate-off-stainless.md"). When user mentions a document by name or reference, ask for location/path rather than searching blindly.

**Justification:** Concrete user-specific workflow pattern with a precise example; removing it risks the agent searching blindly instead of requesting a path for @-referenced documents.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.60, 5.2s)
  - The entry captures a specific user preference (@filename syntax) and a useful behavioral guidance (ask for path rather than searching), but combines two distinct concepts that could be clearer and more actionable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.70, necessity=0.90, 6.2s)
  - Clear, specific instruction that would change agent behavior and is broadly applicable, so it should be part of the system prompt.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 11.6s)
  - Concrete user-specific workflow pattern with a precise example; removing it risks the agent searching blindly instead of requesting a path for @-referenced documents.

### `9cd72c55fda5ded2`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.53, necessity=0.67

**Original entry:**

> Prefers deliberate investigation over trial-and-error. When introducing a new tool, wants agent to "brush up" on how to use it before firing off commands. Values understanding complexity/scope before implementing. Slow at architectural boundaries; iteration speed never substitutes for thinking.

**Justification:** Well-corroborated (4 sessions) behavioral preference that directly opposes default rapid-iteration patterns and would change concrete decisions about researching tools before use and pacing at architectural boundaries. Lacks named entities but contains retrievable, distinctive phrasing.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.60, necessity=0.80, 4.2s)
  - This entry captures a consistent, actionable working preference observed across 4 sessions: deliberate investigation and understanding before implementation. While not citing specific tools or commands, it describes a meta-approach to problem-solving that should shape all agent behavior. It's better suited as permanent system-prompt guidance than as a retrieved fact.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 4.2s)
  - The guidance is useful but too general; it can be made clearer and more actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.70, 17.1s)
  - Well-corroborated (4 sessions) behavioral preference that directly opposes default rapid-iteration patterns and would change concrete decisions about researching tools before use and pacing at architectural boundaries. Lacks named entities but contains retrievable, distinctive phrasing.

### `ccd19a2fa2414c49`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.47, necessity=0.30

**Original entry:**

> Values consistency across the codebase — when fixing bugs or implementing features, prefers to match broader codebase patterns rather than keeping one-off exceptions ("do whatever is most consistent").

**Justification:** Contains a verifiable user quote and a concrete decision heuristic that steers bug fixes and feature work toward global codebase consistency rather than minimal local diffs.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `drop` (quality=0.30, necessity=0.10, 4.4s)
  - This entry describes a general software engineering best practice (consistency over one-off exceptions) that any competent engineer would follow by default. It lacks specificity about what patterns, which codebase contexts, or concrete examples where this preference matters, and would not meaningfully change agent behavior if removed.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.20, 4.3s)
  - The guidance is vague and not specific enough for reliable retrieval, but it conveys a useful principle that could be clarified.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.60, 137.9s)
  - Contains a verifiable user quote and a concrete decision heuristic that steers bug fixes and feature work toward global codebase consistency rather than minimal local diffs.

### `d78b6a695264b8f4`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.78, necessity=0.83

**Original entry:**

> Prefers dropping features entirely when their value proposition weakens rather than maintaining stopgap solutions or adding CLI complexity to preserve them. Applies "re-evaluate dependent features" principle consistently. Example: removed `--model` flag from usage CLI because richer artifact data (trajectory.json) will eventually provide authoritative model identity, avoiding two-sources-of-truth problems.

**Justification:** Corroborated preference backed by a concrete CLI example (`--model` flag, trajectory.json) that directly shapes whether the agent recommends dropping features or maintaining stopgaps.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.80, 4.7s)
  - The entry captures a specific, verifiable design principle with a concrete example (--model flag removal), but the phrasing is somewhat verbose and could be tightened for better retrieval. The principle is actionable and would influence future feature decisions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 7.2s)
  - The entry provides a concrete, actionable principle with a specific example, making it both specific enough for retrieval and influential on the agent's decisions, thus warranting promotion to the system prompt.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 14.8s)
  - Corroborated preference backed by a concrete CLI example (`--model` flag, trajectory.json) that directly shapes whether the agent recommends dropping features or maintaining stopgaps.

### `daa44d66c1c0e810`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.63, necessity=0.73

**Original entry:**

> When user explicitly asks for a specific tool or approach (e.g., "use tmux" not just "parallel subagents"), follow it literally — there's always a reason. Don't substitute with "equivalent" alternatives without asking first.

**Justification:** Actionable behavioral rule with specific examples (tmux, parallel subagents) that directly shapes tool-selection decisions and is unlikely to be duplicated in the base system prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.60, necessity=0.80, 5.9s)
  - This captures an important behavioral principle about respecting explicit user requests for specific tools rather than substituting alternatives. While it uses an example (tmux) rather than being a concrete fact, the underlying principle is broadly applicable and should influence all agent interactions, making it better suited for the system prompt than episodic retrieval.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.50, necessity=0.50, 9.7s)
  - The rule is useful but phrased vaguely; refining will make it clearer and more actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.90, 10.4s)
  - Actionable behavioral rule with specific examples (tmux, parallel subagents) that directly shapes tool-selection decisions and is unlikely to be duplicated in the base system prompt.
