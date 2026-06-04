# Memory triage proposals — `pi-hermes:CONSOLIDATED:user`

## Run

- **council:** `azure-anthropic-claude-sonnet-4-6`, `nvidia-nemotron-3-nano-30b-a3b`, `nvidia-llama-3-3-nemotron-super-49b-v1-5`
- **started:** 2026-06-03T22:05:13.095762+00:00
- **finished:** 2026-06-03T22:51:52.049935+00:00
- **elapsed:** 2799.0s
- **proposals:** 71
- **errors:** 0
- **skipped entries:** 0

## Summary

| verdict | count | % of proposals |
| --- | ---: | ---: |
| `drop` | 1 | 1.4% |
| `merge` | 0 | 0.0% |
| `refine` | 2 | 2.8% |
| `promote_to_prompt` | 4 | 5.6% |
| `keep` | 64 | 90.1% |

## `drop` (1)

### `7350bebdc6f86fbf`

- **verdict:** `drop` (confidence 0.67)
- **scores:** quality=0.23, necessity=0.20

**Original entry:**

> Proponent of good module separation in code organization, even when it differs from existing patterns in the codebase.

**Justification:** This is a vague, single-observation entry that could apply to almost any thoughtful engineer; 'good module separation' is not specific enough to be retrievable or to change agent behavior in a concrete way. Without corroboration or a specific example (e.g., a named project where this preference manifested), it adds no actionable signal.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `drop` (quality=0.20, necessity=0.10, 3.9s)
  - This is a vague, single-observation entry that could apply to almost any thoughtful engineer; 'good module separation' is not specific enough to be retrievable or to change agent behavior in a concrete way. Without corroboration or a specific example (e.g., a named project where this preference manifested), it adds no actionable signal.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.0s)
  - The entry offers a general but useful guideline on module separation that is not tied to specific facts or decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `drop` (quality=0.00, necessity=0.00, 29.3s)
  - The entry is overly vague and states a generic principle that would apply to any thoughtful engineer rather than providing specific, verifiable information. It lacks concrete examples, named entities, or precise guidance, making it indistinguishable from general knowledge already implied in the agent's training.

## `refine` (2)

### `bb0d40fa9755379b`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.90, necessity=0.98

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

**Justification:** The entry combines three distinct topics (refactoring analysis preferences, Linear URL rewriting, git branching workflow) that should be separate entries for reliable retrieval—each topic is unrelated to the others and would be retrieved in different contexts.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.80, necessity=0.95, 2.8s)
  - The entry combines three distinct topics (refactoring analysis preferences, Linear URL rewriting, git branching workflow) that should be separate entries for reliable retrieval—each topic is unrelated to the others and would be retrieved in different contexts.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=1.00, 6.1s)
  - Provides specific, retrievable user preferences for Linear URL rewriting and Git branching that influence concrete agent decisions, making removal impactful.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `refine` (quality=1.00, necessity=1.00, 114.4s)
  - The entry combines two distinct topics (user preferences for refactoring analysis and tool-specific workflow details) that should be separated into independent entries for clarity and targeted retrieval. The defect is 'combining multiple distinct topics'.

### `e626e4bbb2861be3`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.87

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

**Justification:** The entry combines three distinct topics (shell startup performance preferences, beads memory tool usage, and tmux team session preferences) into one entry, violating single-topic principle and making retrieval ambiguous. Each topic should be its own entry.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.90, 3.2s)
  - The entry combines three distinct topics (shell startup performance preferences, beads memory tool usage, and tmux team session preferences) into one entry, violating single-topic principle and making retrieval ambiguous. Each topic should be its own entry.
- `nvidia-nemotron-3-nano-30b-a3b` -> `refine` (quality=0.60, necessity=0.70, 11.8s)
  - The entry bundles multiple distinct guidance points into one overly long memo, exceeding the needed length and obscuring separate topics.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 23.4s)
  - The entry provides specific preferences with named tools (beads, tmux), concrete commands ('bd remember', 'bd prime'), and observable optimizations (async prompts) that directly influence agent behavior. Removal would prevent the agent from implementing these specific workflows.

## `promote_to_prompt` (4)

### `07b56fbdcc233913`

- **verdict:** `promote_to_prompt` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.62

**Original entry:**

> Prefers distilled, compact memories over verbose ones. When memories accumulate specific implementation details (file paths, class names, line numbers), wants them trimmed to essential decisions/principles and pointers to canonical sources. Asks for memory cleanup proactively to reduce context load.

**Justification:** This is a broad, persistent behavioral preference that applies to every interaction involving memory management—it should be always-on rather than retrieval-dependent. The guidance is specific enough (trim file paths/class names/line numbers to decisions/principles, proactively suggest cleanup) to materially change agent behavior if absent.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 3.9s)
  - This is a broad, persistent behavioral preference that applies to every interaction involving memory management—it should be always-on rather than retrieval-dependent. The guidance is specific enough (trim file paths/class names/line numbers to decisions/principles, proactively suggest cleanup) to materially change agent behavior if absent.
- `nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.60, necessity=0.50, 5.2s)
  - High-quality, broadly applicable guidance on memory condensation that would benefit the system prompt.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 14.3s)
  - The entry provides useful guidance on memory formatting preferences but lacks concrete examples, version references, or named entities that would elevate quality. While removal wouldn't alter critical decisions, it would reduce the agent's ability to proactively manage memory context as requested.

### `0f7fb9245ec9337d`

- **verdict:** `promote_to_prompt` (confidence 0.67)
- **scores:** quality=0.83, necessity=0.83

**Original entry:**

> Dislikes "techno-jargon" (e.g., "forcing function," "load-bearing") and em-dashes in written docs — these make text sound AI-generated. Wants their own voice to shine through in RFCs and technical writing.

**Justification:** This entry contains specific, actionable writing preferences with named examples ('forcing function,' 'load-bearing,' em-dashes) that directly affect every piece of technical writing the agent produces. It should be in the always-on system prompt so it applies without needing retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.90, necessity=1.00, 3.5s)
  - This entry contains specific, actionable writing preferences with named examples ('forcing function,' 'load-bearing,' em-dashes) that directly affect every piece of technical writing the agent produces. It should be in the always-on system prompt so it applies without needing retrieval.
- `nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.60, necessity=0.50, 3.6s)
  - The entry captures a clear stylistic preference with concrete examples, making it suitable for inclusion in the system prompt to guide voice consistency.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 153.3s)
  - The entry provides specific examples of disliked terms (e.g., 'forcing function,' 'load-bearing') and stylistic preferences (em-dashes, AI-generated text avoidance) that are concrete and verifiable. Removing this would directly impact the agent's ability to align with the user's writing style preferences in technical documents, altering behavior in RFC generation.

### `2d5005c7ea8c6a13`

- **verdict:** `promote_to_prompt` (confidence 0.67)
- **scores:** quality=0.78, necessity=0.82

**Original entry:**

> Values critical thinking and evidence-based pushback. "If there is anything said above that you take issue with, please push back. Think critically!" Expects substantive engagement over deference. When presenting architectural proposals or recommendations, wants validation with concrete evidence from codebase/docs and grounded reasoning. Will explicitly ask "push back on this read and verify this claim" before bringing ideas to coworkers.

**Justification:** This entry has strong corroboration (6 sessions), contains direct quotes, and describes a fundamental interaction style that should govern every response involving proposals or recommendations. Placing it in the always-on system prompt ensures the agent never defaults to deference without being explicitly reminded.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.95, 3.6s)
  - This entry has strong corroboration (6 sessions), contains direct quotes, and describes a fundamental interaction style that should govern every response involving proposals or recommendations. Placing it in the always-on system prompt ensures the agent never defaults to deference without being explicitly reminded.
