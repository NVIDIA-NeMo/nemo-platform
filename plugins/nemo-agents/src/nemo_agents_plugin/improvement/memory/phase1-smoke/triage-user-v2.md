# Memory triage proposals — `pi-hermes:CONSOLIDATED:user`

## Run

- **council:** `azure-anthropic-claude-sonnet-4-5`, `nvidia-nvidia-nemotron-3-nano-30b-a3b`, `nvidia-moonshotai-kimi-k2-6`
- **started:** 2026-06-03T19:06:33.279358+00:00
- **finished:** 2026-06-03T19:35:00.095868+00:00
- **elapsed:** 1706.8s
- **proposals:** 71
- **errors:** 2
- **skipped entries:** 0

## Summary

| verdict | count | % of proposals |
| --- | ---: | ---: |
| `drop` | 1 | 1.4% |
| `merge` | 0 | 0.0% |
| `refine` | 3 | 4.2% |
| `promote_to_prompt` | 2 | 2.8% |
| `keep` | 65 | 91.5% |

## `drop` (1)

### `7350bebdc6f86fbf`

- **verdict:** `drop` (confidence 1.00)
- **scores:** quality=0.33, necessity=0.13

**Original entry:**

> Proponent of good module separation in code organization, even when it differs from existing patterns in the codebase.

**Justification:** This entry is too generic and could apply to any thoughtful software engineer. It provides no specific guidance about what 'good module separation' means for this user, what patterns they prefer, or concrete examples that would differentiate their preferences from standard engineering practice.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `drop` (quality=0.30, necessity=0.10, 3.7s)
  - This entry is too generic and could apply to any thoughtful software engineer. It provides no specific guidance about what 'good module separation' means for this user, what patterns they prefer, or concrete examples that would differentiate their preferences from standard engineering practice.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `drop` (quality=0.50, necessity=0.20, 12.3s)
  - The statement is a vague, general principle with low necessity; removing it would not affect agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `drop` (quality=0.20, necessity=0.10, 19.0s)
  - The entry expresses a generic engineering philosophy that could apply to any thoughtful developer; it lacks named projects, specific patterns, or actionable boundaries and largely restates standard best practices already implied by the system prompt.

## `refine` (3)

### `1b1ef746cf511fe9`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.70

**Original entry:**

> Prefers planning sessions before implementation when tackling complex fixes. When asked "do you have enough information to get started or would you like a planning session?", explicitly requested a plan before coding. 
> 
> ## Technical preferences — code quality and style
> 
> "I'm always in favor of more static typing, dynamic typing is a bug in potentia." Uses EntityClient as reference for preferred typing style.

**Refined text proposed:**

> Prefers planning sessions before implementation when tackling complex fixes. When asked "do you have enough information to get started or would you like a planning session?", explicitly requested a plan before coding.

**Justification:** The entry combines two distinct topics: planning preference and typing philosophy. These should be separated as they address different aspects of workflow and technical style. The typing preference with specific quote and reference is high quality, while the planning preference is also actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.80, 4.6s)
  - The entry combines two distinct topics: planning preference and typing philosophy. These should be separated as they address different aspects of workflow and technical style. The typing preference with specific quote and reference is high quality, while the planning preference is also actionable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.60, 4.9s)
  - The entry contains a concrete quoted preference and specific behavior (requesting planning before coding) that would affect agent decisions, making it valuable and not redundant.
- `nvidia-moonshotai-kimi-k2-6` -> `refine` (quality=0.70, necessity=0.70, 36.8s)
  - The entry combines two unrelated topics—workflow planning preferences and technical static-typing preferences with an EntityClient reference—that should be stored as separate entries for better retrieval and maintenance.

### `c14577e2c749b6a5`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.80, necessity=0.80

**Original entry:**

> Prefers reading long-form documents in Linear rather than in terminal/files. When drafting decision docs or substantial write-ups, post to Linear for easier reading and commenting. 
> 
> ## Code review — council-of-elders pattern
> 
> Uses "council review" pattern for code reviews: multiple independent reviewers examine same diff separately. Review quality bar: "Would the author be glad I flagged this?" (not "technically correct"). Expects 3-8 substantive findings distributed unevenly (anti-checklist rule). Must-fix requires: verbatim quote, named consumer, reproduction path (file:line → trigger → symptom). Prefers precision over quantity; values specific, consequential findings over comprehensive checklists. The point is consensus signal — one reviewer's opinion is noise, two+ reviewers flagging the same thing is signal worth acting on.

**Refined text proposed:**

> Uses "council review" pattern for code reviews: multiple independent reviewers examine same diff separately. Review quality bar: "Would the author be glad I flagged this?" (not "technically correct"). Expects 3-8 substantive findings distributed unevenly (anti-checklist rule). Must-fix requires: verbatim quote, named consumer, reproduction path (file:line → trigger → symptom). Prefers precision over quantity; values specific, consequential findings over comprehensive checklists. The point is consensus signal — one reviewer's opinion is noise, two+ reviewers flagging the same thing is signal worth acting on.

**Justification:** The entry combines two distinct topics: (1) Linear preference for long-form documents and (2) council-of-elders code review pattern. These should be separate entries for better retrievability.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.80, necessity=0.90, 5.0s)
  - The entry combines two distinct topics: (1) Linear preference for long-form documents and (2) council-of-elders code review pattern. These should be separate entries for better retrievability.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 5.6s)
  - The entry gives specific, actionable guidance on code review patterns that is concrete enough to retain but does not merit inclusion in the system prompt.
- `nvidia-moonshotai-kimi-k2-6` -> `refine` (quality=0.80, necessity=0.90, 31.9s)
  - The entry combines two distinct topics—Linear document preferences and a detailed council-of-elders code review pattern—that should be stored as separate entries to improve retrievability and avoid cross-context noise.

### `e626e4bbb2861be3`

- **verdict:** `refine` (confidence 0.67)
- **scores:** quality=0.78, necessity=0.82

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

> Prefers beads (`bd remember`) for persistent memory storage over file-based MEMORY.md. Memories should use kebab-case keys and load via `bd prime` at session start.
> 
> When dispatching multiple agents for tasks like code review, prefers tmux-visible team sessions to monitor each agent's work in separate panes in real-time. Direct quote: "if you can be sure to use a team so sessions launch in tmux that would be helpful."
> 
> Shell startup performance matters, especially in Python repos where multiple chpwd hooks fire (autoswitch_virtualenv, mise, direnv). Seconds-long shell startup is "workable but not ideal." Values async prompts and deferred loading optimizations.

**Justification:** The entry combines three distinct topics (shell startup performance, beads memory tool preferences, and tmux workflow for agent teams) that should be separated. Each topic has specific, actionable content but they are unrelated enough to warrant separate entries for better retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.80, 5.3s)
  - The entry combines three distinct topics (shell startup performance, beads memory tool preferences, and tmux workflow for agent teams) that should be separated. Each topic has specific, actionable content but they are unrelated enough to warrant separate entries for better retrieval.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.85, 11.1s)
  - The entry is specific, includes named tools and commands, and its removal would affect storage and tmux session preferences.
- `nvidia-moonshotai-kimi-k2-6` -> `refine` (quality=0.80, necessity=0.80, 35.3s)
  - The entry bundles three orthogonal preferences—shell startup optimization, beads memory-tool usage, and tmux team-session workflows—that should be stored as separate retrievable entries to avoid retrieval noise.

## `promote_to_prompt` (2)

### `2c52e8806ac9ede6`

- **verdict:** `promote_to_prompt` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.77

**Original entry:**

> ## Collaboration style
> 
> Keeps user in the development loop — "Be vocal if you are missing information or could use another set of eyes from me." Wants gaps and uncertainties surfaced explicitly rather than having the agent make assumptions. When uncertain, do less not more — pause before spawning ceremony. Values being asked questions when the path is unclear.

**Justification:** This entry captures concrete behavioral guidance (pause before action when uncertain, surface gaps explicitly, ask questions) with 8-session corroboration. The principles are fundamental enough to apply across all interactions and would benefit agent behavior globally rather than through retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.90, 5.6s)
  - This entry captures concrete behavioral guidance (pause before action when uncertain, surface gaps explicitly, ask questions) with 8-session corroboration. The principles are fundamental enough to apply across all interactions and would benefit agent behavior globally rather than through retrieval.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 6.0s)
  - The entry gives useful behavioral guidance but is generic rather than a concrete fact, so it does not merit promotion or refinement.
- `nvidia-moonshotai-kimi-k2-6` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 20.2s)
  - This is the highest-corroborated entry in the entire corpus (8 sessions), indicating a stable, universal user preference. It contains a direct quote and concrete behavioral directives that govern autonomy and communication thresholds, making it prime material for the always-on system prompt rather than retrieval.

### `afee580c9feb00bf`

- **verdict:** `promote_to_prompt` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.68

**Original entry:**

> When writing docstrings and comments, avoid leaking development details: no references to "earlier code", "existing implementations", "coverage gaps", meta-commentary on test suite state, or vestigial wording from removed features. Documentation should describe current behavior cleanly, not expose how it evolved. User will ask to "audit docstrings for leakage" and expects patterns like "the existing X tests" or "closes a coverage gap" to be removed.

**Justification:** This entry describes a specific, verifiable pattern (audit docstrings for 'leakage' phrases like 'existing X tests' or 'closes a coverage gap') and provides concrete examples of what to avoid. It would meaningfully change agent behavior when writing documentation. However, as a general documentation quality principle that applies broadly across all coding work rather than being context-specific, it belongs in the system prompt where it can consistently guide all documentation tasks.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.85, necessity=0.75, 5.0s)
  - This entry describes a specific, verifiable pattern (audit docstrings for 'leakage' phrases like 'existing X tests' or 'closes a coverage gap') and provides concrete examples of what to avoid. It would meaningfully change agent behavior when writing documentation. However, as a general documentation quality principle that applies broadly across all coding work rather than being context-specific, it belongs in the system prompt where it can consistently guide all documentation tasks.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.60, necessity=0.50, 4.3s)
  - Clear, broadly applicable guidance on docstring leakage that merits inclusion in the system prompt.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.80, 130.6s)
  - The entry contains specific trigger phrases ('audit docstrings for leakage'), precise quotes to remove ('the existing X tests', 'closes a coverage gap'), and concrete anti-patterns, making it highly retrievable and actionable. Removing it would change how the agent handles a specific user request that is not covered by general system instructions.

## `keep` (65)

### `09d03f0713454d63`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.95, necessity=0.77

**Original entry:**