- `nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.50, necessity=0.50, 5.9s)
  - General but important instruction that would improve behavior if embedded in the system prompt.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 59.0s)
  - The entry provides specific, verifiable guidance with direct quotes (e.g., 'push back on this read and verify this claim') and concrete expectations for evidence-based validation. Removal would directly alter decision-making processes for architectural proposals, affecting critical behavior.

### `3a4f5eb974a14f65`

- **verdict:** `promote_to_prompt` (confidence 0.67)
- **scores:** quality=0.85, necessity=0.93

**Original entry:**

> Challenges assumptions and expects evidence-based verification. When told something about code or workflow (e.g., "the rebase didn't change anything"), user will question it ("That cannot be right") and expects concrete proof (git range-diff, patch-ids, byte-level diffs) rather than accepting claims at face value. Provide verifiable evidence, not assertions.

**Justification:** This entry captures a fundamental, consistent behavioral trait—demanding verifiable evidence (git range-diff, patch-ids, byte-level diffs) rather than accepting assertions—that should inform every technical interaction, not just ones retrieved contextually. It's specific enough (named tools/methods) and high-impact enough to belong in the always-on system prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.90, 4.9s)
  - This entry captures a fundamental, consistent behavioral trait—demanding verifiable evidence (git range-diff, patch-ids, byte-level diffs) rather than accepting assertions—that should inform every technical interaction, not just ones retrieved contextually. It's specific enough (named tools/methods) and high-impact enough to belong in the always-on system prompt.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.90, 5.5s)
  - Specific guidance on demanding evidence-based verification; removing it would affect the agent's tendency to challenge unsupported claims.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `promote_to_prompt` (quality=1.00, necessity=1.00, 58.8s)
  - The entry provides concrete, specific commands (git range-diff, patch-ids, byte-level diffs) that are directly actionable and verifiable. Removing it would force the agent to rely on lower-quality evidence requests, altering its decision-making process in technical verifications.

## `keep` (64)

### `09d03f0713454d63`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.95, necessity=0.57

**Original entry:**

> Dislikes overly clinical/medical language in documentation headings — rejected "Anatomy of an Agent" in favor of "Agent Definition" when drafting public docs for the NeMo Platform agents page.

**Justification:** This entry is specific and actionable, with a concrete example (rejected 'Anatomy of an Agent' in favor of 'Agent Definition') tied to a named context (NeMo Platform agents page). It would meaningfully guide future documentation heading choices for this user.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.85, necessity=0.70, 3.7s)
  - This entry is specific and actionable, with a concrete example (rejected 'Anatomy of an Agent' in favor of 'Agent Definition') tied to a named context (NeMo Platform agents page). It would meaningfully guide future documentation heading choices for this user.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=0.50, 3.8s)
  - Specific, verifiable preference about heading wording; not broad enough for system prompt.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 18.8s)
  - The entry provides a specific example with named entities (NeMo Platform, 'Anatomy of an Agent' vs 'Agent Definition'), meeting quality criteria. Necessity is 0.5 because removal would alter tone/wording preferences but not directly change a critical decision, as this is a single-session observation without demonstrated corroboration.

### `1f841c1e54060e46`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.63

**Original entry:**

> When filing GitHub issues, user prefers to "leave the labeling for someone else" — apply only obviously correct labels, leave discretionary labels to human reviewers.

**Justification:** This is a specific, actionable preference with a direct quote that would concretely change agent behavior when filing GitHub issues — without it, the agent might over-label. Quality is slightly below 1.0 because 'obviously correct' vs 'discretionary' is somewhat judgment-dependent, but the quote anchors it well.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 5.7s)
  - This is a specific, actionable preference with a direct quote that would concretely change agent behavior when filing GitHub issues — without it, the agent might over-label. Quality is slightly below 1.0 because 'obviously correct' vs 'discretionary' is somewhat judgment-dependent, but the quote anchors it well.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.60, 7.3s)
  - Specific labeling guidance with a clear quote; no structural defect requiring refinement.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 20.0s)
  - The entry provides useful general guidance on user preferences for labeling in GitHub issues. It is not specific enough to rate higher than 0.5 for quality as it lacks named entities, exact quotes, or version numbers. Necessity is 0.5 because removing it might alter the agent's labeling behavior slightly but does not represent a critical, high-impact decision point.

### `24883461872a7245`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.57, necessity=0.57

**Original entry:**

> Prefers explicit credential mapping between services. Does not want automatic substitution of credentials meant for one API provider as fallback credentials for a different provider, even when upstream code has such fallback chains.

**Justification:** This captures a specific, non-obvious preference about credential isolation that would directly change agent behavior when configuring multi-provider API setups—without this entry, the agent might silently allow fallback credential chains that the user explicitly rejects. The guidance is concrete enough to be actionable even without named entities.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.90, 3.9s)
  - This captures a specific, non-obvious preference about credential isolation that would directly change agent behavior when configuring multi-provider API setups—without this entry, the agent might silently allow fallback credential chains that the user explicitly rejects. The guidance is concrete enough to be actionable even without named entities.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.30, 4.4s)
  - The entry expresses a specific design preference about credential mapping that is not broad enough for a system prompt and has no clear defect requiring refinement.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 23.2s)
  - The entry captures a specific user preference regarding credential management, which is useful but lacks named entities or concrete examples for higher quality. Its removal might affect the agent's approach to credential handling, but it doesn't alter a concrete decision explicitly tied to system behavior.

### `2b3f32758b063f73`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.70

**Original entry:**

> When reviewing council/multi-reviewer feedback, user wants balanced reasoning that doesn't overweight obvious mechanical fixes (e.g., "vendoring would of course have been fixed"). Focus on substantive issues that require judgment.

**Justification:** The entry captures a specific preference about council/multi-reviewer feedback analysis with a concrete illustrative example ('vendoring would of course have been fixed'), making it retrievable in the right context. It would meaningfully shape agent behavior when summarizing multi-reviewer feedback, steering away from over-weighting mechanical/obvious fixes.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 3.3s)
  - The entry captures a specific preference about council/multi-reviewer feedback analysis with a concrete illustrative example ('vendoring would of course have been fixed'), making it retrievable in the right context. It would meaningfully shape agent behavior when summarizing multi-reviewer feedback, steering away from over-weighting mechanical/obvious fixes.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.4s)
  - General guidance on balancing feedback; removing it would affect tone but not a concrete decision.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 21.4s)
  - The entry provides concrete, verifiable guidance with a specific example ('vendoring would of course have been fixed') that directly addresses agent behavior in feedback review. Removal would weaken the agent's ability to prioritize substantive judgment over mechanical fixes.

### `2b7aab650de6b343`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.87

**Original entry:**

> Finds hour markers in progress indicators "demoralizing" and prefers MM:SS format over H:MM:SS for elapsed time displays, even when duration exceeds 60 minutes (shows 73:21 instead of 1:13:21).

**Justification:** Highly specific preference with a concrete example (73:21 vs 1:13:21) and a direct quote ('demoralizing'); would meaningfully change how the agent formats elapsed time displays. Single-session corroboration is a minor concern but the specificity is strong enough to retain.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.85, necessity=0.90, 5.5s)
  - Highly specific preference with a concrete example (73:21 vs 1:13:21) and a direct quote ('demoralizing'); would meaningfully change how the agent formats elapsed time displays. Single-session corroboration is a minor concern but the specificity is strong enough to retain.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.85, necessity=0.70, 8.0s)
  - Specific UI formatting preference that would affect elapsed‑time display decisions; removal would alter output.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 24.1s)
  - The entry is a concrete, verifiable preference with specific formatting examples. Removing it would cause the agent to revert to H:MM:SS display for long durations despite user's explicit dislike of hour markers.

### `3362ba488cf7a744`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.82, necessity=0.67

**Original entry:**

> When selecting LLM models for configurations, user prefers "frontier chat across all providers" — comprehensive coverage of high-quality chat models from multiple providers (Anthropic, OpenAI, Google, DeepSeek, Qwen, etc.).

**Justification:** The entry captures a specific, named preference ('frontier chat across all providers') with concrete examples of providers, which would meaningfully guide model selection decisions. Single-session corroboration limits confidence, but the specificity is sufficient to retain.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.75, necessity=0.70, 3.3s)
  - The entry captures a specific, named preference ('frontier chat across all providers') with concrete examples of providers, which would meaningfully guide model selection decisions. Single-session corroboration limits confidence, but the specificity is sufficient to retain.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.30, 5.7s)
  - The entry states a user preference for frontier chat across providers with named examples, but it is a generic guidance rather than a concrete command; its removal would not affect agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 22.8s)
  - The entry is specific with named entities (Anthropic, OpenAI, Google, etc.) and directly impacts model selection behavior. Removing it would change the agent's decision to prioritize comprehensive multi-provider coverage.

### `3adf210f1341a445`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.70

**Original entry:**

> When asking about architecture decisions, user wants concrete reusability analysis ("who is consumer #3") rather than speculative abstraction. Values YAGNI principle and practical justification for shared libraries.

**Justification:** The entry captures a specific, actionable preference—demanding concrete consumer identification ('who is consumer #3') before advocating shared libraries—that would meaningfully change how the agent responds to architecture discussions. The YAGNI framing and the concrete example phrase make it retrievable and non-obvious.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.4s)
  - The entry captures a specific, actionable preference—demanding concrete consumer identification ('who is consumer #3') before advocating shared libraries—that would meaningfully change how the agent responds to architecture discussions. The YAGNI framing and the concrete example phrase make it retrievable and non-obvious.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.80, 4.4s)
  - The entry captures a specific user behavior and principle (concrete reusability analysis, YAGNI, shared libraries) that guides agent responses; removing it would alter how the agent handles architecture queries.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 7.0s)
  - The entry provides useful general guidance on the user's preference for practical justification over speculative abstraction, which could influence the agent's tone and approach. However, it lacks specific, verifiable details such as named entities or precise quotes, and its removal may not significantly alter concrete decisions due to its general nature.

### `41503ab4453d0474`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.57, necessity=0.60

**Original entry:**

> When reviewing PRs that have been open for a while: wants thorough audit across the codebase, not just quick fixes. Appreciates being asked to "be discerning and fan out your team as necessary" when investigating scope/completeness. Values comprehensive investigation of what the PR might have missed or what main has changed since the merge base.

**Justification:** This entry captures a specific behavioral preference—thorough codebase-wide audits for long-open PRs, including a near-direct quote ('be discerning and fan out your team as necessary')—that would meaningfully change how the agent scopes PR review tasks. It is specific enough to be retrievable and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.6s)
  - This entry captures a specific behavioral preference—thorough codebase-wide audits for long-open PRs, including a near-direct quote ('be discerning and fan out your team as necessary')—that would meaningfully change how the agent scopes PR review tasks. It is specific enough to be retrievable and actionable.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 6.4s)
  - The entry offers useful but generic guidance on PR audits and lacks concrete specifics; its removal would affect review depth but not cause a specific decision change.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 35.2s)
  - The entry contains useful guidance with a precise quote ('be discerning and fan out your team as necessary'), but it is not tied to specific entities or commands. Removing it would slightly reduce contextual nuance in PR review behavior but not fundamentally alter outcomes.

### `4fe0da7c8b7f985f`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.67, necessity=0.83

**Original entry:**

> When CodeRabbit suggests a Ruff rule violation, check the project's ruff.toml first — if the rule isn't enabled, the suggestion may be unhelpful. Justify by noting the rule isn't enforced and that fixing creates inconsistency with existing production patterns. Check project lint config before applying style/rule suggestions.

**Justification:** This entry provides concrete, actionable guidance specific to CodeRabbit and ruff.toml interactions that would meaningfully change agent behavior when evaluating lint suggestions. The named tools (CodeRabbit, Ruff, ruff.toml) and the specific reasoning pattern (check config before accepting suggestions) make it retrievable and non-obvious.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.4s)
  - This entry provides concrete, actionable guidance specific to CodeRabbit and ruff.toml interactions that would meaningfully change agent behavior when evaluating lint suggestions. The named tools (CodeRabbit, Ruff, ruff.toml) and the specific reasoning pattern (check config before accepting suggestions) make it retrievable and non-obvious.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=1.00, 3.9s)
  - The entry gives a concrete tip about checking ruff.toml, but the advice is general rather than a precise fact, leading to moderate quality. Its removal would affect the agent's handling of Ruff suggestions, so it is necessary.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.70, 8.7s)
  - The entry provides specific, actionable guidance related to Ruff rule violations and project configuration, making it both useful and likely to influence agent behavior. However, it does not reach the highest quality threshold due to the absence of named entities or specific commands, and its necessity is moderately high as it offers project-specific insight that might not be covered elsewhere but could be inferred by a knowledgeable agent.

### `552517c9122f43f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.57, necessity=0.60

**Original entry:**

> When resolving conflicts between openshell-sdk refactors and upstream changes: prefer extending the SDK to accept new parameters rather than falling back to inline implementations in consumers like openshell-cli. Keep shared logic in the SDK.

**Justification:** This entry is specific to named projects (openshell-sdk, openshell-cli) and captures a concrete architectural preference that would directly influence decisions about where to place shared logic. Removing it could lead the agent to suggest inline implementations in consumers rather than extending the SDK.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.4s)
  - This entry is specific to named projects (openshell-sdk, openshell-cli) and captures a concrete architectural preference that would directly influence decisions about where to place shared logic. Removing it could lead the agent to suggest inline implementations in consumers rather than extending the SDK.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.3s)
  - The entry offers general architectural advice that is somewhat specific but not a concrete fact or critical rule.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 10.7s)
  - The entry provides useful general guidance for resolving conflicts between SDK refactors and upstream changes, but it lacks specific, verifiable details such as named entities, commands, or version numbers. Its removal would not significantly alter agent behavior, as the advice is considered best practice and may already be implied in the system prompt or covered elsewhere.

### `59c8938da3dfc3dc`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.77

**Original entry:**

> Prefers all project outputs in consistent locations under REPO_ROOT (e.g., nat-jobs/, eval-out/, optimizer_results/). When adding new output directories, check existing stages first to match the pattern.

**Justification:** The entry provides actionable, project-specific guidance with concrete named directories (nat-jobs/, eval-out/, optimizer_results/) and a clear behavioral rule about checking existing stages before adding new output dirs. Specific enough to influence real decisions without being derivable from general principles.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.70, 3.3s)
  - The entry provides actionable, project-specific guidance with concrete named directories (nat-jobs/, eval-out/, optimizer_results/) and a clear behavioral rule about checking existing stages before adding new output dirs. Specific enough to influence real decisions without being derivable from general principles.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 3.9s)
  - The entry gives concrete, actionable guidance on output directory placement that would affect agent behavior if removed, and contains no refactorable defects.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 15.4s)
  - The entry provides specific, verifiable patterns with named directories (nat-jobs/, eval-out/, optimizer_results/) and concrete guidance on directory structure. Removing it would lead to inconsistent output placement decisions, as it directly informs where to place project artifacts.

### `7bb47dba9a7be92c`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.63

**Original entry:**

> Prefers proper tool/API usage over guessing: "please use your skills/mcp server (don't just randomly set stuff)" when working with external systems like NVBugs.

**Justification:** The entry includes a direct quote and names a specific external system (NVBugs), making it concrete and retrievable. It signals a preference that would affect agent behavior when working with NVBugs or similar tool-mediated workflows.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.60, 3.8s)
  - The entry includes a direct quote and names a specific external system (NVBugs), making it concrete and retrievable. It signals a preference that would affect agent behavior when working with NVBugs or similar tool-mediated workflows.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=0.80, 9.8s)
  - Concrete quoted instruction that directly influences tool usage decisions; removal would alter agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 32.2s)
  - The entry contains a specific, verifiable quote with named entities (NVBugs, MCP server) and concrete guidance about tool usage, making it high quality. However, removal might not change core decisions but could reduce emphasis on proper API/tool usage in edge cases, justifying moderate necessity.

### `7d5cfef6e3046c40`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.92, necessity=0.92

**Original entry:**

> Branch naming convention: `md/<issue-number>-<short-description>`. Prefers `/md` as branch suffix when creating worktrees (not `+md` or other variants).

**Justification:** This entry is specific and actionable, naming the exact branch naming convention (`md/<issue-number>-<short-description>`) and the preferred worktree suffix (`/md` not `+md`). Without it, the agent would likely default to generic or incorrect conventions when creating branches or worktrees.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.85, necessity=0.90, 3.3s)
  - This entry is specific and actionable, naming the exact branch naming convention (`md/<issue-number>-<short-description>`) and the preferred worktree suffix (`/md` not `+md`). Without it, the agent would likely default to generic or incorrect conventions when creating branches or worktrees.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.85, 5.0s)
  - The rule provides a clear, verifiable naming pattern and explicitly excludes alternatives, making it specific and actionable.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 15.8s)
  - The entry provides a concrete, specific, and verifiable convention for branch naming with direct examples, making it a high-quality memory. Its removal would impact the agent's ability to follow this exact pattern when creating worktrees, affecting behavior.

### `81d7a0d390ee897d`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.87, necessity=0.83

**Original entry:**

> Uses @filename syntax to reference files (e.g., "@RFC-migrate-off-stainless.md"). When user mentions a document by name or reference, ask for location/path rather than searching blindly.

**Justification:** This entry captures a concrete user convention (@filename syntax) with a specific example, and the actionable guidance (ask for path rather than searching blindly) would meaningfully change agent behavior. Single-session corroboration is a mild concern, but the signal is specific enough to be worth retaining.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.70, 3.8s)
  - This entry captures a concrete user convention (@filename syntax) with a specific example, and the actionable guidance (ask for path rather than searching blindly) would meaningfully change agent behavior. Single-session corroboration is a mild concern, but the signal is specific enough to be worth retaining.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.80, 3.5s)
  - The entry is specific about @filename usage and the required behavior, and removing it would affect how the agent handles file references.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 23.9s)
  - The entry provides a specific, verifiable syntax ('@filename') with a concrete example and actionable instruction. Removing it would change agent behavior by allowing uninformed file searches instead of prompting for paths.

### `8f83115f4850f5ef`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.65, necessity=0.60

**Original entry:**

> Prefers accepting Python tracebacks for rare edge cases (e.g., stat-able but not list-able directories) over defensive TOCTOU permission checks. Values clean error paths for expected failures, tolerates crashes for truly exceptional conditions.

**Justification:** This entry captures a specific, actionable preference about error-handling philosophy (TOCTOU checks vs. letting Python raise tracebacks for genuinely rare filesystem edge cases) that would meaningfully influence code-generation decisions. It is specific enough to be retrievable and non-obvious.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.7s)
  - This entry captures a specific, actionable preference about error-handling philosophy (TOCTOU checks vs. letting Python raise tracebacks for genuinely rare filesystem edge cases) that would meaningfully influence code-generation decisions. It is specific enough to be retrievable and non-obvious.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.75, necessity=0.50, 5.8s)
  - The entry provides a clear, specific preference about error handling that is not redundant and would affect agent decisions in edge cases.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 35.7s)
  - The entry provides useful guidance on error handling preferences but lacks specific examples, commands, or named entities that would make it highly retrievable. Removal might slightly alter the agent's tone toward error handling but would not change concrete decisions already implied by the system's broader safety protocols.

### `aa59a8b701389ed4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.68, necessity=0.63

**Original entry:**

> Has extensive experience writing OpenAPI parsers/utils. Previously worked at Gretel where he used OpenAPI Generator and had to hack internals to get good bindings. This background informs his skepticism about off-the-shelf OpenAPI generators.

**Justification:** This entry has concrete named entities (Gretel, OpenAPI Generator) and a specific detail about hacking internals, making it retrievable and actionable. It would change agent behavior by calibrating recommendations about OpenAPI tooling to match known expertise and skepticism.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.75, necessity=0.80, 3.2s)
  - This entry has concrete named entities (Gretel, OpenAPI Generator) and a specific detail about hacking internals, making it retrievable and actionable. It would change agent behavior by calibrating recommendations about OpenAPI tooling to match known expertise and skepticism.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 4.2s)
  - The entry offers concrete, named-context details about the agent's OpenAPI experience and skepticism, making it specific and moderately necessary for behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 22.9s)
  - The entry provides specific named entities (Gretel, OpenAPI Generator) that add verifiable context, but lacks concrete details like version numbers or quotes. Removal might soften the skepticism justification but wouldn't alter major decisions.

### `afee580c9feb00bf`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.67, necessity=0.62

**Original entry:**

> When writing docstrings and comments, avoid leaking development details: no references to "earlier code", "existing implementations", "coverage gaps", meta-commentary on test suite state, or vestigial wording from removed features. Documentation should describe current behavior cleanly, not expose how it evolved. User will ask to "audit docstrings for leakage" and expects patterns like "the existing X tests" or "closes a coverage gap" to be removed.

**Justification:** This entry is specific and actionable, with concrete anti-patterns quoted ("the existing X tests", "closes a coverage gap") and a named trigger phrase ("audit docstrings for leakage"). Removing it would cause the agent to miss these particular documentation hygiene requirements unless explicitly reminded.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.80, necessity=0.85, 4.0s)
  - This entry is specific and actionable, with concrete anti-patterns quoted ("the existing X tests", "closes a coverage gap") and a named trigger phrase ("audit docstrings for leakage"). Removing it would cause the agent to miss these particular documentation hygiene requirements unless explicitly reminded.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.50, 3.5s)
  - Clear guidance on avoiding development detail leakage in docstrings; useful but not a high‑priority prompt item.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 15.4s)
  - The entry provides useful general guidance for documentation practices but lacks concrete facts or specific examples that would elevate it to a 1.0 quality score. Removing it would not change core agent decisions but might lead to less precise documentation tone, warranting a 0.5 necessity score. It avoids duplication and does not contain nameable defects requiring refinement.

### `b287eaa965ce9712`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.73, necessity=0.77

**Original entry:**

> When evaluating review feedback (like coderabbit comments), prefers to "fan out and get multiple opinions" — have multiple independent reviewers assess each point with different lenses, then synthesize their consensus.

**Justification:** This captures a specific and somewhat unusual workflow preference (multi-agent/multi-perspective review synthesis) that would meaningfully change how the agent handles code review tasks like CodeRabbit feedback. It's concrete enough to be actionable and not something a default agent would infer.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 4.0s)
  - This captures a specific and somewhat unusual workflow preference (multi-agent/multi-perspective review synthesis) that would meaningfully change how the agent handles code review tasks like CodeRabbit feedback. It's concrete enough to be actionable and not something a default agent would infer.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.3s)
  - Moderate quality general guidance that is not concrete enough for promotion; removal likely won't affect concrete decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 32.4s)
  - The entry is specific with a named entity ('coderabbit comments') and a precise quoted strategy ('fan out and get multiple opinions'), making it verifiable. Its removal would remove a concrete behavioral directive for feedback evaluation, altering agent decision-making.

### `bd67f4f43e9c9694`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.83, necessity=0.67