> Dislikes overly clinical/medical language in documentation headings — rejected "Anatomy of an Agent" in favor of "Agent Definition" when drafting public docs for the NeMo Platform agents page.

**Justification:** Highly specific entry with concrete named entities (exact heading titles, specific platform documentation context) and a verifiable user preference that would influence future documentation decisions. The preference is actionable enough to affect heading choices in similar contexts.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.70, 4.4s)
  - Highly specific entry with concrete named entities (exact heading titles, specific platform documentation context) and a verifiable user preference that would influence future documentation decisions. The preference is actionable enough to affect heading choices in similar contexts.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=0.80, 5.1s)
  - Specific stylistic preference with named headings; essential for consistent heading generation.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.80, 25.6s)
  - The entry includes precise heading examples ('Anatomy of an Agent' vs. 'Agent Definition'), a named platform (NeMo Platform), and a concrete domain (documentation headings), making it a highly specific, retrievable preference that would directly shape future drafting decisions.

### `0f7fb9245ec9337d`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.68

**Original entry:**

> Dislikes "techno-jargon" (e.g., "forcing function," "load-bearing") and em-dashes in written docs — these make text sound AI-generated. Wants their own voice to shine through in RFCs and technical writing.

**Justification:** Entry contains specific, actionable writing preferences with concrete examples ("forcing function," "load-bearing," em-dashes) that would directly influence the agent's word choice and punctuation in technical writing. These are retrievable preferences that would change agent behavior when drafting RFCs or documentation for this user.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 5.6s)
  - Entry contains specific, actionable writing preferences with concrete examples ("forcing function," "load-bearing," em-dashes) that would directly influence the agent's word choice and punctuation in technical writing. These are retrievable preferences that would change agent behavior when drafting RFCs or documentation for this user.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.50, 3.2s)
  - The entry is a clear user preference about avoiding certain jargon and em‑dashes to maintain a personal voice, which is specific enough to be useful but not strong enough for system‑prompt inclusion.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 19.6s)
  - The entry contains specific, quoted examples of disliked jargon and a concrete punctuation preference (em-dashes), tied directly to RFCs and technical writing. Removing it would change the agent's concrete word-choice and punctuation decisions when drafting documents for this user, and the preference is unlikely to be in the base system prompt.

### `1f841c1e54060e46`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.88, necessity=0.83

**Original entry:**

> When filing GitHub issues, user prefers to "leave the labeling for someone else" — apply only obviously correct labels, leave discretionary labels to human reviewers.

**Justification:** Entry contains a specific, actionable preference with a direct quote about GitHub issue labeling behavior. It would meaningfully change agent decisions when filing issues - specifically which labels to apply and which to defer to human reviewers.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.85, 3.8s)
  - Entry contains a specific, actionable preference with a direct quote about GitHub issue labeling behavior. It would meaningfully change agent decisions when filing issues - specifically which labels to apply and which to defer to human reviewers.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.90, 6.1s)
  - The entry specifies a distinct user behavior for GitHub issue labeling that is concrete and would affect agent decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.75, 14.2s)
  - The entry contains a direct quote and specific behavioral guidance for GitHub issue filing that would materially change agent actions, but is narrow enough to remain in durable memory rather than the system prompt.

### `225dfc15f4624267`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.65, necessity=0.72

**Original entry:**

> When monitoring PRs for code review feedback: Apply good CodeRabbit suggestions automatically, but justify and reply to unhelpful ones before resolving. Team member feedback carries more weight — flag those for user review instead of fixing automatically.

**Justification:** Entry contains specific, actionable guidance about handling CodeRabbit (named tool) vs. team member feedback differently during PR review, with concrete decision criteria (auto-apply vs. flag for review). The distinction between automated tool suggestions and human feedback represents a verifiable behavioral rule that would change agent decisions if removed.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.80, 4.5s)
  - Entry contains specific, actionable guidance about handling CodeRabbit (named tool) vs. team member feedback differently during PR review, with concrete decision criteria (auto-apply vs. flag for review). The distinction between automated tool suggestions and human feedback represents a verifiable behavioral rule that would change agent decisions if removed.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.5s)
  - The entry provides useful general guidance but lacks concrete, retrievable specifics such as exact commands or named entities.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.85, 11.1s)
  - Specific operational preference distinguishing between automated tool (CodeRabbit) and human team member feedback with clear action protocols; removing it would change concrete agent decisions on PRs.

### `24883461872a7245`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.62, necessity=0.68

**Original entry:**

> Prefers explicit credential mapping between services. Does not want automatic substitution of credentials meant for one API provider as fallback credentials for a different provider, even when upstream code has such fallback chains.

**Justification:** This is a specific, actionable preference about credential handling behavior that would concretely change how the agent configures API integrations. The entry clearly states opposition to automatic credential fallback chains, which is verifiable and would directly affect implementation decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.85, 3.2s)
  - This is a specific, actionable preference about credential handling behavior that would concretely change how the agent configures API integrations. The entry clearly states opposition to automatic credential fallback chains, which is verifiable and would directly affect implementation decisions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.4s)
  - The entry expresses a clear preference about credential mapping but is a general guidance statement without concrete commands or examples, so it is not high quality nor critical for behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 15.3s)
  - Captures a specific, actionable constraint about credential isolation across API providers that would change integration code decisions, though it lacks named entities to make it fully concrete.

### `27ab19ee42afc820`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.78, necessity=0.77

**Original entry:**

> Prefers condensed, action-oriented UIs. Asked to remove verbose descriptions from skill previews and replace Y/n confirmations with clear multi-choice menus (e.g., "1. Install all 2. Select which 3. Skip"). Likes hierarchical multiselect UIs with sublabels showing structure (plugin name > skill names).

**Justification:** Entry contains specific, concrete UI preferences with clear examples (Y/n → numbered menu, hierarchical multiselect with sublabels). These preferences would directly change how the agent designs confirmation prompts and selection interfaces. High necessity because removing it would eliminate actionable UI design guidance.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 3.5s)
  - Entry contains specific, concrete UI preferences with clear examples (Y/n → numbered menu, hierarchical multiselect with sublabels). These preferences would directly change how the agent designs confirmation prompts and selection interfaces. High necessity because removing it would eliminate actionable UI design guidance.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.60, 3.4s)
  - The entry clearly states a preference for condensed, action‑oriented UIs with concrete examples of menu formats and hierarchical multiselect structures, making it both specific enough to be retrievable and influential on design decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.80, 14.9s)
  - The entry contains precise, retrievable UI preferences with concrete examples (specific multi-choice menu wording and hierarchical labeling patterns) that would directly change generated interface behavior if removed.

### `2b3f32758b063f73`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.63, necessity=0.67

**Original entry:**

> When reviewing council/multi-reviewer feedback, user wants balanced reasoning that doesn't overweight obvious mechanical fixes (e.g., "vendoring would of course have been fixed"). Focus on substantive issues that require judgment.

**Justification:** This entry captures a specific preference about how to weigh different types of feedback in multi-reviewer scenarios, with a concrete example ('vendoring would of course have been fixed'). It would meaningfully change agent behavior when processing council feedback by guiding what to emphasize versus downplay.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.70, 5.2s)
  - This entry captures a specific preference about how to weigh different types of feedback in multi-reviewer scenarios, with a concrete example ('vendoring would of course have been fixed'). It would meaningfully change agent behavior when processing council feedback by guiding what to emphasize versus downplay.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.2s)
  - The entry provides a specific instruction for handling council/multi‑reviewer feedback, but it is general guidance rather than a concrete fact.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 12.6s)
  - The entry records a specific, actionable preference with a concrete example quote, guiding the agent to prioritize substantive judgment over mechanical fixes during multi-reviewer feedback review.

### `2b7aab650de6b343`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.88, necessity=0.75

**Original entry:**

> Finds hour markers in progress indicators "demoralizing" and prefers MM:SS format over H:MM:SS for elapsed time displays, even when duration exceeds 60 minutes (shows 73:21 instead of 1:13:21).

**Justification:** This entry captures a specific, verifiable UI preference with concrete examples (MM:SS showing 73:21 vs H:MM:SS showing 1:13:21). It would clearly influence agent decisions when designing or selecting progress indicators, making it actionable and worth retaining.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 4.7s)
  - This entry captures a specific, verifiable UI preference with concrete examples (MM:SS showing 73:21 vs H:MM:SS showing 1:13:21). It would clearly influence agent decisions when designing or selecting progress indicators, making it actionable and worth retaining.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.60, 3.2s)
  - Specific observation about display format with concrete example; no obvious defect.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 133.8s)
  - The entry states a specific formatting preference with a concrete example (73:21 vs 1:13:21) and an emotional signal word ('demoralizing'), making it highly retrievable and directly actionable for elapsed time displays. No defects require refinement.

### `3362ba488cf7a744`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.73, necessity=0.70

**Original entry:**

> When selecting LLM models for configurations, user prefers "frontier chat across all providers" — comprehensive coverage of high-quality chat models from multiple providers (Anthropic, OpenAI, Google, DeepSeek, Qwen, etc.).

**Justification:** Entry captures a specific, verifiable preference for LLM model selection strategy with concrete provider examples (Anthropic, OpenAI, Google, DeepSeek, Qwen). This would directly influence which models the agent recommends or configures when asked about LLM selection, making it actionable and necessary.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.80, 4.4s)
  - Entry captures a specific, verifiable preference for LLM model selection strategy with concrete provider examples (Anthropic, OpenAI, Google, DeepSeek, Qwen). This would directly influence which models the agent recommends or configures when asked about LLM selection, making it actionable and necessary.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.7s)
  - The entry records a user preference for frontier chat across multiple providers but is relatively general and not uniquely actionable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.80, 12.1s)
  - The entry includes a direct user quote ('frontier chat across all providers') and names specific providers (Anthropic, OpenAI, Google, DeepSeek, Qwen), making it concrete and easily retrievable. It captures a distinct configuration preference that would directly change model selection recommendations.

### `3adf210f1341a445`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.67, necessity=0.62

**Original entry:**

> When asking about architecture decisions, user wants concrete reusability analysis ("who is consumer #3") rather than speculative abstraction. Values YAGNI principle and practical justification for shared libraries.