**Original entry:**

> Identity-shaped prompts ("you are a deliberate collaborator who...") belong at the very top of CLAUDE.md/AGENTS.md, not buried in bullet lists. They set the lens through which all other rules are read. Placement matters: framing at the top establishes character; the same content as rule #7 just gets weighted alongside everything else.

**Justification:** This entry provides specific, actionable guidance about document structure (CLAUDE.md/AGENTS.md) with a concrete rationale—identity-framing at the top sets interpretive context for all other rules. It's specific enough to influence a real decision when the agent is helping structure such files, and the named file targets give it retrievability.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 4.3s)
  - This entry provides specific, actionable guidance about document structure (CLAUDE.md/AGENTS.md) with a concrete rationale—identity-framing at the top sets interpretive context for all other rules. It's specific enough to influence a real decision when the agent is helping structure such files, and the named file targets give it retrievability.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.90, 6.5s)
  - Specific instruction about where to place identity-shaped prompts; crucial for rule hierarchy.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 24.8s)
  - The entry provides specific, actionable guidance about document structure (CLAUDE.md/AGENTS.md) with concrete placement rules. While removal wouldn't alter core decision-making, it would weaken the emphasis on framing principles that shape interpretive context.

### `c39e32157fe70312`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.97, necessity=0.97

**Original entry:**

> Assigns Tyler Bray (GitHub: tylersbray, email: tbray@nvidia.com) as reviewer for CLI and agent-related work on NeMo Platform.

**Justification:** This entry contains specific named entities (person, GitHub handle, email, domain area) that would directly change agent behavior when routing reviews or tagging reviewers for CLI/agent work on NeMo Platform. Highly concrete and retrievable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.90, necessity=0.90, 3.3s)
  - This entry contains specific named entities (person, GitHub handle, email, domain area) that would directly change agent behavior when routing reviews or tagging reviewers for CLI/agent work on NeMo Platform. Highly concrete and retrievable.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=1.00, 2.9s)
  - Specific, verifiable assignment of reviewer Tyler Bray with concrete identifiers and role.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 20.8s)
  - The entry contains concrete, verifiable information with named entities (Tyler Bray, GitHub handle, email) and specific domain context (CLI/agent work on NeMo Platform). Removal would impact the agent's ability to correctly assign review responsibilities, which are context-specific and not covered by general prompts.

### `d78b6a695264b8f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.78, necessity=0.67

**Original entry:**

> Prefers dropping features entirely when their value proposition weakens rather than maintaining stopgap solutions or adding CLI complexity to preserve them. Applies "re-evaluate dependent features" principle consistently. Example: removed `--model` flag from usage CLI because richer artifact data (trajectory.json) will eventually provide authoritative model identity, avoiding two-sources-of-truth problems.

**Justification:** The entry is specific and grounded with a concrete example (removing `--model` flag due to trajectory.json providing authoritative model identity), which makes it retrievable and actionable. It captures a non-obvious design preference that would directly affect decisions about whether to maintain stopgap features, and its 2-session corroboration adds credibility.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.75, necessity=0.70, 3.6s)
  - The entry is specific and grounded with a concrete example (removing `--model` flag due to trajectory.json providing authoritative model identity), which makes it retrievable and actionable. It captures a non-obvious design preference that would directly affect decisions about whether to maintain stopgap features, and its 2-session corroboration adds credibility.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 3.7s)
  - Concrete example of removing the `--model` flag using `trajectory.json`, specific enough to retain.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.70, 5.0s)
  - The entry is specific with a concrete example, making it verifiable and retrievable. Removing it might not change a concrete decision immediately, but it provides valuable context for decision-making, hence a moderate necessity score.

### `d79b57fd26ea50c1`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.70

**Original entry:**

> Prefers critical evaluation of automated suggestions (CodeRabbit, linters) — willing to reject suggestions that don't align with actual project config or that introduce unnecessary complexity, even when they come from automated tools.

**Justification:** The entry is moderately specific (names CodeRabbit and linters as concrete examples) and captures a meaningful behavioral preference that would affect how the agent frames tool suggestions—encouraging critical evaluation rather than blind acceptance. It's not obvious from generic engineering principles and would influence agent tone and recommendations.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 4.0s)
  - The entry is moderately specific (names CodeRabbit and linters as concrete examples) and captures a meaningful behavioral preference that would affect how the agent frames tool suggestions—encouraging critical evaluation rather than blind acceptance. It's not obvious from generic engineering principles and would influence agent tone and recommendations.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.9s)
  - The entry provides a clear, moderately specific guideline about rejecting irrelevant automated suggestions, but it is general guidance rather than a concrete fact; its removal would affect behavior only modestly.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 18.4s)
  - The entry is highly specific with named tools (CodeRabbit, linters) and precise criteria for rejection (project config alignment, unnecessary complexity), making it verifiable and actionable. Removal would risk agents blindly accepting automated suggestions that violate project constraints.

### `e37c64430111426a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.77

**Original entry:**

> When drafting technical content for the user to share with others (team messages, announcements), provide plain editable text rather than trying to match their voice. User explicitly asked for "a couple lines of text that I can edit to sound like me."

**Justification:** The entry captures a concrete, specific preference backed by a direct quote, and it would change agent behavior when drafting team messages or announcements—providing editable plain text rather than polished copy meant to mimic the user's voice. No defect warrants refinement.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.9s)
  - The entry captures a concrete, specific preference backed by a direct quote, and it would change agent behavior when drafting team messages or announcements—providing editable plain text rather than polished copy meant to mimic the user's voice. No defect warrants refinement.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=0.50, 4.4s)
  - The entry is specific, includes a direct user quote, and provides clear guidance; removing it could affect the agent's handling of this user request.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 16.9s)
  - The entry contains a direct user quote and specific context (technical content sharing), making it concrete and verifiable. Removing it would lead the agent to misinterpret the user's explicit request for editable text over voice mimicry.

### `e85750de7b7fc4fa`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.73, necessity=0.60

**Original entry:**

> Prefers canonical specifications to live in language-agnostic artifacts (reviewer prompts, synthesis templates, shell scripts) with each runtime (Claude Code, deepagents-cli) wrapping them with runtime-specific dispatch glue. Reason: keeps substance in one place and isolates runtime quirks, avoiding drift when maintaining parallel implementations in different systems.

**Justification:** The entry captures a specific architectural preference with named systems (Claude Code, deepagents-cli) and concrete artifact types (reviewer prompts, synthesis templates, shell scripts), making it actionable and retrievable. It would meaningfully influence how the agent structures deliverables when working across multiple runtimes.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.7s)
  - The entry captures a specific architectural preference with named systems (Claude Code, deepagents-cli) and concrete artifact types (reviewer prompts, synthesis templates, shell scripts), making it actionable and retrievable. It would meaningfully influence how the agent structures deliverables when working across multiple runtimes.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.6s)
  - The entry expresses a general architectural preference without concrete defects, so it should be retained as a reusable guideline.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 42.7s)
  - The entry provides specific concrete guidance with named entities (Claude Code, deepagents-cli) and addresses a non-obvious architectural pattern. While the core principle could be inferred by a thoughtful engineer, the runtime-specific examples and precise implementation recommendation elevate its quality. However, removing it would primarily affect code organization tone rather than concrete decision outcomes, as alternative valid approaches exist.

### `eb06022f0c6cec7a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.53

**Original entry:**

> When blocked on unmerged dependencies (PRs, branches), prefers to check out the branch in a worktree and start iterating rather than waiting. Wants action over planning delays.

**Justification:** This entry captures a specific, actionable workflow preference (git worktree checkout of dependency branches rather than waiting) that would directly change agent behavior when blocked on unmerged PRs. It's concrete enough to be retrievable in the relevant context.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.3s)
  - This entry captures a specific, actionable workflow preference (git worktree checkout of dependency branches rather than waiting) that would directly change agent behavior when blocked on unmerged PRs. It's concrete enough to be retrievable in the relevant context.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.30, 4.9s)
  - The entry gives a concrete behavior guideline but is not detailed enough for promotion and contains no clear defect that needs fixing.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 24.3s)
  - The entry provides useful guidance about workflow preferences but lacks specific commands, named entities, or precise quotes for high quality. It influences agent tone/prioritization rather than concrete decisions, warranting mid-tier necessity.

### `f5632decb7fda7e1`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.53, necessity=0.53

**Original entry:**

> Prefers "easy stuff first" when tackling problems. Will explicitly call out this approach when breaking down work.

**Justification:** This captures a specific behavioral preference (easy-first ordering with explicit callout) that would influence how the agent structures responses to multi-part problems. Single-session corroboration warrants keeping but not promoting; the signal is concrete enough to be actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 4.9s)
  - This captures a specific behavioral preference (easy-first ordering with explicit callout) that would influence how the agent structures responses to multi-part problems. Single-session corroboration warrants keeping but not promoting; the signal is concrete enough to be actionable.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 2.4s)
  - The entry is a vague preference without concrete identifiers and does not drive specific decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 10.7s)
  - The entry provides useful general guidance about problem-solving approach but lacks specificity (e.g., named entities, concrete examples). Its removal would not significantly alter agent behavior as similar reasoning might be inferred from system prompt or other entries.

### `fb1a3473bef6711a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.70

**Original entry:**

> Treats RFC review feedback as peer input to evaluate, not gospel: "view it through the lens of a peer with whom you might not agree on everything."

**Justification:** The entry contains a direct quote that anchors a specific, retrievable stance on RFC review feedback—this is not obvious default behavior and would shape how the agent frames disagreement with reviewers. Single-session corroboration limits confidence but the quote specificity warrants retention.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.80, necessity=0.60, 3.6s)
  - The entry contains a direct quote that anchors a specific, retrievable stance on RFC review feedback—this is not obvious default behavior and would shape how the agent frames disagreement with reviewers. Single-session corroboration limits confidence but the quote specificity warrants retention.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=1.00, 5.7s)
  - Provides a concrete directive with a direct quote; removal would change agent behavior toward RFC feedback.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 23.4s)
  - The entry provides useful general guidance on evaluating feedback but lacks specific named entities or concrete examples that would elevate its quality. It influences tone by encouraging critical engagement with feedback, but its removal would not alter core decision-making outcomes, as similar principles might be covered implicitly.

### `0cf94a88d9bf510e`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.78, necessity=0.80

**Original entry:**

> Prefers deep "under the hood" explanations that connect abstract mechanisms to familiar experiences ("you've used this without realizing"). Appreciates bridging theory to practice rather than surface-level how-to guides. 
> 
> ## Time estimates and planning
> 
> Dislikes time estimates in agentic development contexts: "I don't care about estimates and they only serve to muddy the waters. We're all doing agentic development, so engineering days means very little." "Estimates muddy the waters." Considers them subjective and unlikely to influence decisions unless something will take a year. Prefers categorical scales (none/small/non-trivial) over specific durations. What matters is whether a slice depends on hard design calls, not calendar-day framing.

**Justification:** The entry states a clear design preference but is general guidance rather than a concrete, retrievable fact; removing it would affect tone but not a specific decision.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.85, necessity=0.90, 4.1s)
  - The entry combines two distinct topics (explanation style preferences and time-estimate preferences) that should be separate entries for clean retrieval. The time-estimate section is high-quality with direct quotes and specific guidance; the explanation-style section is also useful but unrelated.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 2.6s)
  - The entry states a clear design preference but is general guidance rather than a concrete, retrievable fact; removing it would affect tone but not a specific decision.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 28.5s)
  - The entry contains precise quotes, specific terminology (e.g., 'categorical scales', 'hard design calls'), and directly impacts agent behavior by dictating communication style and planning approach. Removal would lead to concrete decision changes in time estimate handling.

### `1afa1e62e8955f70`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.60

**Original entry:**

> Prefers interactive sessions with think-out-loud reasoning. Wants to be included in the reasoning process, not just presented with conclusions. Values collaborative decision-making over being handed finished answers.

**Justification:** The entry offers general guidance on interactive, collaborative reasoning but is somewhat vague; removing it would mainly affect tone rather than specific decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.60, necessity=0.80, 3.5s)
  - This is a fundamental interaction style preference that would affect nearly every response the agent gives, making it more appropriate as an always-on system prompt directive than a retrieved memory. It meaningfully changes agent behavior (showing reasoning vs. presenting conclusions) and applies broadly enough to warrant constant application.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.7s)
  - The entry offers general guidance on interactive, collaborative reasoning but is somewhat vague; removing it would mainly affect tone rather than specific decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 17.9s)
  - The entry provides useful guidance about collaborative reasoning preferences but lacks specificity or concrete examples that would elevate it to 'promote_to_prompt'. It isn't redundant with system prompts but also doesn't contain defects requiring refinement.

### `1b1ef746cf511fe9`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.88, necessity=0.78

**Original entry:**

> Prefers planning sessions before implementation when tackling complex fixes. When asked "do you have enough information to get started or would you like a planning session?", explicitly requested a plan before coding. 
> 
> ## Technical preferences — code quality and style
> 
> "I'm always in favor of more static typing, dynamic typing is a bug in potentia." Uses EntityClient as reference for preferred typing style.

**Justification:** Specific preference captured with a direct quote and named reference, verifiable and would affect interaction if removed.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.75, necessity=0.85, 2.9s)
  - The entry combines two distinct topics (planning-before-implementation preference and static typing philosophy) that should be separate entries for clean retrieval. This is the concrete defect: multiple distinct topics merged into one.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.50, 4.7s)
  - Specific preference captured with a direct quote and named reference, verifiable and would affect interaction if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 339.7s)
  - The entry contains specific, verifiable technical preferences (direct quote about static typing, reference to EntityClient) and a concrete behavioral observation (requesting planning sessions). These are not redundant with system prompts or other entries. Removal would change the agent's code structuring and planning decisions.

### `2071e206646832a9`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.83, necessity=0.73

**Original entry:**

> When syncing between local and remote document mirrors (e.g., in-repo RFC and Linear doc): update whichever is more current. If both are the same, start with the local copy then push that up. 
> 
> ## Tools and workflows — shell and dotfiles
> 
> Uses zsh with oh-my-zsh. ZDOTDIR is `~/.config/zsh`. Has `.zshrc.local` symlinked to `.config/zsh/locals/.zshrc.work`. Prefers cached completion approach for shell startup performance.

**Justification:** The entry provides concrete, verifiable details about shell configuration and syncing strategy, making it useful and non‑redundant.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.80, 3.9s)
  - The entry combines two distinct topics — document sync policy and shell/dotfiles configuration — which should be separated into independent entries for retrieval clarity.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.40, 5.5s)
  - The entry provides concrete, verifiable details about shell configuration and syncing strategy, making it useful and non‑redundant.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 311.3s)
  - The entry contains concrete, specific information with named entities (e.g., zsh, oh-my-zsh, ZDOTDIR, `.zshrc.local`), specific file paths, and actionable sync workflows. Removing this would directly affect the agent's configuration and document-syncing decisions, altering its behavior significantly.

### `225dfc15f4624267`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.80

**Original entry:**

> When monitoring PRs for code review feedback: Apply good CodeRabbit suggestions automatically, but justify and reply to unhelpful ones before resolving. Team member feedback carries more weight — flag those for user review instead of fixing automatically.

**Justification:** Moderate quality specific guidance; removal would affect agent behavior, so it should be kept.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.90, 4.2s)
  - This entry defines a clear, actionable workflow for PR review that meaningfully differentiates behavior by source (CodeRabbit vs. team members) and action type (auto-fix vs. flag for review). It applies broadly enough to every PR-monitoring task that it should be always-on rather than retrieved situationally.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=1.00, 7.6s)
  - Moderate quality specific guidance; removal would affect agent behavior, so it should be kept.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 28.1s)
  - The entry provides useful guidance for code review behavior but lacks concrete specifics like named commands or version numbers. It influences behavior by prioritizing team feedback over auto-application, but removal would only subtly alter tone rather than core decisions.

### `27ab19ee42afc820`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.88, necessity=0.63

**Original entry:**

> Prefers condensed, action-oriented UIs. Asked to remove verbose descriptions from skill previews and replace Y/n confirmations with clear multi-choice menus (e.g., "1. Install all 2. Select which 3. Skip"). Likes hierarchical multiselect UIs with sublabels showing structure (plugin name > skill names).

**Justification:** Specific UI design preferences with concrete example; useful but not essential for behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.90, 3.5s)
  - This entry is specific (concrete UI patterns with verbatim examples), broadly applicable to any interactive CLI or UI design session, and would materially change agent behavior on every interface-design task—making it a strong candidate for the always-on system prompt rather than retrieval-dependent memory.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.50, 4.0s)
  - Specific UI design preferences with concrete example; useful but not essential for behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 16.1s)
  - The entry provides specific UI preferences with concrete examples (e.g., replacing Y/n with numbered options, hierarchical multiselect structure). While it would change implementation tone if removed, core functionality might still align with general good UX principles from other entries.

### `2c52e8806ac9ede6`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.67

**Original entry:**

> ## Collaboration style
> 
> Keeps user in the development loop — "Be vocal if you are missing information or could use another set of eyes from me." Wants gaps and uncertainties surfaced explicitly rather than having the agent make assumptions. When uncertain, do less not more — pause before spawning ceremony. Values being asked questions when the path is unclear.

**Justification:** Provides general collaboration guidance that is useful but not concrete; removal would affect tone rather than specific agent decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=1.00, 4.5s)
  - This entry has 8-session corroboration, contains a direct quote, and defines a concrete behavioral rule (pause before spawning ceremony, surface gaps explicitly, ask questions when uncertain) that should govern every interaction — not just retrieved ones. It belongs in the always-on system prompt.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.9s)
  - Provides general collaboration guidance that is useful but not concrete; removal would affect tone rather than specific agent decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 35.9s)
  - The entry provides useful but general guidance about collaboration style. It lacks specific examples or named entities warranting a higher quality score. Removal would slightly weaken the emphasis on explicit uncertainty surfacing but not alter core behavior, hence moderate necessity.

### `33490df8bf4790b5`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.80

**Original entry:**

> For bug reports, user wants diagnostic findings without fix recommendations ("avoid making fix recommendations since this is a bug"). Keep bug issues descriptive of the problem, not prescriptive of the solution.

**Justification:** Guidance is specific but general; no concrete defect requiring refinement, and removal would affect tone but not critical behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 3.1s)
  - This is a clear, actionable behavioral rule with a direct quote that would materially change how the agent responds to bug reports. It applies broadly enough across all bug-related interactions to belong in the always-on system prompt rather than being retrieved situationally.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.1s)
  - Guidance is specific but general; no concrete defect requiring refinement, and removal would affect tone but not critical behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 24.1s)
  - The entry provides a concrete, verifiable directive with a quoted user requirement ('avoid making fix recommendations since this is a bug'), which is specific and actionable. Removing it would cause the agent to improperly include fix recommendations in diagnostic responses.

### `3b633c1de36c5c76`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.60, necessity=0.77

**Original entry:**

> When user provides explicit design decisions or answers to questions, proceed with those answers rather than continuing extensive exploration. Values efficiency when decisions are already made. When scoping work, prefers to clarify intent if the request is ambiguous rather than having agent guess. Often refines scope or clarifies intent rather than picking from menus. Prefers narrow, well-scoped iterations over committing to large sweeps upfront.

**Justification:** The entry provides a clear, actionable guideline on clarifying intent and preferring narrow iterations, which is necessary for agent decisions; it has moderate quality but no correctable defect.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.70, necessity=0.90, 3.7s)
  - This entry captures consistent, session-corroborated behavioral preferences (don't over-explore when decisions are made, clarify ambiguity rather than guess, prefer narrow iterations) that should govern nearly every interaction. With 3-session corroboration and direct impact on agent decision-making style, it belongs in the always-on system prompt rather than being retrieved situationally.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.90, 6.1s)
  - The entry provides a clear, actionable guideline on clarifying intent and preferring narrow iterations, which is necessary for agent decisions; it has moderate quality but no correctable defect.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 24.0s)
  - The entry provides useful general guidance about user preferences for decision-making and scoping but lacks concrete specifics (e.g., named entities, commands, or exact quotes) to qualify as high-quality. It may influence subtle behavioral adjustments (e.g., prioritizing clarification) but does not dictate concrete decisions, so removal might slightly alter tone without changing core outcomes.

### `3ebdcd9b6c4913b5`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.40, necessity=0.37

**Original entry:**