**Justification:** Entry captures a specific architectural philosophy (YAGNI, concrete reusability analysis like 'who is consumer #3') that would meaningfully change how the agent responds to architecture questions. Specific enough to be actionable with the concrete example quote, though limited to one session of corroboration.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.75, 4.3s)
  - Entry captures a specific architectural philosophy (YAGNI, concrete reusability analysis like 'who is consumer #3') that would meaningfully change how the agent responds to architecture questions. Specific enough to be actionable with the concrete example quote, though limited to one session of corroboration.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.40, 4.1s)
  - Concrete guidance on handling architecture queries with reusability analysis informs the agent's response style and is not redundant.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.70, 19.3s)
  - The entry includes a precise, quoted heuristic ('who is consumer #3') and a named principle (YAGNI) that directly guide architecture recommendations, making it specific and actionable despite single-session corroboration.

### `41503ab4453d0474`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.67

**Original entry:**

> When reviewing PRs that have been open for a while: wants thorough audit across the codebase, not just quick fixes. Appreciates being asked to "be discerning and fan out your team as necessary" when investigating scope/completeness. Values comprehensive investigation of what the PR might have missed or what main has changed since the merge base.

**Justification:** Entry captures specific, actionable preference about PR review methodology with concrete phrasing ('be discerning and fan out your team') and distinguishes thorough audit from quick fixes. Single-session corroboration is acceptable given the specificity of the behavior described.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.70, 3.1s)
  - Entry captures specific, actionable preference about PR review methodology with concrete phrasing ('be discerning and fan out your team') and distinguishes thorough audit from quick fixes. Single-session corroboration is acceptable given the specificity of the behavior described.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.50, 4.5s)
  - Specific, concrete guidance on PR review depth and team investigation, but not broad enough for system prompt and has no actionable defect.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 14.0s)
  - Entry includes a direct quote and specific, actionable guidance for reviewing stale PRs that would change concrete audit behavior and recommendations if removed. No compressible defects.

### `4c3b54653e36b0a0`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.57, necessity=0.75

**Original entry:**

> When macOS sandbox causes permission errors with local services, user wants commands run without sandbox immediately (no need to ask first).

**Justification:** This entry captures a specific user preference about handling macOS sandbox permission errors - to run commands without the sandbox immediately rather than asking first. It's actionable and would change agent behavior (ask vs. don't ask), though it could be slightly more specific about what 'local services' means.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.85, 3.9s)
  - This entry captures a specific user preference about handling macOS sandbox permission errors - to run commands without the sandbox immediately rather than asking first. It's actionable and would change agent behavior (ask vs. don't ask), though it could be slightly more specific about what 'local services' means.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.6s)
  - General guidance about bypassing sandbox prompts without concrete commands or version specifics.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.90, 16.3s)
  - The entry encodes a specific, behavior-changing user preference for handling macOS sandbox permission errors with local services by acting without prior confirmation. It is useful contextual guidance not covered by generic system instructions.

### `4fe0da7c8b7f985f`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.73

**Original entry:**

> When CodeRabbit suggests a Ruff rule violation, check the project's ruff.toml first — if the rule isn't enabled, the suggestion may be unhelpful. Justify by noting the rule isn't enforced and that fixing creates inconsistency with existing production patterns. Check project lint config before applying style/rule suggestions.

**Justification:** This entry provides specific, actionable guidance about checking ruff.toml configuration before acting on CodeRabbit suggestions, with concrete reasoning about consistency and enforcement. It would change agent behavior in code review scenarios by prompting verification of project lint configuration first.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 3.8s)
  - This entry provides specific, actionable guidance about checking ruff.toml configuration before acting on CodeRabbit suggestions, with concrete reasoning about consistency and enforcement. It would change agent behavior in code review scenarios by prompting verification of project lint configuration first.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.70, 5.9s)
  - Specific, actionable advice about checking ruff.toml before applying Ruff suggestions, meeting concrete criteria.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.70, 20.1s)
  - Specific, actionable workflow guidance tied to named tools (CodeRabbit, Ruff, ruff.toml) that would change how the agent evaluates automated suggestions. No concrete defect warranting refinement.

### `552517c9122f43f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.82

**Original entry:**

> When resolving conflicts between openshell-sdk refactors and upstream changes: prefer extending the SDK to accept new parameters rather than falling back to inline implementations in consumers like openshell-cli. Keep shared logic in the SDK.

**Justification:** Entry provides specific, actionable architectural guidance for resolving conflicts between two named codebases (openshell-sdk and openshell-cli), with a clear principle: extend the SDK rather than duplicate logic in consumers. This would change concrete refactoring decisions when conflicts arise.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.85, 4.3s)
  - Entry provides specific, actionable architectural guidance for resolving conflicts between two named codebases (openshell-sdk and openshell-cli), with a clear principle: extend the SDK rather than duplicate logic in consumers. This would change concrete refactoring decisions when conflicts arise.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.80, 5.7s)
  - The guidance is specific and actionable, with named components, and its removal would affect the agent's conflict‑resolution decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 15.3s)
  - Names specific codebase entities (openshell-sdk, openshell-cli) and prescribes a concrete architectural rule for resolving conflicts that would change agent decisions in this codebase.

### `55a644cd8f6ff2c0`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.68, necessity=0.70

**Original entry:**

> Action-oriented when path is clear. "Don't have time to dawdle" — wants implementation over extended discussion when requirements are understood and context is available. Trusts recommended paths when offered choices during complex operations. Will choose autonomous completion of git workflows when given the choice. But: "If you have any questions/concerns, stop and ask." Values getting it right over getting it done fast.

**Justification:** Contains specific behavioral guidance with direct quotes ('Don't have time to dawdle', 'If you have any questions/concerns, stop and ask') and concrete examples (git workflows, autonomous completion). The tension between speed preference and accuracy priority ('getting it right over getting it done fast') provides actionable guidance that would change agent behavior in ambiguous situations.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 4.5s)
  - Contains specific behavioral guidance with direct quotes ('Don't have time to dawdle', 'If you have any questions/concerns, stop and ask') and concrete examples (git workflows, autonomous completion). The tension between speed preference and accuracy priority ('getting it right over getting it done fast') provides actionable guidance that would change agent behavior in ambiguous situations.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.7s)
  - The entry provides useful, concrete guidance but lacks sufficient specificity for promotion or refinement, and shows no clear defect.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 22.2s)
  - Entry contains specific, verifiable direct quotes and a concrete behavioral example (git workflows) that would change agent decisions on when to proceed autonomously versus pause for clarification. Multi-session corroboration strengthens reliability without needing refinement.

### `59c8938da3dfc3dc`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.70

**Original entry:**

> Prefers all project outputs in consistent locations under REPO_ROOT (e.g., nat-jobs/, eval-out/, optimizer_results/). When adding new output directories, check existing stages first to match the pattern.

**Justification:** The entry identifies a specific, verifiable pattern with concrete examples (nat-jobs/, eval-out/, optimizer_results/) and provides actionable guidance. It would influence where the agent places new output directories, constituting a concrete behavioral change.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.70, 2.8s)
  - The entry identifies a specific, verifiable pattern with concrete examples (nat-jobs/, eval-out/, optimizer_results/) and provides actionable guidance. It would influence where the agent places new output directories, constituting a concrete behavioral change.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.70, 3.1s)
  - The entry gives a clear, concrete rule for output directory placement and would affect the agent's decisions if removed.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.70, 9.8s)
  - The entry provides specific directory examples (nat-jobs/, eval-out/, optimizer_results/) and a clear actionable preference about output organization under REPO_ROOT. It is concrete enough to guide file placement decisions and does not have an obvious defect requiring refinement.

### `5e218e8023703797`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.82, necessity=0.77

**Original entry:**

> When filing bugs, user prefers minimal investigation — capture the repro and symptoms, don't deep-dive into root cause. User said "Don't work too hard, the person fixing it can dig" when asked not to over-investigate code during bug filing.

**Justification:** Contains a specific, actionable workflow preference with a direct quote that would materially change agent behavior when filing bugs. The concrete guidance ('capture the repro and symptoms, don't deep-dive') paired with the user's exact words makes this highly retrievable and behaviorally decisive.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.80, 4.9s)
  - Contains a specific, actionable workflow preference with a direct quote that would materially change agent behavior when filing bugs. The concrete guidance ('capture the repro and symptoms, don't deep-dive') paired with the user's exact words makes this highly retrievable and behaviorally decisive.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.60, 4.1s)
  - Specific, concrete user instruction with a precise quote; no redundancy or vagueness requiring change.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 11.3s)
  - The entry records a specific, quotable user preference about bug-filing behavior that would directly change agent actions if removed; it is concrete and retrievable.

### `6935e3c6fc1098b3`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.62

**Original entry:**

> Has deepagents-cli configured with internal model provider access to many interesting models. Plans to use deepagents as the interface where prompt-tuned models will eventually be exposed. Prefers to do most writing/authoring in Claude Code (Opus-4.7 as best coding model) but run execution in deepagents. Watching token spend — cost-conscious when evaluating multi-model approaches.

**Justification:** Entry contains specific, concrete details about tooling choices (deepagents-cli, Claude Code, Opus-4.7), workflow patterns (authoring vs execution separation), and behavioral constraints (cost-consciousness with token spend). These are actionable facts that would influence agent recommendations and behavior, particularly around model selection and execution environment choices.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.80, 4.0s)
  - Entry contains specific, concrete details about tooling choices (deepagents-cli, Claude Code, Opus-4.7), workflow patterns (authoring vs execution separation), and behavioral constraints (cost-consciousness with token spend). These are actionable facts that would influence agent recommendations and behavior, particularly around model selection and execution environment choices.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.20, 2.7s)
  - The entry provides some specific details but is mainly a high-level plan and not essential for current agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.85, 13.3s)
  - The entry contains specific named tools (deepagents-cli, Claude Code, Opus-4.7), a concrete workflow split (authoring vs. execution), and a measurable preference (cost-consciousness) that would directly change agent recommendations. No concrete defect warrants refinement.

### `7bb47dba9a7be92c`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.58

**Original entry:**

> Prefers proper tool/API usage over guessing: "please use your skills/mcp server (don't just randomly set stuff)" when working with external systems like NVBugs.

**Justification:** The entry contains a specific, verifiable user preference with a direct quote about tool/API usage in the context of NVBugs. While it reinforces generally good practice, the concrete reference to 'skills/mcp server' and the NVBugs system makes it retrievable and actionable for that specific context.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.65, 4.1s)
  - The entry contains a specific, verifiable user preference with a direct quote about tool/API usage in the context of NVBugs. While it reinforces generally good practice, the concrete reference to 'skills/mcp server' and the NVBugs system makes it retrievable and actionable for that specific context.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.50, 6.5s)
  - The entry provides a clear, quoted instruction for proper tool usage, is specific and verifiable, but its scope is limited to external system interactions, not broad enough for system‑prompt promotion.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.60, 21.3s)
  - Contains a specific named system (NVBugs), a distinctive direct quote, and concrete guidance that would influence tool-selection behavior for that system.

### `7d5cfef6e3046c40`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.87

**Original entry:**

> Branch naming convention: `md/<issue-number>-<short-description>`. Prefers `/md` as branch suffix when creating worktrees (not `+md` or other variants).

**Justification:** Highly specific entry documenting a concrete naming convention with precise format (`md/<issue-number>-<short-description>`) and an explicit preference for `/md` over variants like `+md`. This is verifiable user preference that would directly affect branch and worktree creation decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.85, 5.0s)
  - Highly specific entry documenting a concrete naming convention with precise format (`md/<issue-number>-<short-description>`) and an explicit preference for `/md` over variants like `+md`. This is verifiable user preference that would directly affect branch and worktree creation decisions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.90, 4.2s)
  - Specific, verifiable naming guideline that influences branch creation decisions; removal would affect agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.95, necessity=0.85, 21.0s)
  - Specific, verifiable git workflow conventions with exact syntax for branch naming and worktree suffixes; removing it would change concrete branching decisions.

### `8936920730d38570`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.68, necessity=0.73

**Original entry:**

> Uses dotfiles across multiple platforms (macOS, Ubuntu, Debian, Arch, CentOS). Cannot rely on consistent package managers like homebrew. Prefers cross-platform solutions using shell scripts and git clone over package-manager-specific approaches.

**Justification:** This entry contains specific, actionable technical preferences (multiple named platforms, explicit preference for shell scripts and git clone over package managers) that would directly influence how the agent suggests dotfile management solutions. The cross-platform constraint and avoidance of package-manager-specific approaches are concrete decision criteria.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 6.7s)
  - This entry contains specific, actionable technical preferences (multiple named platforms, explicit preference for shell scripts and git clone over package managers) that would directly influence how the agent suggests dotfile management solutions. The cross-platform constraint and avoidance of package-manager-specific approaches are concrete decision criteria.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 2.7s)
  - The entry provides a concise, domain‑specific guideline but lacks concrete commands or version details, making it moderately specific.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 14.2s)
  - Lists specific operating systems and names Homebrew while stating a concrete, actionable preference for shell scripts and git clone that would directly alter environment-setup and dotfile-management recommendations.

### `8f83115f4850f5ef`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.67

**Original entry:**

> Prefers accepting Python tracebacks for rare edge cases (e.g., stat-able but not list-able directories) over defensive TOCTOU permission checks. Values clean error paths for expected failures, tolerates crashes for truly exceptional conditions.

**Justification:** Entry captures a specific technical preference regarding error handling strategy (accepting tracebacks vs TOCTOU checks) with concrete examples (stat-able but not list-able directories). This would guide actual implementation decisions around defensive programming vs fail-fast approaches, making it actionable and worth keeping.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 4.2s)
  - Entry captures a specific technical preference regarding error handling strategy (accepting tracebacks vs TOCTOU checks) with concrete examples (stat-able but not list-able directories). This would guide actual implementation decisions around defensive programming vs fail-fast approaches, making it actionable and worth keeping.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.70, necessity=0.40, 7.2s)
  - The entry provides a clear, concrete preference about error handling with a specific example, but it is not a duplicate or prompt-worthy principle.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 19.4s)
  - Captures a specific, retrievable coding philosophy using precise technical terms (TOCTOU, stat/list, Python tracebacks) with a concrete filesystem example; removing it would change whether the agent writes defensive permission checks or allows exceptions in rare edge cases.

### `aa59a8b701389ed4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.82, necessity=0.68

**Original entry:**

> Has extensive experience writing OpenAPI parsers/utils. Previously worked at Gretel where he used OpenAPI Generator and had to hack internals to get good bindings. This background informs his skepticism about off-the-shelf OpenAPI generators.

**Justification:** Specific, verifiable background information with named entities (OpenAPI Generator, Gretel) that explains the user's domain expertise and informed perspective on tooling choices. This context would meaningfully influence agent recommendations about API tooling and code generation approaches.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 3.1s)
  - Specific, verifiable background information with named entities (OpenAPI Generator, Gretel) that explains the user's domain expertise and informed perspective on tooling choices. This context would meaningfully influence agent recommendations about API tooling and code generation approaches.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 2.8s)
  - Specific mention of Gretel and OpenAPI Generator gives concrete context; removal would not materially alter agent decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 25.3s)
  - Contains specific named entities (Gretel, OpenAPI Generator) and a concrete technical history (hacking internals for bindings) that directly informs tooling recommendations and skepticism. No visible duplicate signal or condensation defect.

### `b287eaa965ce9712`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.65, necessity=0.65

**Original entry:**

> When evaluating review feedback (like coderabbit comments), prefers to "fan out and get multiple opinions" — have multiple independent reviewers assess each point with different lenses, then synthesize their consensus.

**Justification:** The entry describes a specific procedural preference for handling review feedback with concrete method ('fan out and get multiple opinions') and context (coderabbit comments). While it could theoretically apply broadly, the specificity of the multi-reviewer synthesis approach and the named tool make it retrievable and actionable enough to warrant keeping as a personal preference rather than general guidance.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.70, 4.3s)
  - The entry describes a specific procedural preference for handling review feedback with concrete method ('fan out and get multiple opinions') and context (coderabbit comments). While it could theoretically apply broadly, the specificity of the multi-reviewer synthesis approach and the named tool make it retrievable and actionable enough to warrant keeping as a personal preference rather than general guidance.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.4s)
  - Provides a specific strategy for handling review feedback but is a single-observation suggestion that is not uniquely critical.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.75, 17.2s)
  - Entry captures a specific, quotable preference tied to a named tool (CodeRabbit) that would change how the agent processes review feedback; no concrete defect to fix.

### `b6d1a2581c4fd3b3`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.67

**Original entry:**

> For NVIDIA/OpenShell issues/PRs, user prefers casual, conversational, first-person tone over formal third-person language. Example: "I'm thinking we just add the command" rather than "Adding the command is the better fix." Avoid referring to "maintainers" in third person since the user is part of that group — use inclusive language like "we" or direct proposals. Prefers tight, conversational prose over verbose academic/formal writing. User replaced a 4-paragraph feature-request body with ~3 sentences in first-person. Avoid walls of text in issue/PR drafts — show the minimal viable version first.

**Justification:** Entry contains specific, verifiable guidance about tone and style for NVIDIA/OpenShell contributions, with concrete examples (first-person vs third-person, 'we' vs 'maintainers', 3 sentences vs 4 paragraphs). While it affects tone more than outcomes, it would meaningfully change the agent's communication style in a specific context, and the examples make it retrievable and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 4.5s)
  - Entry contains specific, verifiable guidance about tone and style for NVIDIA/OpenShell contributions, with concrete examples (first-person vs third-person, 'we' vs 'maintainers', 3 sentences vs 4 paragraphs). While it affects tone more than outcomes, it would meaningfully change the agent's communication style in a specific context, and the examples make it retrievable and actionable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.50, 10.9s)
  - The entry gives clear, actionable guidance on tone and conciseness for NVIDIA/OpenShell interactions, includes a concrete example, and does not contain a defect that requires refinement.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.75, 22.8s)
  - The entry supplies concrete, verifiable stylistic guidance featuring direct quotes, a named project context, and a specific before/after comparison, making it highly retrievable and actionable. Removing it would likely cause the agent to produce formal, verbose, third-person drafts for NVIDIA/OpenShell contributions, directly contradicting the user's demonstrated preferences.

### `bd67f4f43e9c9694`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.65

**Original entry:**

> Identity-shaped prompts ("you are a deliberate collaborator who...") belong at the very top of CLAUDE.md/AGENTS.md, not buried in bullet lists. They set the lens through which all other rules are read. Placement matters: framing at the top establishes character; the same content as rule #7 just gets weighted alongside everything else.

**Justification:** Specific, actionable guidance about document structure with concrete reasoning about why placement matters (framing vs. weighted rule). The distinction between 'top of file' vs 'rule #7' is verifiable and would change concrete decisions about where to place identity prompts in configuration files.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 4.0s)
  - Specific, actionable guidance about document structure with concrete reasoning about why placement matters (framing vs. weighted rule). The distinction between 'top of file' vs 'rule #7' is verifiable and would change concrete decisions about where to place identity prompts in configuration files.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.3s)
  - Provides specific, actionable guidance about placement of identity-shaped prompts; removal would affect tone but not a concrete decision.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 28.5s)
  - The entry names specific files (CLAUDE.md/AGENTS.md), includes a precise example quote, and gives concrete structural guidance that would directly change how the agent orders content when drafting agent instructions.

### `c39e32157fe70312`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.95, necessity=0.65

**Original entry:**

> Assigns Tyler Bray (GitHub: tylersbray, email: tbray@nvidia.com) as reviewer for CLI and agent-related work on NeMo Platform.

**Justification:** Highly specific entry with named entities (Tyler Bray), contact information (GitHub handle, email), and clear scope (CLI and agent-related work on NeMo Platform). This would directly influence reviewer assignment decisions for relevant pull requests.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.85, 3.5s)
  - Highly specific entry with named entities (Tyler Bray), contact information (GitHub handle, email), and clear scope (CLI and agent-related work on NeMo Platform). This would directly influence reviewer assignment decisions for relevant pull requests.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.20, 3.6s)
  - The entry provides a clear, named reviewer assignment with verifiable identifiers, making it both specific and useful.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=1.00, necessity=0.90, 11.8s)
  - The entry is a concrete operational fact with named entities, contact details, and a precise scope; removing it would directly change reviewer-assignment decisions for CLI and agent-related NeMo work.

### `c793c6c82dacdb5e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.92, necessity=0.75

**Original entry:**

> Uses marker file pattern for machine-specific config: `touch ~/.config/zsh/.work` on work machines, then conditionally source work config with `[[ -f $ZDOTDIR/.work ]] && source ...`. Prefers this over hostname matching or untracked machine-local files because it's explicit and visible in the repo flow.

**Justification:** Highly specific technical pattern with concrete implementation details (exact file path ~/.config/zsh/.work, specific conditional syntax). Documents a deliberate architectural decision with clear rationale, making it actionable and retrievable for future shell configuration work.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.85, 3.8s)
  - Highly specific technical pattern with concrete implementation details (exact file path ~/.config/zsh/.work, specific conditional syntax). Documents a deliberate architectural decision with clear rationale, making it actionable and retrievable for future shell configuration work.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.50, 3.6s)
  - The entry is a concrete, specific tip about using a marker file for Zsh work config, but it addresses a niche technique rather than a general behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 15.1s)
  - The entry records a specific, verifiable technical preference with exact commands, file paths, and rationale that would concretely change agent recommendations when managing machine-specific shell configuration.