> Comfortable with uncertainty and explicit about unknowns. Will say "I genuinely don't know" rather than guessing. Values honesty about knowledge gaps in decision-making.

**Justification:** The entry expresses a useful principle but is vague and not tied to specific entities or concrete commands, so its quality is moderate. It would likely affect tone but not fully replace any explicit decision-making behavior, yielding moderate necessity.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `drop` (quality=0.20, necessity=0.10, 3.7s)
  - This entry describes a generic epistemic virtue ('comfortable with uncertainty, says I don't know') that could apply to almost any thoughtful person and provides no concrete, retrievable signal specific to this user. Single-session corroboration and no named entities or specific examples make it too vague to drive different agent behavior.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.9s)
  - The entry expresses a useful principle but is vague and not tied to specific entities or concrete commands, so its quality is moderate. It would likely affect tone but not fully replace any explicit decision-making behavior, yielding moderate necessity.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 11.3s)
  - The entry provides useful general guidance about desired agent behavior but lacks specific, verifiable details. It influences tone rather than concrete decisions, making it moderately necessary but not critical.

### `44321d2304e81f90`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.60

**Original entry:**

> Comfortable with "YOLO" approaches for small changes vs. rigid testing. Pragmatic about testing — willing to YOLO small changes and defer test infrastructure until it's genuinely needed. 
> 
> ## Named people, tools, and projects
> 
> User is Max Dubrinsky (mdubrinsky@nvidia.com, GitHub: maxdubrinsky).

**Justification:** Specific named entities and clear preference, but remains general guidance without concrete commands.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.60, necessity=0.80, 3.6s)
  - The entry combines two distinct topics — Max's pragmatic testing philosophy and his PII/identity information — which should be separate entries for clean retrieval. This is the 'combines multiple distinct topics' defect.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.50, 3.6s)
  - Specific named entities and clear preference, but remains general guidance without concrete commands.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 54.1s)
  - Entry is a concrete fact with named entities (Max Dubrinsky) and specific development philosophy, making it verifiable and retrievable. Removal might alter the agent's testing strategy tone when collaborating with Max, but core outcomes could still align with general engineering practices.

### `4c3b54653e36b0a0`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.67

**Original entry:**

> When macOS sandbox causes permission errors with local services, user wants commands run without sandbox immediately (no need to ask first).

**Justification:** This entry captures a specific behavioral preference (skip asking, run without sandbox immediately) for a concrete macOS scenario, which would meaningfully change agent behavior if removed. The quality is good but not perfect since it lacks specific command examples.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.8s)
  - This entry captures a specific behavioral preference (skip asking, run without sandbox immediately) for a concrete macOS scenario, which would meaningfully change agent behavior if removed. The quality is good but not perfect since it lacks specific command examples.
- `nvidia-nemotron-3-nano-30b-a3b` -> `drop` (quality=0.40, necessity=0.20, 6.9s)
  - It is a vague preference without concrete commands, and removing it would not noticeably affect the agent’s behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=1.00, 22.4s)
  - The entry provides useful general guidance about user preferences for macOS sandbox scenarios but lacks specific commands or named entities. Removing it would change agent behavior (necessity=1.0), as the agent would no longer know to bypass sandboxing immediately without confirmation.

### `5312e5c7aaf8d182`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.63

**Original entry:**

> Evaluates code review findings critically with justification. Expects "FIX" vs "DON'T FIX" decisions with clear reasoning, not blind acceptance of all suggestions. Uses cost/benefit analysis for proposed changes. Expects critical evaluation with justification for every decision — prefers seeing reasoning for both what gets applied and what gets rejected.

**Justification:** The entry gives general guidance on critical code review evaluation but remains vague and lacks specific, verifiable details.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.90, 3.7s)
  - This entry captures a consistent, high-impact behavioral preference (critical evaluation with FIX/DON'T FIX reasoning for code review) that would meaningfully change agent behavior if absent. It has 2-session corroboration and applies broadly enough to code review contexts that it belongs in the always-on system prompt rather than being retrieved situationally.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.7s)
  - The entry gives general guidance on critical code review evaluation but remains vague and lacks specific, verifiable details.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 32.6s)
  - The entry provides useful general guidance on code review evaluation but lacks specific entities, commands, or precise quotes. Its removal might reduce critical evaluation depth but wouldn't alter fundamental system behavior if similar principles exist elsewhere.

### `55a644cd8f6ff2c0`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.85, necessity=0.85

**Original entry:**

> Action-oriented when path is clear. "Don't have time to dawdle" — wants implementation over extended discussion when requirements are understood and context is available. Trusts recommended paths when offered choices during complex operations. Will choose autonomous completion of git workflows when given the choice. But: "If you have any questions/concerns, stop and ask." Values getting it right over getting it done fast.

**Justification:** The entry contains concrete preferences and a direct quote, influencing agent behavior, and is neither vague nor redundant.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.95, 3.7s)
  - This entry directly shapes agent behavior on a recurring pattern (implementation vs. discussion, autonomous vs. interrupted workflows) and includes specific quotes that anchor the guidance. With 3-session corroboration and high behavioral impact, it belongs in the always-on system prompt rather than retrieval.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.60, 3.6s)
  - The entry contains concrete preferences and a direct quote, influencing agent behavior, and is neither vague nor redundant.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 43.3s)
  - The entry contains concrete behaviors (e.g., autonomous git workflows, trust in recommended paths) and direct quotes that provide specific, verifiable guidance. Removing it would directly impact the agent's decision-making in implementation scenarios.

### `5e218e8023703797`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.92, necessity=0.93

**Original entry:**

> When filing bugs, user prefers minimal investigation — capture the repro and symptoms, don't deep-dive into root cause. User said "Don't work too hard, the person fixing it can dig" when asked not to over-investigate code during bug filing.

**Justification:** The entry provides a concrete user quote and precise guidance on bug filing, directly influencing agent behavior without redundancy.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.90, 3.2s)
  - This is a high-quality, specific preference with a direct quote that would consistently alter agent behavior during bug-filing tasks. It applies broadly enough to warrant always-on availability rather than retrieval.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.90, 5.4s)
  - The entry provides a concrete user quote and precise guidance on bug filing, directly influencing agent behavior without redundancy.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 21.6s)
  - The entry contains a specific, direct quote from the user about bug-filing behavior, which is both verifiable and retrievable. Removing it would cause the agent to over-investigate bugs, altering its core behavior in this domain.

### `6935e3c6fc1098b3`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.60, necessity=0.57

**Original entry:**

> Has deepagents-cli configured with internal model provider access to many interesting models. Plans to use deepagents as the interface where prompt-tuned models will eventually be exposed. Prefers to do most writing/authoring in Claude Code (Opus-4.7 as best coding model) but run execution in deepagents. Watching token spend — cost-conscious when evaluating multi-model approaches.

**Justification:** The entry includes some specific details like Opus-4.7 but remains vague about model access and lacks concrete commands, making it only moderately useful.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.60, necessity=0.80, 4.7s)
  - The entry combines multiple distinct topics: (1) deepagents-cli setup and model access, (2) workflow split between Claude Code and deepagents, (3) cost-consciousness. These should be separated so retrieval surfaces the right signal in context. Also, 'Opus-4.7' appears to be a hallucinated/incorrect model version (likely 'claude-opus-4' or similar) — but since this was the user's stated preference, it should be preserved as-is rather than corrected by the judge. The main defect is topic combination.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.30, 3.4s)
  - The entry includes some specific details like Opus-4.7 but remains vague about model access and lacks concrete commands, making it only moderately useful.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.60, 6.8s)
  - The entry provides specific information about the agent's configuration and preferences, making it useful for retrieval. However, it lacks concrete details like version numbers or specific commands, which prevents it from reaching the highest quality score. Its necessity is moderate as it influences the agent's approach to model usage and cost management, but it may not change concrete decisions on its own.

### `777f85f2c2a6580f`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.60

**Original entry:**

> Framework distinction: **skills are primitives** (single-invocation, single deliverable, no session state), **agents are sessions** (multi-round, collaborative, durable state across turns). Council-of-elders is a primitive so should stay a skill. 
> 
> ## Documentation and writing style
> 
> For RFC and design docs: wants concise text, avoids "puff language," not looking for word count. Prefers "broad strokes" to iterate on rather than deep detail up front.

**Justification:** Provides a clear distinction between skills and agents and specifies documentation style preferences, but remains somewhat general.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.80, 3.9s)
  - The entry combines two distinct topics (skills-vs-agents framework distinction and documentation/writing style preferences) that should be separate entries for clean retrieval.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.7s)
  - Provides a clear distinction between skills and agents and specifies documentation style preferences, but remains somewhat general.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.50, 126.4s)
  - The entry provides useful guidance on distinguishing between skills and agents, which is specific to the system's architecture. However, it does not contain concrete facts or named entities that would warrant a higher quality score. Its removal would not significantly alter agent behavior, as the concepts are likely covered elsewhere or could be inferred by a thoughtful engineer.

### `84d3ccff688a9114`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.62

**Original entry:**

> Tighten text in prompts/instructions — "more text is sometimes less impactful." Values distilled, essential content over verbose explanations. Prefers condensed, to-the-point communication. "Don't try to explain the world" when asking for summaries — wants informative but focused content.

**Justification:** Useful general guidance on concise communication; removing it would only affect tone, not concrete decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 3.2s)
  - This preference directly governs how the agent drafts all responses and prompts — brevity over verbosity is a core behavioral directive. With 3-session corroboration and direct quotes, it's reliable and broadly applicable enough to belong in the always-on system prompt rather than being retrieved situationally.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 7.1s)
  - Useful general guidance on concise communication; removing it would only affect tone, not concrete decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 15.9s)
  - The entry provides specific communication preferences (condensed text, focus on essential content) but lacks named entities or measurable constraints. Removal would slightly reduce clarity in prompts but not alter core decision-making logic.

### `9cd72c55fda5ded2`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.63

**Original entry:**

> Prefers deliberate investigation over trial-and-error. When introducing a new tool, wants agent to "brush up" on how to use it before firing off commands. Values understanding complexity/scope before implementing. Slow at architectural boundaries; iteration speed never substitutes for thinking.