### `cc2763c3925d2b64`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.60

**Original entry:**

> Max Dubrinsky (GitHub: maxdubrinsky) is a maintainer of NVIDIA/OpenShell. Has personal connections to NVIDIA/OpenShell maintainers but contributes via fork (not direct push access).

**Justification:** Highly specific entry with named entities (Max Dubrinsky, GitHub handle, NVIDIA/OpenShell repository) and concrete technical details about contribution patterns and access permissions. This information would affect how the agent interacts with or reasons about this maintainer's role and workflow, particularly regarding PR processes and repository access.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.95, necessity=0.75, 4.2s)
  - Highly specific entry with named entities (Max Dubrinsky, GitHub handle, NVIDIA/OpenShell repository) and concrete technical details about contribution patterns and access permissions. This information would affect how the agent interacts with or reasons about this maintainer's role and workflow, particularly regarding PR processes and repository access.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.85, necessity=0.35, 2.3s)
  - The entry is a concrete, specific fact about Max Dubrinsky, but its influence on agent decisions is limited, so it does not drive notable behavior changes.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.70, 13.7s)
  - Specific, verifiable fact about a named individual's role and access model for a specific repository; removing it would alter agent recommendations regarding collaboration paths.

### `d78b6a695264b8f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.83, necessity=0.63

**Original entry:**

> Prefers dropping features entirely when their value proposition weakens rather than maintaining stopgap solutions or adding CLI complexity to preserve them. Applies "re-evaluate dependent features" principle consistently. Example: removed `--model` flag from usage CLI because richer artifact data (trajectory.json) will eventually provide authoritative model identity, avoiding two-sources-of-truth problems.

**Justification:** Entry contains a specific, concrete example (removal of --model flag from usage CLI with detailed reasoning about trajectory.json and two-sources-of-truth) that demonstrates a clear design principle. The corroboration across 2 sessions and the specific example make this actionable and retrievable enough to influence future feature decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.80, 5.9s)
  - Entry contains a specific, concrete example (removal of --model flag from usage CLI with detailed reasoning about trajectory.json and two-sources-of-truth) that demonstrates a clear design principle. The corroboration across 2 sessions and the specific example make this actionable and retrievable enough to influence future feature decisions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.30, 6.8s)
  - Specific example of removing the `--model` flag and using trajectory.json, but the behavior is not uniquely essential.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.80, 10.3s)
  - The entry names a specific design principle and grounds it with concrete CLI flags, artifact filenames, and reasoning that would directly shape future feature-removal decisions.

### `d79b57fd26ea50c1`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.63

**Original entry:**

> Prefers critical evaluation of automated suggestions (CodeRabbit, linters) — willing to reject suggestions that don't align with actual project config or that introduce unnecessary complexity, even when they come from automated tools.

**Justification:** Entry captures a specific behavioral preference about evaluating automated tool suggestions (CodeRabbit, linters) with concrete examples of rejection criteria. While it could be slightly more specific with actual examples, it provides actionable guidance that would influence agent behavior when responding to automated tooling recommendations.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.60, necessity=0.70, 3.9s)
  - Entry captures a specific behavioral preference about evaluating automated tool suggestions (CodeRabbit, linters) with concrete examples of rejection criteria. While it could be slightly more specific with actual examples, it provides actionable guidance that would influence agent behavior when responding to automated tooling recommendations.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.60, 7.1s)
  - Specific preference about rejecting automated suggestions, concrete enough to retain.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.60, 14.5s)
  - Names the specific tool CodeRabbit and captures a distinct, non-obvious preference to critically evaluate rather than defer to automated suggestions, which can directly influence whether the agent accepts or rejects linter and AI-generated recommendations.

### `da5498e4affca2a0`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.72

**Original entry:**

> Expects verification of claims before making breaking changes. Will ask "can you make sure of that" and wants downstream impact checked (e.g., grepping for field usage before removing from public schema). 
> 
> ## Technical preferences — architecture and design
> 
> Data model evolution: prefer to omit fields until there's a concrete consumer. "Easier to add a field than remove one." Keep surface area small in initial implementations rather than pre-emptively adding fields that might be useful later.

**Justification:** Contains specific behavioral patterns with a direct quote ('can you make sure of that') and concrete examples (grepping for field usage, schema changes). The data model evolution principle ('Easier to add a field than remove one') is specific enough to guide decisions about API surface area and will change how the agent approaches design choices.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 4.1s)
  - Contains specific behavioral patterns with a direct quote ('can you make sure of that') and concrete examples (grepping for field usage, schema changes). The data model evolution principle ('Easier to add a field than remove one') is specific enough to guide decisions about API surface area and will change how the agent approaches design choices.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.0s)
  - General design guideline; specific but not concrete, and removing it would not alter concrete agent decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.85, 14.8s)
  - The entry includes precise user quotes ('can you make sure of that', 'Easier to add a field than remove one') and a concrete verification ritual (grepping for field usage) that make it specific and actionable. Removing it would change concrete agent behavior when proposing breaking changes or designing schemas.

### `e37c64430111426a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.88, necessity=0.83

**Original entry:**

> When drafting technical content for the user to share with others (team messages, announcements), provide plain editable text rather than trying to match their voice. User explicitly asked for "a couple lines of text that I can edit to sound like me."

**Justification:** This entry contains a specific, verifiable preference with a direct quote from the user. It describes a concrete behavioral change (provide plain editable text rather than matching voice) that would affect agent output for technical drafts. The quote provides strong evidence of user intent.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.90, 3.7s)
  - This entry contains a specific, verifiable preference with a direct quote from the user. It describes a concrete behavioral change (provide plain editable text rather than matching voice) that would affect agent output for technical drafts. The quote provides strong evidence of user intent.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.70, 6.7s)
  - Specific request for editable plain text to match user voice; removing it would likely alter the agent's tone when drafting shared technical content.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 19.3s)
  - Contains a specific drafting preference backed by a direct user quote, clearly instructing the agent to provide plain editable text instead of voice-matched prose for shareable communications.

### `e85750de7b7fc4fa`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.68, necessity=0.63

**Original entry:**

> Prefers canonical specifications to live in language-agnostic artifacts (reviewer prompts, synthesis templates, shell scripts) with each runtime (Claude Code, deepagents-cli) wrapping them with runtime-specific dispatch glue. Reason: keeps substance in one place and isolates runtime quirks, avoiding drift when maintaining parallel implementations in different systems.

**Justification:** The entry captures a specific architectural preference with concrete examples (reviewer prompts, synthesis templates, shell scripts) and named runtimes (Claude Code, deepagents-cli). It would directly influence design decisions about where to place specifications versus runtime-specific code, making it actionable and retrievable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.80, 3.8s)
  - The entry captures a specific architectural preference with concrete examples (reviewer prompts, synthesis templates, shell scripts) and named runtimes (Claude Code, deepagents-cli). It would directly influence design decisions about where to place specifications versus runtime-specific code, making it actionable and retrievable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.40, 4.3s)
  - The entry offers a clear but general principle without concrete commands, making it moderately useful but not essential for agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 16.7s)
  - The entry contains named runtimes (Claude Code, deepagents-cli) and concrete artifact types, making it a specific, retrievable preference that would directly influence how the agent structures cross-runtime specifications.

### `eb06022f0c6cec7a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.65, necessity=0.57

**Original entry:**

> When blocked on unmerged dependencies (PRs, branches), prefers to check out the branch in a worktree and start iterating rather than waiting. Wants action over planning delays.

**Justification:** Entry describes a specific behavioral preference (using worktrees to unblock on dependencies) with concrete context. While it could theoretically apply broadly, the specific strategy of checking out branches in worktrees rather than waiting is actionable guidance that would influence agent decisions when encountering blocked dependencies.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.70, 4.7s)
  - Entry describes a specific behavioral preference (using worktrees to unblock on dependencies) with concrete context. While it could theoretically apply broadly, the specific strategy of checking out branches in worktrees rather than waiting is actionable guidance that would influence agent decisions when encountering blocked dependencies.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.55, necessity=0.20, 3.6s)
  - The entry provides a clear, specific guideline but is not critical for core decision making and contains no defects requiring refinement.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 15.6s)
  - It records a specific, retrievable workflow preference—using git worktrees when blocked on unmerged dependencies—that would change concrete agent recommendations in relevant scenarios. The signal is concise and user-specific rather than generic.

### `ef4733acc96c530e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.53

**Original entry:**

> Manages dotfiles with GNU Stow for both work and personal machines. Spins up new machines rarely. Prefers declarative, in-repo configuration over implicit machine-local setup. Values shell startup performance, especially in Python repos.

**Justification:** Entry contains specific, actionable preferences (GNU Stow for dotfiles, declarative in-repo config, shell startup performance concerns in Python repos) that would influence agent recommendations around development environment setup and tooling choices. Concrete enough to be retrievable when discussing configuration management or performance optimization.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.70, 5.6s)
  - Entry contains specific, actionable preferences (GNU Stow for dotfiles, declarative in-repo config, shell startup performance concerns in Python repos) that would influence agent recommendations around development environment setup and tooling choices. Concrete enough to be retrievable when discussing configuration management or performance optimization.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.20, 4.8s)
  - Moderate quality, low necessity; no concrete defect requiring refinement.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 11.4s)
  - It identifies a specific workflow tool (GNU Stow) and concrete preferences (declarative in-repo config, shell startup in Python repos) that would directly alter setup recommendations. The entry is specific and retrievable without being overly broad or vague.

### `f06b7cf3228f3384`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.63, necessity=0.67

**Original entry:**

> When evaluating architectural decisions or migration costs, prefers concrete data: LOC counts, file counts, time estimates broken down by work area. Wants "how many can we delete?" answered with measurements, not speculation.

**Justification:** Entry captures a specific, actionable preference for quantitative data (LOC counts, file counts, time estimates) over speculation in architectural decisions. While it could apply to many engineers, the specificity of the requested metrics and the direct quote make it retrievable and behaviorally useful for an agent responding to migration or refactoring questions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.70, 3.3s)
  - Entry captures a specific, actionable preference for quantitative data (LOC counts, file counts, time estimates) over speculation in architectural decisions. While it could apply to many engineers, the specificity of the requested metrics and the direct quote make it retrievable and behaviorally useful for an agent responding to migration or refactoring questions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.60, 3.6s)
  - Specific but lacks named entities and precise metrics, making it moderately concrete and generally useful.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 16.2s)
  - Entry provides a specific, behavioral preference for metrics-driven architectural and migration analysis that would concretely shape agent outputs if absent; concise and not redundant with typical system prompts.

### `f4a359b3859edf3d`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.65

**Original entry:**

> Prefers Python-style pseudocode over LaTeX/mathematical notation for expressing formulas and algorithms. "Prefer python to math since it's been 15 years since I've used LaTeX."

**Justification:** This entry contains a specific, actionable preference with a direct quote explaining the rationale. It will concretely change how the agent formats technical content (Python pseudocode vs LaTeX). The corroboration level is low but the specificity and direct quote make it verifiable and retrievable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.85, 3.9s)
  - This entry contains a specific, actionable preference with a direct quote explaining the rationale. It will concretely change how the agent formats technical content (Python pseudocode vs LaTeX). The corroboration level is low but the specificity and direct quote make it verifiable and retrievable.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.30, 4.5s)
  - The entry gives a clear personal stylistic preference expressed as a quote but does not provide a concrete instruction that would alter the agent's decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.80, 10.4s)
  - The entry captures a concrete, verifiable formatting preference with a direct quote, and removing it would cause the agent to default to mathematical notation instead of Python pseudocode for algorithms.

### `fa248bb8026a7f3e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.55, necessity=0.53

**Original entry:**

> Prefers interactive, incremental onboarding when exploring new codebases. Wants information "fed" in chunks rather than large reports. Starts exploration by examining types and contracts first to understand how data is structured and used.

**Justification:** Entry describes a specific, actionable preference pattern for codebase exploration (incremental chunks, types-first approach) that would influence how the agent presents information. While only seen once, the behavior is concrete enough to guide future interactions differently than a generic 'be helpful' instruction would.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.65, necessity=0.70, 5.5s)
  - Entry describes a specific, actionable preference pattern for codebase exploration (incremental chunks, types-first approach) that would influence how the agent presents information. While only seen once, the behavior is concrete enough to guide future interactions differently than a generic 'be helpful' instruction would.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.30, 4.2s)
  - The entry conveys a useful general guidance about onboarding style but is vague and not tied to concrete decisions; removing it would not materially affect agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.60, 36.8s)
  - Captures a concrete, actionable user preference for how to present new codebase information (chunked, interactive) and where to begin exploration (types/contracts). While it lacks named entities or direct quotes, it is specific enough to change agent behavior.

### `fb1a3473bef6711a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.47

**Original entry:**

> Treats RFC review feedback as peer input to evaluate, not gospel: "view it through the lens of a peer with whom you might not agree on everything."

**Justification:** The entry captures a specific attitude toward RFC feedback with a direct quote, making it retrievable. However, with only single-session corroboration and representing general professional judgment rather than a concrete decision point, its necessity is moderate—it would influence tone and approach but not change specific outcomes.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.65, necessity=0.40, 3.8s)
  - The entry captures a specific attitude toward RFC feedback with a direct quote, making it retrievable. However, with only single-session corroboration and representing general professional judgment rather than a concrete decision point, its necessity is moderate—it would influence tone and approach but not change specific outcomes.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.90, necessity=0.50, 7.4s)
  - Specific guidance with a precise quote, but only a single observation and not broad enough to be promoted to the system prompt.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.50, 18.7s)
  - Retrievable due to a precise direct quote and specific context (RFC review feedback). Documents a user-specific stance that could shift tone during feedback evaluation, making it worth preserving despite partial overlap with general critical-thinking defaults.

### `fe3b38f60055f95f`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.68

**Original entry:**

> When reviewing PRs, user wants to distinguish between issues caused by the PR (net-new) vs issues that were pre-existing on main. Asked explicitly: "Are there any issues created by this PR or are these problems present on the current implementation?"

**Justification:** This entry captures a specific, verifiable user preference about PR review methodology with a direct quote showing the exact distinction the user wants to make. It would meaningfully change agent behavior during code reviews by prompting it to explicitly separate net-new issues from pre-existing ones, which is not a default system behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.85, necessity=0.75, 4.8s)
  - This entry captures a specific, verifiable user preference about PR review methodology with a direct quote showing the exact distinction the user wants to make. It would meaningfully change agent behavior during code reviews by prompting it to explicitly separate net-new issues from pre-existing ones, which is not a default system behavior.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 6.0s)
  - The entry offers useful guidance on distinguishing PR‑introduced issues, but it is a general instruction without concrete entities or facts, and its removal would affect the specific question asked without being duplicated elsewhere.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.80, 20.7s)
  - The entry is anchored by a direct quote and describes a specific, actionable preference for PR reviews that would change how the agent classifies and reports issues.

### `ffccf834cf1224a4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.60

**Original entry:**

> Prefers minimal, deliberate solutions over adding configuration mechanisms — "don't want to add that mechanism" when rejecting a sidecar config approach. Favors starting small with explicit overrides and iterating from there.

**Justification:** Entry contains a specific quoted phrase ('don't want to add that mechanism') and concrete behavioral preference (rejecting sidecar config, favoring explicit overrides). Specific enough to guide architectural decisions around configuration approaches, though single-session corroboration means it could benefit from additional observations.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.70, 4.2s)
  - Entry contains a specific quoted phrase ('don't want to add that mechanism') and concrete behavioral preference (rejecting sidecar config, favoring explicit overrides). Specific enough to guide architectural decisions around configuration approaches, though single-session corroboration means it could benefit from additional observations.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.75, necessity=0.50, 6.3s)
  - The entry expresses a clear, observed preference but is not broad enough for a system prompt and contains no actionable defect.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.60, 22.8s)
  - The entry includes a direct quote and a specific technical context (rejecting a sidecar config approach) that make it concrete and retrievable, capturing a distinct architectural preference beyond generic minimalism.

### `07b56fbdcc233913`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.60

**Original entry:**

> Prefers distilled, compact memories over verbose ones. When memories accumulate specific implementation details (file paths, class names, line numbers), wants them trimmed to essential decisions/principles and pointers to canonical sources. Asks for memory cleanup proactively to reduce context load.

**Justification:** The entry specifies a clear preference for distilled memories and proactive cleanup, but it is general guidance without concrete specifics, so it is moderately high quality and of low necessity.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 4.9s)
  - This describes a meta-preference about how the agent should manage its own memory system—preferring compact over verbose entries and proactively trimming implementation details. This is high-value operational guidance that should apply to all memory operations, making it better suited for the system prompt than retrieval-based memory.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.20, 4.8s)
  - The entry specifies a clear preference for distilled memories and proactive cleanup, but it is general guidance without concrete specifics, so it is moderately high quality and of low necessity.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 22.2s)
  - The entry provides concrete, actionable guidance on memory style (trimming file paths, class names, and line numbers to essential principles/pointers) and on proactive memory cleanup, which would directly change the agent's memory-writing and consolidation behavior if removed.

### `0cf94a88d9bf510e`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.73

**Original entry:**

> Prefers deep "under the hood" explanations that connect abstract mechanisms to familiar experiences ("you've used this without realizing"). Appreciates bridging theory to practice rather than surface-level how-to guides. 
> 
> ## Time estimates and planning
> 
> Dislikes time estimates in agentic development contexts: "I don't care about estimates and they only serve to muddy the waters. We're all doing agentic development, so engineering days means very little." "Estimates muddy the waters." Considers them subjective and unlikely to influence decisions unless something will take a year. Prefers categorical scales (none/small/non-trivial) over specific durations. What matters is whether a slice depends on hard design calls, not calendar-day framing.

**Justification:** The entry provides concrete preferences with quoted directives that are specific and verifiable, but it is not broad enough for a system‑level prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.80, 4.2s)
  - The entry combines two distinct topics (explanation style preferences and time estimation preferences) that should be separated. Each topic is specific and actionable, but they are unrelated communication preferences that would be better retrieved independently.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.80, necessity=0.60, 4.0s)
  - The entry provides concrete preferences with quoted directives that are specific and verifiable, but it is not broad enough for a system‑level prompt.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 31.9s)
  - Contains direct quotes and specific, actionable guidance that would change concrete agent decisions around providing time estimates and choosing explanation depth. Although it covers two related preference areas, both concern communication style and are appropriately consolidated.

### `1afa1e62e8955f70`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.60

**Original entry:**

> Prefers interactive sessions with think-out-loud reasoning. Wants to be included in the reasoning process, not just presented with conclusions. Values collaborative decision-making over being handed finished answers.

**Justification:** General but useful guidance on interaction style; not a concrete directive.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 4.5s)
  - This entry describes a fundamental interaction preference that should shape every agent response: showing reasoning process and involving the user collaboratively. This is broadly applicable guidance that belongs in the system prompt rather than being conditionally retrieved.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.4s)
  - General but useful guidance on interaction style; not a concrete directive.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.50, 20.6s)
  - A clear, actionable user preference that distinguishes this user from those wanting terse, conclusion-only responses. It lacks named entities or quotes, so quality is moderate, but it meaningfully guides interaction style.

### `2d5005c7ea8c6a13`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.77

**Original entry:**

> Values critical thinking and evidence-based pushback. "If there is anything said above that you take issue with, please push back. Think critically!" Expects substantive engagement over deference. When presenting architectural proposals or recommendations, wants validation with concrete evidence from codebase/docs and grounded reasoning. Will explicitly ask "push back on this read and verify this claim" before bringing ideas to coworkers.

**Justification:** The entry gives clear guidance on critical thinking and evidence-based pushback but remains somewhat general; removing it would affect tone more than cause a concrete behavioral shift.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 4.3s)
  - This entry defines a fundamental interaction pattern with high corroboration (6 sessions) that should apply to all interactions: the user wants critical thinking, evidence-based validation, and substantive pushback rather than deference. This is a core behavioral expectation that belongs in the system prompt rather than being retrieved conditionally.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 8.1s)
  - The entry gives clear guidance on critical thinking and evidence-based pushback but remains somewhat general; removing it would affect tone more than cause a concrete behavioral shift.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 19.1s)
  - High-corroboration entry containing direct quotes and specific behavioral guidance around critical pushback and evidence-based validation; removing it would risk defaulting to deference rather than substantive engagement.

### `33490df8bf4790b5`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.70, necessity=0.83

**Original entry:**