**Justification:** The entry conveys a valid behavioral preference but is vague and not strongly tied to concrete decisions; it should be retained as a memory entry.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.90, 3.7s)
  - This entry captures a core, persistent working style preference—deliberate investigation over trial-and-error, understanding before implementing—that affects nearly every tool introduction and architectural decision. With 4-session corroboration it is well-established, broadly applicable, and should be always-on rather than retrieval-dependent.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.8s)
  - The entry conveys a valid behavioral preference but is vague and not strongly tied to concrete decisions; it should be retained as a memory entry.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 21.0s)
  - The entry provides specific behavioral preferences about tool usage and architectural thinking, but lacks concrete examples or named entities. While not unambiguously retrievable, it offers distinct guidance. Removal might reduce emphasis on preparatory learning, but core system prompt principles likely cover similar ground.

### `a2904a90b343a7bf`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.75, necessity=0.78

**Original entry:**

> Strongly dislikes adding imperatives/directives in front of existing DO/DO NOT blocks in AGENTS.md. "If an agent isn't obeying [the DO/DO NOT block], then I don't know what will." Don't stack ceremony in front of existing instructions. 
> 
> ## Communication style and output preferences
> 
> Prefers terse output, ≲ one terminal screen. Wants response lengths kept shorter — feedback that output "just longer than my screen" was too long.

**Justification:** The entry specifies a clear stylistic rule (keep output terse and within one screen) that guides agent behavior, but it is a general preference rather than a concrete command.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.75, necessity=0.85, 4.9s)
  - The entry combines two distinct topics — AGENTS.md formatting preferences (no stacking imperatives before DO/DO NOT blocks) and general output length preferences — which should be separate entries for targeted retrieval.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 2.4s)
  - The entry specifies a clear stylistic rule (keep output terse and within one screen) that guides agent behavior, but it is a general preference rather than a concrete command.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 57.6s)
  - Entry contains specific directives (e.g., 'DO/DO NOT blocks in AGENTS.md'), direct quotes, and concrete preferences ('terse output, ≲ one terminal screen') that are verifiable and actionable. Removal would alter agent behavior in structuring instructions and output length.

### `b6d1a2581c4fd3b3`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.77

**Original entry:**

> For NVIDIA/OpenShell issues/PRs, user prefers casual, conversational, first-person tone over formal third-person language. Example: "I'm thinking we just add the command" rather than "Adding the command is the better fix." Avoid referring to "maintainers" in third person since the user is part of that group — use inclusive language like "we" or direct proposals. Prefers tight, conversational prose over verbose academic/formal writing. User replaced a 4-paragraph feature-request body with ~3 sentences in first-person. Avoid walls of text in issue/PR drafts — show the minimal viable version first.

**Justification:** General tone guidance that is useful but not concrete; removing it wouldn't change concrete agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.80, necessity=0.80, 5.3s)
  - The entry combines two distinct topics that should be separated: (1) tone/voice preferences for NVIDIA/OpenShell issue/PR drafts, and (2) length/format preferences (minimal viable version, avoid walls of text). Additionally, the entry is more than twice as long as needed — the concrete quote and the 'replaced 4-paragraph with 3 sentences' example are sufficient; the rest is redundant elaboration.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.1s)
  - General tone guidance that is useful but not concrete; removing it wouldn't change concrete agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 25.3s)
  - The entry contains specific, verifiable guidance with named entities (NVIDIA/OpenShell) and concrete examples ('I'm thinking we just add the command'). Removing it would change agent behavior by altering tone and decision-making in issue/PR drafting.

### `c14577e2c749b6a5`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.83, necessity=0.80

**Original entry:**

> Prefers reading long-form documents in Linear rather than in terminal/files. When drafting decision docs or substantial write-ups, post to Linear for easier reading and commenting. 
> 
> ## Code review — council-of-elders pattern
> 
> Uses "council review" pattern for code reviews: multiple independent reviewers examine same diff separately. Review quality bar: "Would the author be glad I flagged this?" (not "technically correct"). Expects 3-8 substantive findings distributed unevenly (anti-checklist rule). Must-fix requires: verbatim quote, named consumer, reproduction path (file:line → trigger → symptom). Prefers precision over quantity; values specific, consequential findings over comprehensive checklists. The point is consensus signal — one reviewer's opinion is noise, two+ reviewers flagging the same thing is signal worth acting on.

**Justification:** Specific and useful guidance but not broad enough to promote to prompt; retains as durable memory.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.80, necessity=0.90, 4.4s)
  - The entry combines two distinct topics (Linear for long-form reading and the council-of-elders code review pattern) that should be separate entries for correct retrieval in relevant contexts.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.80, 4.2s)
  - Specific and useful guidance but not broad enough to promote to prompt; retains as durable memory.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.70, 5.8s)
  - The entry provides specific, verifiable guidance on code review practices and document drafting preferences, making it useful for retrieval. However, its necessity is moderate since some aspects might be inferred from general best practices, though the specifics here add unique value.

### `c793c6c82dacdb5e`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.93, necessity=0.80

**Original entry:**

> Uses marker file pattern for machine-specific config: `touch ~/.config/zsh/.work` on work machines, then conditionally source work config with `[[ -f $ZDOTDIR/.work ]] && source ...`. Prefers this over hostname matching or untracked machine-local files because it's explicit and visible in the repo flow.

**Justification:** Highly specific entry with exact command, file path, and explicit rationale for preferring this pattern over alternatives—agent would use this when helping configure zsh or dotfiles on this user's machines.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.90, necessity=0.80, 3.4s)
  - Highly specific entry with exact command, file path, and explicit rationale for preferring this pattern over alternatives—agent would use this when helping configure zsh or dotfiles on this user's machines.