> For bug reports, user wants diagnostic findings without fix recommendations ("avoid making fix recommendations since this is a bug"). Keep bug issues descriptive of the problem, not prescriptive of the solution.

**Justification:** This is a specific, actionable user preference about bug report format with a direct quote. It would meaningfully change agent behavior by preventing fix recommendations in bug contexts, which is not a default assumption.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.80, necessity=0.90, 4.0s)
  - This is a specific, actionable user preference about bug report format with a direct quote. It would meaningfully change agent behavior by preventing fix recommendations in bug contexts, which is not a default assumption.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.50, necessity=0.80, 5.5s)
  - The guidance is specific enough for bug‑report handling but is a general principle that would be useful as a permanent system rule.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.80, 8.8s)
  - The entry includes a direct user quote and a precise, domain-specific constraint that overrides default helpful behavior; removing it would cause the agent to inappropriately offer fix recommendations when reporting bugs.

### `3a4f5eb974a14f65`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.82

**Original entry:**

> Challenges assumptions and expects evidence-based verification. When told something about code or workflow (e.g., "the rebase didn't change anything"), user will question it ("That cannot be right") and expects concrete proof (git range-diff, patch-ids, byte-level diffs) rather than accepting claims at face value. Provide verifiable evidence, not assertions.

**Justification:** Entry captures a specific interaction pattern with concrete examples (git range-diff, patch-ids, byte-level diffs) and actionable guidance. While slightly general in tone, the named verification methods and quoted skepticism ('That cannot be right') make it retrievable and behaviorally significant—agent should proactively provide evidence rather than assertions when working with this user.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.70, necessity=0.80, 4.5s)
  - Entry captures a specific interaction pattern with concrete examples (git range-diff, patch-ids, byte-level diffs) and actionable guidance. While slightly general in tone, the named verification methods and quoted skepticism ('That cannot be right') make it retrievable and behaviorally significant—agent should proactively provide evidence rather than assertions when working with this user.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.60, necessity=0.80, 8.7s)
  - The instruction is broadly applicable and encourages evidence‑based verification, but it is somewhat general rather than a concrete command.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.85, 14.2s)
  - Entry captures a specific, actionable user preference with precise examples, direct quotes, and named verification tools (git range-diff, patch-ids, byte-level diffs) that would concretely change how the agent substantiates technical claims.

### `3b633c1de36c5c76`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.67

**Original entry:**

> When user provides explicit design decisions or answers to questions, proceed with those answers rather than continuing extensive exploration. Values efficiency when decisions are already made. When scoping work, prefers to clarify intent if the request is ambiguous rather than having agent guess. Often refines scope or clarifies intent rather than picking from menus. Prefers narrow, well-scoped iterations over committing to large sweeps upfront.

**Justification:** The entry offers useful but somewhat vague guidance; it is not concrete enough for promotion and lacks a clear defect warranting refinement.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.60, necessity=0.70, 5.4s)
  - This entry describes a consistent interaction pattern observed across 3 sessions: preferring explicit decisions over exploration, clarifying ambiguity, and favoring narrow iterations. These are broad behavioral preferences that should guide all agent interactions rather than being retrieved contextually.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 9.2s)
  - The entry offers useful but somewhat vague guidance; it is not concrete enough for promotion and lacks a clear defect warranting refinement.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.80, 26.3s)
  - Multi-session corroborated preference describing a distinct working style around decision handling, ambiguity clarification, and iteration scope. It is specific enough to materially change agent behavior and lacks a concrete defect requiring refinement.

### `44321d2304e81f90`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.57

**Original entry:**

> Comfortable with "YOLO" approaches for small changes vs. rigid testing. Pragmatic about testing — willing to YOLO small changes and defer test infrastructure until it's genuinely needed. 
> 
> ## Named people, tools, and projects
> 
> User is Max Dubrinsky (mdubrinsky@nvidia.com, GitHub: maxdubrinsky).

**Justification:** The entry offers generic pragmatic guidance with limited specificity and does not drive a concrete behavior change.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.60, 3.4s)
  - The entry combines two distinct topics: (1) pragmatic testing philosophy and (2) user identity information. These should be separated as they serve different retrieval purposes and have different validity scopes.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.0s)
  - The entry offers generic pragmatic guidance with limited specificity and does not drive a concrete behavior change.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.60, 37.4s)
  - The entry captures a specific, non-default preference about test rigor that would change concrete agent recommendations for small changes. While it is general guidance rather than a hard fact, the 'YOLO' framing makes it distinct and retrievable.

### `5312e5c7aaf8d182`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.57, necessity=0.73

**Original entry:**

> Evaluates code review findings critically with justification. Expects "FIX" vs "DON'T FIX" decisions with clear reasoning, not blind acceptance of all suggestions. Uses cost/benefit analysis for proposed changes. Expects critical evaluation with justification for every decision — prefers seeing reasoning for both what gets applied and what gets rejected.

**Justification:** Provides useful general guidance on critical code‑review evaluation but lacks concrete specifics such as named entities or precise commands, so it should remain a memory entry.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.90, 4.8s)
  - This describes a fundamental approach to code review evaluation that should apply consistently across all sessions. The principle of critical evaluation with cost/benefit analysis and explicit FIX/DON'T FIX reasoning is a core workflow preference that belongs in the system prompt rather than being retrieved selectively.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.70, 5.7s)
  - Provides useful general guidance on critical code‑review evaluation but lacks concrete specifics such as named entities or precise commands, so it should remain a memory entry.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.60, 20.9s)
  - This is a corroborated user preference that meaningfully shapes how the agent structures code review feedback, but it remains general behavioral guidance without named entities or direct quotes. There is no concrete defect to justify refinement.

### `81d7a0d390ee897d`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.85, necessity=0.80

**Original entry:**

> Uses @filename syntax to reference files (e.g., "@RFC-migrate-off-stainless.md"). When user mentions a document by name or reference, ask for location/path rather than searching blindly.

**Justification:** The entry captures a specific behavioral pattern (@filename syntax) and a concrete interaction strategy (ask for location rather than searching blindly). This is actionable guidance that would change agent behavior in file-reference scenarios.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `keep` (quality=0.75, necessity=0.70, 3.2s)
  - The entry captures a specific behavioral pattern (@filename syntax) and a concrete interaction strategy (ask for location rather than searching blindly). This is actionable guidance that would change agent behavior in file-reference scenarios.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `promote_to_prompt` (quality=0.90, necessity=0.80, 5.3s)
  - Specific guidance on @filename handling that would affect agent behavior if removed, and is broadly applicable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.90, 12.2s)
  - The entry records a concrete, actionable user preference with a precise example (@RFC-migrate-off-stainless.md) and a clear behavioral rule; removing it would change whether the agent asks for a file path or searches blindly.

### `84d3ccff688a9114`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.68

**Original entry:**

> Tighten text in prompts/instructions — "more text is sometimes less impactful." Values distilled, essential content over verbose explanations. Prefers condensed, to-the-point communication. "Don't try to explain the world" when asking for summaries — wants informative but focused content.

**Justification:** The entry offers general guidance on concise communication but lacks concrete specifics and would not dramatically alter behavior if removed.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 5.6s)
  - This entry captures a clear, actionable communication preference with concrete guidance ('don't try to explain the world', favor condensed over verbose) that applies broadly across interactions. The 3-session corroboration and behavioral impact (changing how the agent structures all responses) make it a candidate for the system prompt rather than retrieval-based memory.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 3.8s)
  - The entry offers general guidance on concise communication but lacks concrete specifics and would not dramatically alter behavior if removed.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.75, 18.9s)
  - The entry includes precise user quotes and a clear, actionable preference about conciseness in summaries and instructions that is corroborated across three sessions. Removing it would change concrete output decisions, not merely tone.

### `9cd72c55fda5ded2`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.60, necessity=0.70

**Original entry:**

> Prefers deliberate investigation over trial-and-error. When introducing a new tool, wants agent to "brush up" on how to use it before firing off commands. Values understanding complexity/scope before implementing. Slow at architectural boundaries; iteration speed never substitutes for thinking.

**Justification:** The entry is a clear guideline but remains a general principle rather than a concrete rule; removing it would shift tone without altering concrete decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.60, necessity=0.80, 4.8s)
  - This entry captures a consistent working style preference observed across 4 sessions: preferring understanding over trial-and-error, requiring upfront tool research, and valuing architectural thinking. While somewhat general, it would meaningfully change agent behavior (pacing, when to research vs. act). The broad applicability and high corroboration suggest it belongs in the system prompt rather than retrieval-dependent memory.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.3s)
  - The entry is a clear guideline but remains a general principle rather than a concrete rule; removing it would shift tone without altering concrete decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.70, necessity=0.80, 23.6s)
  - The entry captures a specific, corroborated user workflow preference—favoring deliberate investigation over trial-and-error and reading up on new tools before use—that would materially change agent behavior if removed, and it contains no defect requiring refinement.

### `a2904a90b343a7bf`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.72, necessity=0.77

**Original entry:**

> Strongly dislikes adding imperatives/directives in front of existing DO/DO NOT blocks in AGENTS.md. "If an agent isn't obeying [the DO/DO NOT block], then I don't know what will." Don't stack ceremony in front of existing instructions. 
> 
> ## Communication style and output preferences
> 
> Prefers terse output, ≲ one terminal screen. Wants response lengths kept shorter — feedback that output "just longer than my screen" was too long.

**Justification:** Specific user preference on response length, but not a concrete fact; removing it would only affect tone, not critical decisions.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.80, necessity=0.90, 5.0s)
  - The entry combines two distinct topics: (1) specific guidance about not adding imperatives before DO/DO NOT blocks in AGENTS.md, and (2) general output length preferences. These should be separated as they address different concerns and would be retrieved for different contexts.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 5.3s)
  - Specific user preference on response length, but not a concrete fact; removing it would only affect tone, not critical decisions.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.85, necessity=0.90, 36.6s)
  - Specific, corroborated preference with named file (AGENTS.md), direct quotes, and a quantified length constraint; removing it would alter concrete editing and output-formatting decisions.

### `bb0d40fa9755379b`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.88, necessity=0.90

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

**Justification:** Specific, actionable preferences with concrete examples; removing would alter agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.85, 5.2s)
  - The entry combines three distinct topics (refactoring analysis preferences, Linear URL rewriting, git workflow) that should be separated. This is a structural defect making retrieval less precise.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=1.00, necessity=0.90, 8.2s)
  - Specific, actionable preferences with concrete examples; removing would alter agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.90, necessity=0.95, 45.1s)
  - Contains specific, behavior-changing directives: exact URL rewrite rules for Linear with named output contexts, direct quotes on branching preferences, and precise guidance on refactoring trade-offs. Well-structured with clear headers making each section retrievable despite spanning multiple topics.

### `ccd19a2fa2414c49`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.47, necessity=0.40

**Original entry:**

> Values consistency across the codebase — when fixing bugs or implementing features, prefers to match broader codebase patterns rather than keeping one-off exceptions ("do whatever is most consistent").

**Justification:** Provides general guidance on consistency but lacks specific identifiers and would not materially affect behavior if removed.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `drop` (quality=0.30, necessity=0.10, 4.8s)
  - This entry describes a general software engineering best practice (code consistency) that any competent developer would follow by default. It provides no concrete, actionable information that would change agent behavior beyond what is already expected in basic engineering discipline.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.2s)
  - Provides general guidance on consistency but lacks specific identifiers and would not materially affect behavior if removed.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.60, 20.1s)
  - The entry captures a distinct, non-universal user preference for global codebase consistency over local one-off exceptions, anchored by a direct quote that aids retrieval. It is specific enough to alter concrete implementation decisions and does not merely restate obvious or generic guidance.

### `cd59e47469ff3772`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.43, necessity=0.27

**Original entry:**

> Thinks architecturally before implementing — considers whether ideas are "in step with project direction" and evaluates second-order implications. Prefers to ground discussions in actual code before reasoning about design.

**Justification:** The entry describes a general architectural behavior without concrete specifics, making it moderately useful but not essential.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `drop` (quality=0.30, necessity=0.10, 3.8s)
  - This entry describes generic software engineering best practices ('thinks architecturally', 'considers implications', 'prefers grounding in code') that could apply to any thoughtful developer. It provides no concrete, retrievable guidance that would change agent behavior in specific situations.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.20, 5.4s)
  - The entry describes a general architectural behavior without concrete specifics, making it moderately useful but not essential.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.50, 30.5s)
  - Captures a distinct user workflow preference—balancing architectural thinking with code-first design discussion—that would change agent behavior, though it is a generalized inference lacking concrete examples or named entities.

### `daa44d66c1c0e810`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.78

**Original entry:**

> When user explicitly asks for a specific tool or approach (e.g., "use tmux" not just "parallel subagents"), follow it literally — there's always a reason. Don't substitute with "equivalent" alternatives without asking first.

**Justification:** Clear, concrete guidance with a specific example; essential for correct tool handling.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 4.7s)
  - This entry captures a specific behavioral pattern (literal interpretation of user's explicit tool requests) with a concrete example (tmux vs parallel subagents). It applies broadly across all interactions and represents a fundamental principle about respecting user intent that should guide all agent behavior, not just retrieved occasionally.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.75, necessity=0.85, 4.6s)
  - Clear, concrete guidance with a specific example; essential for correct tool handling.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.50, necessity=0.70, 20.2s)
  - The entry encodes a specific user preference with concrete examples ('tmux', 'parallel subagents') that is unlikely to be in the base system prompt; removing it would risk the agent overriding explicit tool choices with 'equivalent' alternatives. No concrete defect warrants refinement.

### `ecbfeb8c7243fb9d`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.67

**Original entry:**

> Skills are "capabilities and conventions the agent draws on, not scripts it executes" — avoid making skills overly rigid. Every rigid rule added is future maintenance cost. Prefers to "rely on larger skill routing and context, not rigid skills."

**Justification:** The entry provides useful design guidance but remains a general principle without concrete, verifiable details, limiting its quality and necessity; no specific defect requires refinement.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 8.4s)
  - This entry captures a specific architectural philosophy about skill design with a direct quote and clear guidance that would influence how the agent structures its capabilities. The principle applies broadly to all skill development and belongs in the system prompt where it can guide all skill-related decisions consistently.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 7.2s)
  - The entry provides useful design guidance but remains a general principle without concrete, verifiable details, limiting its quality and necessity; no specific defect requires refinement.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.80, necessity=0.70, 23.9s)
  - Corroborated principle with a direct quote about skill design philosophy; removing it could cause the agent to default to rigid, script-like skills instead of flexible, context-dependent capabilities.

### `f5632decb7fda7e1`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.47, necessity=0.43

**Original entry:**

> Prefers "easy stuff first" when tackling problems. Will explicitly call out this approach when breaking down work.

**Justification:** General statement about problem‑solving preference; not specific or indispensable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `drop` (quality=0.30, necessity=0.10, 3.8s)
  - This entry describes a common problem-solving heuristic that any competent agent would naturally employ without explicit instruction. The observation is too general to meaningfully change agent behavior and lacks the specificity needed to be actionable or retrievable in relevant contexts.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 4.1s)
  - General statement about problem‑solving preference; not specific or indispensable.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.60, necessity=0.70, 19.2s)
  - The quoted phrase 'easy stuff first' provides a specific, retrievable signal of the user's preferred problem-solving approach, and removing it would alter concrete task-sequencing recommendations the agent makes for this user.

### `ffebf77904896ae7`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.70, necessity=0.70

**Original entry:**

> Works with NVIDIA projects (NeMo, Studio, Omnipush, etc.) and tests cmux integration. Has access to NVIDIA Omnistations. Working on NeMo Platform agentic-use benchmarking. Has access to NVIDIA NGC/inference API keys.

**Justification:** The entry lists specific NVIDIA projects and resources but is somewhat generic and not critical for core agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.75, necessity=0.85, 3.9s)
  - The entry combines multiple distinct topics (NVIDIA project work, hardware access, benchmarking work, and API credentials) that would be better separated for precise retrieval. Each represents a different facet of the user's work environment.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.40, 4.5s)
  - The entry lists specific NVIDIA projects and resources but is somewhat generic and not critical for core agent behavior.
- `nvidia-moonshotai-kimi-k2-6` -> `keep` (quality=0.75, necessity=0.85, 16.9s)
  - The entry contains multiple specific named entities (NeMo, Omnipush, cmux, Omnistations, NGC) and concrete resource facts that would directly influence the agent's technical recommendations and assumptions about API access.

### `2071e206646832a9`

- **verdict:** `keep` (confidence 0.50)
- **scores:** quality=0.80, necessity=0.53

**Original entry:**

> When syncing between local and remote document mirrors (e.g., in-repo RFC and Linear doc): update whichever is more current. If both are the same, start with the local copy then push that up. 
> 
> ## Tools and workflows — shell and dotfiles
> 
> Uses zsh with oh-my-zsh. ZDOTDIR is `~/.config/zsh`. Has `.zshrc.local` symlinked to `.config/zsh/locals/.zshrc.work`. Prefers cached completion approach for shell startup performance.

**Justification:** The entry provides concrete details about sync rules and zsh configuration but is not critical for core agent behavior.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.85, necessity=0.80, 3.8s)
  - The entry combines two distinct topics: document syncing workflow and shell configuration. These should be separated as they address completely different concerns and would be retrieved in different contexts.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.75, necessity=0.25, 4.6s)
  - The entry provides concrete details about sync rules and zsh configuration but is not critical for core agent behavior.

### `777f85f2c2a6580f`

- **verdict:** `keep` (confidence 0.50)
- **scores:** quality=0.65, necessity=0.55

**Original entry:**

> Framework distinction: **skills are primitives** (single-invocation, single deliverable, no session state), **agents are sessions** (multi-round, collaborative, durable state across turns). Council-of-elders is a primitive so should stay a skill. 
> 
> ## Documentation and writing style
> 
> For RFC and design docs: wants concise text, avoids "puff language," not looking for word count. Prefers "broad strokes" to iterate on rather than deep detail up front.

**Justification:** Specific guidance on primitives vs agents and documentation style, fairly concrete and not duplicated.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `refine` (quality=0.70, necessity=0.80, 3.5s)
  - The entry combines two distinct topics: (1) a specific architectural distinction about skills vs agents, and (2) general documentation writing preferences. These should be separated as they address unrelated concerns and would be retrieved in different contexts.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.60, necessity=0.30, 7.2s)
  - Specific guidance on primitives vs agents and documentation style, fairly concrete and not duplicated.

### `3ebdcd9b6c4913b5`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.40, necessity=0.37

**Original entry:**

> Comfortable with uncertainty and explicit about unknowns. Will say "I genuinely don't know" rather than guessing. Values honesty about knowledge gaps in decision-making.

**Justification:** Clear behavioral guideline about honesty with uncertainty, but somewhat general; removal would affect tone and uncertainty handling rather than a specific decision.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-5` -> `promote_to_prompt` (quality=0.30, necessity=0.50, 4.3s)
  - This describes a general communication style about acknowledging uncertainty that should apply universally across all interactions, not just in specific retrievable contexts. While valuable, it's better suited as a system-level instruction than a durable memory entry tied to particular sessions.
- `nvidia-nvidia-nemotron-3-nano-30b-a3b` -> `keep` (quality=0.50, necessity=0.50, 8.9s)
  - Clear behavioral guideline about honesty with uncertainty, but somewhat general; removal would affect tone and uncertainty handling rather than a specific decision.
- `nvidia-moonshotai-kimi-k2-6` -> `drop` (quality=0.40, necessity=0.10, 49.6s)
  - Honesty about knowledge gaps and avoiding speculation is standard behavior already enforced by the base system prompt; this entry adds no distinct, user-specific signal that would change agent decisions or tone in a meaningful way.

## Per-judge errors

| entry | model | type | message |
| --- | --- | --- | --- |
| `777f85f2c2a6580f` | `nvidia-moonshotai-kimi-k2-6` | `ValueError` | openai-compatible response had empty content: ChatCompletion(id='chatcmpl-2ce15600-4d70-4a47-b17f-955958d06cd3', choices=[Choice(finish_reason='length', index=0, logprobs=None, message=ChatCompletionMessage(content=None, refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=None, reasoning_content='The user wants me to evaluate a durable memory entry for an AI agent. I need to output exactly one JSON object with no preamble, no markdown, no code fences.\n\n |
| `2071e206646832a9` | `nvidia-moonshotai-kimi-k2-6` | `ValueError` | openai-compatible response had empty content: ChatCompletion(id='chatcmpl-448001d5-5793-4699-847b-b154b95c1b33', choices=[Choice(finish_reason='length', index=0, logprobs=None, message=ChatCompletionMessage(content=None, refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=None, reasoning_content='The user wants me to evaluate a single durable memory entry and output only a JSON object.\n\nLet\'s analyze the entry:\n\n```\nWhen syncing between local and re |