- `nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.90, necessity=0.60, 6.4s)
  - High-quality, concrete pattern for machine-specific config that is broadly applicable.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 31.3s)
  - The entry provides concrete technical specifics (exact marker file path, conditional sourcing syntax) with named entities, meeting the highest quality bar. Removal would alter the agent's environment configuration decisions, as this method is directly actionable and distinct from alternatives mentioned.

### `cc2763c3925d2b64`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.50

**Original entry:**

> Max Dubrinsky (GitHub: maxdubrinsky) is a maintainer of NVIDIA/OpenShell. Has personal connections to NVIDIA/OpenShell maintainers but contributes via fork (not direct push access).

**Justification:** Specific named‑entity information about a maintainer that is useful but not broad enough for a system prompt, and removing it would not change agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.60, 4.6s)
  - The entry combines two distinct claims that should be separate: (1) Max Dubrinsky's role as a maintainer of NVIDIA/OpenShell, and (2) his contribution method (via fork, not direct push). Additionally, the first sentence contradicts itself—calling him a 'maintainer' while the second sentence says he lacks direct push access, which is a defect requiring clarification.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.30, 6.7s)
  - Specific named‑entity information about a maintainer that is useful but not broad enough for a system prompt, and removing it would not change agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.60, 19.9s)
  - The entry provides concrete details about Max Dubrinsky's role and contribution method, which adds context for interactions with NVIDIA/OpenShell contributors. While not containing quotes or version numbers, it includes named entities and specific relationships. Removal would slightly reduce contextual awareness but not alter core decisions.

### `ccd19a2fa2414c49`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.60

**Original entry:**

> Values consistency across the codebase — when fixing bugs or implementing features, prefers to match broader codebase patterns rather than keeping one-off exceptions ("do whatever is most consistent").

**Justification:** Moderate quality general guidance; removing it would not meaningfully alter behavior, so it stays as a retrievable entry.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 3.3s)
  - This preference directly shapes how the agent handles implementation decisions—favoring consistency over local optimization—and applies broadly enough across all coding interactions to belong in the always-on system prompt rather than being retrieved situationally.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.8s)
  - Moderate quality general guidance; removing it would not meaningfully alter behavior, so it stays as a retrievable entry.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 30.7s)
  - The entry provides useful general guidance about code consistency but lacks specific examples, named entities, or precise implementation details. It would not change concrete agent decisions if removed but might subtly influence coding style choices.

### `da5498e4affca2a0`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.55, necessity=0.62

**Original entry:**

> Expects verification of claims before making breaking changes. Will ask "can you make sure of that" and wants downstream impact checked (e.g., grepping for field usage before removing from public schema). 
> 
> ## Technical preferences — architecture and design
> 
> Data model evolution: prefer to omit fields until there's a concrete consumer. "Easier to add a field than remove one." Keep surface area small in initial implementations rather than pre-emptively adding fields that might be useful later.

**Justification:** The entry provides general guidance on field management that is specific enough but not uniquely retrievable or behavior‑changing.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.65, necessity=0.85, 3.7s)
  - The entry combines two distinct behavioral signals that should be separate entries: (1) verification behavior before breaking changes (with the concrete quote and grep example), and (2) the data-model philosophy of minimal surface area. Splitting them makes each independently retrievable and avoids context pollution when only one is relevant.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 2.2s)
  - The entry provides general guidance on field management that is specific enough but not uniquely retrievable or behavior‑changing.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 5.5s)
  - The entry provides useful general guidance on data model evolution and verification, but it lacks specific, verifiable details or named entities to warrant a higher quality score. Its removal might slightly alter the agent's tone or approach but wouldn't change concrete decisions, hence the medium necessity score.

### `daa44d66c1c0e810`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.75, necessity=0.85

**Original entry:**

> When user explicitly asks for a specific tool or approach (e.g., "use tmux" not just "parallel subagents"), follow it literally — there's always a reason. Don't substitute with "equivalent" alternatives without asking first.

**Justification:** Provides a clear, actionable rule for following explicit user-specified tools, which is specific enough and impacts agent decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 3.3s)
  - This is a high-value behavioral rule with a concrete example ('use tmux' vs 'parallel subagents') that directly governs agent decision-making. It applies broadly enough across all sessions to belong in the system prompt rather than being retrieved situationally.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.70, 5.1s)
  - Provides a clear, actionable rule for following explicit user-specified tools, which is specific enough and impacts agent decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 30.5s)
  - The entry provides specific, verifiable guidance with a concrete example ('use tmux'), making it high-quality. Its removal would change agent behavior by allowing substitutions the user explicitly prohibited, confirming high necessity.

### `ecbfeb8c7243fb9d`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.60

**Original entry:**

> Skills are "capabilities and conventions the agent draws on, not scripts it executes" — avoid making skills overly rigid. Every rigid rule added is future maintenance cost. Prefers to "rely on larger skill routing and context, not rigid skills."

**Justification:** Provides a useful design principle but is general and not uniquely actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.80, 3.2s)
  - This entry captures a specific, corroborated philosophy about skill design with a direct quote, and it broadly governs how the agent should approach all skill definition — making it always-on guidance rather than something to retrieve contextually.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.0s)
  - Provides a useful design principle but is general and not uniquely actionable.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 9.4s)
  - The entry provides useful general guidance on skill design but lacks specific, verifiable details, warranting a quality score of 0.5. Its necessity is moderate, as it influences tone and design philosophy but does not directly impact concrete decisions, resulting in a necessity score of 0.5. No defects are present that would justify refinement, so the entry is kept as-is.

### `ef4733acc96c530e`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.57

**Original entry:**

> Manages dotfiles with GNU Stow for both work and personal machines. Spins up new machines rarely. Prefers declarative, in-repo configuration over implicit machine-local setup. Values shell startup performance, especially in Python repos.

**Justification:** The entry is fairly concrete about using GNU Stow and preferences for declarative dotfile management, but it is somewhat general and not essential for agent decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.60, necessity=0.80, 3.8s)
  - The entry combines two distinct topics that should be separated: (1) dotfile management tooling and machine setup preferences, and (2) shell startup performance in Python repos. Splitting these allows each to be retrieved independently and targeted more precisely.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.40, 3.5s)
  - The entry is fairly concrete about using GNU Stow and preferences for declarative dotfile management, but it is somewhat general and not essential for agent decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 31.5s)
  - The entry provides useful guidance about tool preferences (GNU Stow) and configuration philosophy but lacks concrete specifics like version numbers, exact commands, or measurable metrics. While not unambiguously retrievable, it captures meaningful workflow tendencies. Removal would not alter critical decisions but might affect nuanced configuration advice.

### `f06b7cf3228f3384`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.75, necessity=0.62

**Original entry:**

> When evaluating architectural decisions or migration costs, prefers concrete data: LOC counts, file counts, time estimates broken down by work area. Wants "how many can we delete?" answered with measurements, not speculation.

**Justification:** Useful guideline but not a concrete fact; it influences decisions but could be covered elsewhere.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 3.7s)
  - This entry captures a concrete, actionable communication preference—always answer architectural/migration questions with measured data (LOC, file counts, time breakdowns) rather than speculation—that should influence every such interaction, not just retrieved ones. It is specific enough to change agent behavior and broad enough to apply across sessions.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.1s)
  - Useful guideline but not a concrete fact; it influences decisions but could be covered elsewhere.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 21.1s)
  - The entry specifies concrete examples (LOC counts, file counts) and includes a direct quote ('how many can we delete?'), meeting the highest quality standard. Its removal might reduce specificity in responses but not fundamentally alter core agent behavior, warranting a moderate necessity score.

### `f4a359b3859edf3d`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.88, necessity=0.65

**Original entry:**

> Prefers Python-style pseudocode over LaTeX/mathematical notation for expressing formulas and algorithms. "Prefer python to math since it's been 15 years since I've used LaTeX."

**Justification:** Concrete preference for Python pseudocode that is retrievable but not essential for core decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.95, 3.7s)
  - This is a concrete, actionable formatting preference with a direct quote explaining why—it would change agent behavior any time formulas or algorithms are presented. It applies broadly across all technical interactions, making it a good candidate for the always-on system prompt rather than a retrieved memory.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.50, 6.8s)
  - Concrete preference for Python pseudocode that is retrievable but not essential for core decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 36.9s)
  - The entry contains a specific preference with a direct quote and named entity (LaTeX), meeting quality criteria. Its removal would alter stylistic choices rather than concrete decisions, hence moderate necessity.

### `fa248bb8026a7f3e`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.57

**Original entry:**

> Prefers interactive, incremental onboarding when exploring new codebases. Wants information "fed" in chunks rather than large reports. Starts exploration by examining types and contracts first to understand how data is structured and used.

**Justification:** The entry clearly states a user preference for incremental onboarding with no concrete defect, making it appropriate to retain as is.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.60, necessity=0.80, 3.9s)
  - The entry combines two distinct behavioral signals that should be separated: (1) a general interaction preference (chunked/incremental delivery of information) and (2) a specific exploration methodology (types-and-contracts-first when studying new codebases). Splitting these allows each to be retrieved independently in relevant contexts.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.40, 3.9s)
  - The entry clearly states a user preference for incremental onboarding with no concrete defect, making it appropriate to retain as is.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 4.9s)
  - The entry provides useful general guidance on onboarding preferences but lacks specific, verifiable details or named entities. Removing it would not significantly change agent behavior as the advice is somewhat generic and could be inferred from broader system prompt guidance.

### `fe3b38f60055f95f`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.82, necessity=0.73

**Original entry:**

> When reviewing PRs, user wants to distinguish between issues caused by the PR (net-new) vs issues that were pre-existing on main. Asked explicitly: "Are there any issues created by this PR or are these problems present on the current implementation?"

**Justification:** Specific instruction with a quoted question that is concrete and retrievable, but not essential for core behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.90, 3.4s)
  - This captures a specific, high-value behavioral preference with a direct quote: when reviewing PRs, always distinguish net-new issues introduced by the PR from pre-existing issues on main. This applies broadly to every PR review interaction and should be in the always-on system prompt rather than relying on retrieval.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 3.4s)
  - Specific instruction with a quoted question that is concrete and retrievable, but not essential for core behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.70, 50.1s)
  - The entry provides a specific user requirement with a direct quote, making it concrete and retrievable. The query explicitly distinguishes between PR-introduced and pre-existing issues, which is critical for code review behavior. While the necessity is moderate (as similar guidance might exist elsewhere), removing it would risk the agent overlooking this key distinction during PR review tasks.

### `ffccf834cf1224a4`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.62

**Original entry:**

> Prefers minimal, deliberate solutions over adding configuration mechanisms — "don't want to add that mechanism" when rejecting a sidecar config approach. Favors starting small with explicit overrides and iterating from there.

**Justification:** The entry specifies a clear design preference with a quoted statement, but it is not broad enough for a system prompt and has no correctable defect.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 3.3s)
  - This is a broadly applicable design philosophy (prefer minimal, explicit solutions over configuration mechanisms; start small and iterate) that should inform nearly every technical recommendation the agent makes, not just retrieved in specific sessions. The direct quote adds specificity above the baseline.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.50, 7.1s)
  - The entry specifies a clear design preference with a quoted statement, but it is not broad enough for a system prompt and has no correctable defect.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 46.3s)
  - The entry provides specific context (sidecar config rejection) and a direct quote, adding verifiable detail. However, it aligns with general engineering best practices, reducing uniqueness. Removal might soften tone but not critical decisions, as similar principles likely exist elsewhere.

### `ffebf77904896ae7`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.87, necessity=0.80

**Original entry:**

> Works with NVIDIA projects (NeMo, Studio, Omnipush, etc.) and tests cmux integration. Has access to NVIDIA Omnistations. Working on NeMo Platform agentic-use benchmarking. Has access to NVIDIA NGC/inference API keys.

**Justification:** The entry is concrete about NVIDIA resource access and not redundant, so it should be retained as-is.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.80, 3.8s)
  - The entry combines multiple distinct topics (NVIDIA project affiliations, cmux integration testing, Omnistation access, NeMo Platform benchmarking work, and NGC/API key access) that should be separated for better retrieval. Splitting these allows targeted retrieval when relevant context is needed.
- `nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.60, 4.8s)
  - The entry is concrete about NVIDIA resource access and not redundant, so it should be retained as-is.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 143.9s)
  - The entry contains specific named entities (NeMo, Studio, Omnistations, NGC, cmux) and concrete access details that are verifiable and would impact agent behavior if missing. The specificity justifies top quality and necessity scores.

### `8936920730d38570`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.73, necessity=0.67

**Original entry:**

> Uses dotfiles across multiple platforms (macOS, Ubuntu, Debian, Arch, CentOS). Cannot rely on consistent package managers like homebrew. Prefers cross-platform solutions using shell scripts and git clone over package-manager-specific approaches.

**Justification:** The entry is highly specific with named platforms (macOS, Ubuntu, etc.) and concrete technical preferences (shell scripts, git clone). Removing it would directly impact the agent's ability to prioritize cross-platform solutions over package-manager-specific approaches in dotfile management.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 3.3s)
  - This entry directly governs how the agent should recommend solutions (cross-platform shell scripts + git clone over package-manager-specific approaches) and applies to every technical interaction involving tooling or setup. Its broad applicability and concrete behavioral impact make it a strong candidate for the always-on system prompt rather than retrieval.
- `nvidia-nemotron-3-nano-30b-a3b` -> `drop` (quality=0.40, necessity=0.10, 1.9s)
  - The entry is a vague, general guideline without concrete specifics or named entities, and removing it would not affect agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 22.0s)
  - The entry is highly specific with named platforms (macOS, Ubuntu, etc.) and concrete technical preferences (shell scripts, git clone). Removing it would directly impact the agent's ability to prioritize cross-platform solutions over package-manager-specific approaches in dotfile management.

### `cd59e47469ff3772`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.30, necessity=0.33

**Original entry:**

> Thinks architecturally before implementing — considers whether ideas are "in step with project direction" and evaluates second-order implications. Prefers to ground discussions in actual code before reasoning about design.

**Justification:** The entry provides useful general guidance about architectural thinking and code-grounded discussions but lacks specific, verifiable details. It would likely not change concrete agent decisions if removed, as such principles may be implied in broader prompts or covered by other entries.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.40, necessity=0.50, 4.2s)
  - The entry combines two distinct behavioral signals that should be separated: (1) architectural/second-order thinking before implementing, and (2) preference for grounding design discussions in actual code. These are independent traits that may be retrieved in different contexts.
- `nvidia-nemotron-3-nano-30b-a3b` -> `drop` (quality=0.00, necessity=0.00, 3.9s)
  - The entry is a vague, general description that offers no concrete guidance or influence on agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 19.8s)
  - The entry provides useful general guidance about architectural thinking and code-grounded discussions but lacks specific, verifiable details. It would likely not change concrete agent decisions if removed, as such principles may be implied in broader prompts or covered by other entries.
