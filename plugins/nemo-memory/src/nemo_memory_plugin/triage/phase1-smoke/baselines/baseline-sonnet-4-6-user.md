# Memory triage proposals — `pi-hermes:CONSOLIDATED:user`

## Run

- **council:** `azure-anthropic-claude-sonnet-4-6`
- **started:** 2026-06-04T15:36:51.245389+00:00
- **finished:** 2026-06-04T15:48:19.887708+00:00
- **elapsed:** 688.6s
- **proposals:** 71
- **errors:** 0
- **skipped entries:** 0

## Summary

| verdict | count | % of proposals |
| --- | ---: | ---: |
| `drop` | 1 | 1.4% |
| `merge` | 0 | 0.0% |
| `refine` | 17 | 23.9% |
| `promote_to_prompt` | 21 | 29.6% |
| `keep` | 32 | 45.1% |

## `drop` (1)

### `3ebdcd9b6c4913b5`

- **verdict:** `drop` (confidence 1.00)
- **scores:** quality=0.20, necessity=0.10

**Original entry:**

> Comfortable with uncertainty and explicit about unknowns. Will say "I genuinely don't know" rather than guessing. Values honesty about knowledge gaps in decision-making.

**Justification:** This entry describes a general epistemic virtue (comfort with uncertainty, honesty about knowledge gaps) that applies to any thoughtful person and is not specific to this user's workflows, tools, or decisions. It would not change concrete agent behavior and is too vague to be retrievable in a meaningful way.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `drop` (quality=0.20, necessity=0.10, 3.8s)
  - This entry describes a general epistemic virtue (comfort with uncertainty, honesty about knowledge gaps) that applies to any thoughtful person and is not specific to this user's workflows, tools, or decisions. It would not change concrete agent behavior and is too vague to be retrievable in a meaningful way.

## `refine` (17)

### `0cf94a88d9bf510e`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.90

**Original entry:**

> Prefers deep "under the hood" explanations that connect abstract mechanisms to familiar experiences ("you've used this without realizing"). Appreciates bridging theory to practice rather than surface-level how-to guides. 
> 
> ## Time estimates and planning
> 
> Dislikes time estimates in agentic development contexts: "I don't care about estimates and they only serve to muddy the waters. We're all doing agentic development, so engineering days means very little." "Estimates muddy the waters." Considers them subjective and unlikely to influence decisions unless something will take a year. Prefers categorical scales (none/small/non-trivial) over specific durations. What matters is whether a slice depends on hard design calls, not calendar-day framing.

**Justification:** The entry combines two distinct topics (explanation style preferences and time-estimate preferences) that should be separate entries for precise retrieval. Both topics are high-quality with direct quotes and concrete behavioral signals.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.85, necessity=0.90, 5.4s)
  - The entry combines two distinct topics (explanation style preferences and time-estimate preferences) that should be separate entries for precise retrieval. Both topics are high-quality with direct quotes and concrete behavioral signals.

### `1b1ef746cf511fe9`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.80

**Original entry:**

> Prefers planning sessions before implementation when tackling complex fixes. When asked "do you have enough information to get started or would you like a planning session?", explicitly requested a plan before coding. 
> 
> ## Technical preferences — code quality and style
> 
> "I'm always in favor of more static typing, dynamic typing is a bug in potentia." Uses EntityClient as reference for preferred typing style.

**Justification:** The entry combines two distinct topics (planning preference and static typing preference) that should be separate entries for clean retrieval. Both contain specific, actionable signals including a direct quote and a named reference entity.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.75, necessity=0.80, 3.5s)
  - The entry combines two distinct topics (planning preference and static typing preference) that should be separate entries for clean retrieval. Both contain specific, actionable signals including a direct quote and a named reference entity.

### `2071e206646832a9`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When syncing between local and remote document mirrors (e.g., in-repo RFC and Linear doc): update whichever is more current. If both are the same, start with the local copy then push that up. 
> 
> ## Tools and workflows — shell and dotfiles
> 
> Uses zsh with oh-my-zsh. ZDOTDIR is `~/.config/zsh`. Has `.zshrc.local` symlinked to `.config/zsh/locals/.zshrc.work`. Prefers cached completion approach for shell startup performance.

**Justification:** The entry combines two distinct topics (document sync strategy and zsh/dotfiles configuration) that should be separate entries for proper retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.80, 3.8s)
  - The entry combines two distinct topics (document sync strategy and zsh/dotfiles configuration) that should be separate entries for proper retrieval.

### `44321d2304e81f90`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.80

**Original entry:**

> Comfortable with "YOLO" approaches for small changes vs. rigid testing. Pragmatic about testing — willing to YOLO small changes and defer test infrastructure until it's genuinely needed. 
> 
> ## Named people, tools, and projects
> 
> User is Max Dubrinsky (mdubrinsky@nvidia.com, GitHub: maxdubrinsky).

**Refined text proposed:**

> Max is pragmatic about testing: comfortable with 'YOLO' approaches for small changes and prefers to defer test infrastructure until it's genuinely needed rather than building it upfront.

**Justification:** The entry combines two distinct topics that should be separated: Max's testing pragmatism/YOLO preference, and his identity/contact info. Mixing PII with a behavioral preference makes both harder to retrieve accurately.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.60, necessity=0.80, 4.2s)
  - The entry combines two distinct topics that should be separated: Max's testing pragmatism/YOLO preference, and his identity/contact info. Mixing PII with a behavioral preference makes both harder to retrieve accurately.

### `6935e3c6fc1098b3`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.65, necessity=0.80

**Original entry:**

> Has deepagents-cli configured with internal model provider access to many interesting models. Plans to use deepagents as the interface where prompt-tuned models will eventually be exposed. Prefers to do most writing/authoring in Claude Code (Opus-4.7 as best coding model) but run execution in deepagents. Watching token spend — cost-conscious when evaluating multi-model approaches.

**Justification:** The entry combines multiple distinct topics: (1) deepagents-cli setup and workflow split between Claude Code vs deepagents, (2) model preference (Opus-4.7 for coding), and (3) cost-consciousness. These should be separated so each can be retrieved independently. Also, 'Opus-4.7' appears to be a non-standard model name that may reflect a misremembering (Claude Opus 4 / claude-opus-4-5 are real; '4.7' is not standard) — preserving as-stated since it's the user's own claim.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.65, necessity=0.80, 5.5s)
  - The entry combines multiple distinct topics: (1) deepagents-cli setup and workflow split between Claude Code vs deepagents, (2) model preference (Opus-4.7 for coding), and (3) cost-consciousness. These should be separated so each can be retrieved independently. Also, 'Opus-4.7' appears to be a non-standard model name that may reflect a misremembering (Claude Opus 4 / claude-opus-4-5 are real; '4.7' is not standard) — preserving as-stated since it's the user's own claim.

### `777f85f2c2a6580f`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.85

**Original entry:**

> Framework distinction: **skills are primitives** (single-invocation, single deliverable, no session state), **agents are sessions** (multi-round, collaborative, durable state across turns). Council-of-elders is a primitive so should stay a skill. 
> 
> ## Documentation and writing style
> 
> For RFC and design docs: wants concise text, avoids "puff language," not looking for word count. Prefers "broad strokes" to iterate on rather than deep detail up front.

**Justification:** The entry combines two distinct topics (skills-vs-agents framework distinction and RFC/doc writing style preferences) that should be separate entries for clean retrieval. This is the 'multiple distinct topics' defect.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.85, 3.8s)
  - The entry combines two distinct topics (skills-vs-agents framework distinction and RFC/doc writing style preferences) that should be separate entries for clean retrieval. This is the 'multiple distinct topics' defect.

### `a2904a90b343a7bf`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.90

**Original entry:**

> Strongly dislikes adding imperatives/directives in front of existing DO/DO NOT blocks in AGENTS.md. "If an agent isn't obeying [the DO/DO NOT block], then I don't know what will." Don't stack ceremony in front of existing instructions. 
> 
> ## Communication style and output preferences
> 
> Prefers terse output, ≲ one terminal screen. Wants response lengths kept shorter — feedback that output "just longer than my screen" was too long.

**Refined text proposed:**

> Strongly dislikes adding imperatives/directives in front of existing DO/DO NOT blocks in AGENTS.md. "If an agent isn't obeying [the DO/DO NOT block], then I don't know what will." Don't stack ceremony in front of existing instructions.

**Justification:** The entry combines two distinct topics (AGENTS.md formatting preference and general output length preference) that should be separate entries for clean retrieval and targeted application.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.75, necessity=0.90, 6.0s)
  - The entry combines two distinct topics (AGENTS.md formatting preference and general output length preference) that should be separate entries for clean retrieval and targeted application.

### `b6d1a2581c4fd3b3`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.85

**Original entry:**

> For NVIDIA/OpenShell issues/PRs, user prefers casual, conversational, first-person tone over formal third-person language. Example: "I'm thinking we just add the command" rather than "Adding the command is the better fix." Avoid referring to "maintainers" in third person since the user is part of that group — use inclusive language like "we" or direct proposals. Prefers tight, conversational prose over verbose academic/formal writing. User replaced a 4-paragraph feature-request body with ~3 sentences in first-person. Avoid walls of text in issue/PR drafts — show the minimal viable version first.

**Refined text proposed:**

> For NVIDIA/OpenShell GitHub issues/PRs: use casual, conversational first-person ('I'm thinking we just add the command') not formal third-person. Use 'we' instead of 'maintainers' — user is part of the team. Keep drafts minimal: show the shortest viable version first, no walls of text (user replaced a 4-paragraph feature-request body with ~3 sentences).

**Justification:** The entry combines two distinct topics: (1) tone/voice preferences for NVIDIA/OpenShell GitHub issues/PRs, and (2) length/format preference (minimal viable version first, avoid walls of text). These should ideally be separate, but more critically the entry is more than twice as long as needed — the core signals can be expressed concisely without losing the named entities or the direct quote.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.75, necessity=0.85, 6.3s)
  - The entry combines two distinct topics: (1) tone/voice preferences for NVIDIA/OpenShell GitHub issues/PRs, and (2) length/format preference (minimal viable version first, avoid walls of text). These should ideally be separate, but more critically the entry is more than twice as long as needed — the core signals can be expressed concisely without losing the named entities or the direct quote.

### `bb0d40fa9755379b`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.95

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

**Justification:** The entry combines three distinct topics (refactoring analysis preferences, Linear URL rewriting, and git branch workflow) that should be separate entries for reliable retrieval. The defect is topic consolidation — each topic is retrievable only when all three happen to be queried simultaneously.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.80, necessity=0.95, 3.3s)
  - The entry combines three distinct topics (refactoring analysis preferences, Linear URL rewriting, and git branch workflow) that should be separate entries for reliable retrieval. The defect is topic consolidation — each topic is retrievable only when all three happen to be queried simultaneously.

### `c14577e2c749b6a5`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.90

**Original entry:**

> Prefers reading long-form documents in Linear rather than in terminal/files. When drafting decision docs or substantial write-ups, post to Linear for easier reading and commenting. 
> 
> ## Code review — council-of-elders pattern
> 
> Uses "council review" pattern for code reviews: multiple independent reviewers examine same diff separately. Review quality bar: "Would the author be glad I flagged this?" (not "technically correct"). Expects 3-8 substantive findings distributed unevenly (anti-checklist rule). Must-fix requires: verbatim quote, named consumer, reproduction path (file:line → trigger → symptom). Prefers precision over quantity; values specific, consequential findings over comprehensive checklists. The point is consensus signal — one reviewer's opinion is noise, two+ reviewers flagging the same thing is signal worth acting on.

**Justification:** The entry combines two distinct topics—Linear document posting preference and the council-of-elders code review pattern—that should be separate entries for precise retrieval. Each topic is specific and behavior-changing, but conflating them reduces retrievability when only one is relevant.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.80, necessity=0.90, 3.1s)
  - The entry combines two distinct topics—Linear document posting preference and the council-of-elders code review pattern—that should be separate entries for precise retrieval. Each topic is specific and behavior-changing, but conflating them reduces retrievability when only one is relevant.

### `cc2763c3925d2b64`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.60

**Original entry:**

> Max Dubrinsky (GitHub: maxdubrinsky) is a maintainer of NVIDIA/OpenShell. Has personal connections to NVIDIA/OpenShell maintainers but contributes via fork (not direct push access).

**Refined text proposed:**

> Max Dubrinsky (GitHub: maxdubrinsky) is a maintainer of NVIDIA/OpenShell with personal connections to other maintainers, but contributes via fork rather than direct push access to the repository.

**Justification:** The entry combines two distinct facts that should be separated: (1) Max Dubrinsky's identity and GitHub handle as an NVIDIA/OpenShell maintainer, and (2) his contribution method (via fork, not direct push access). These are separate retrievable facts with different use cases.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.60, 3.6s)
  - The entry combines two distinct facts that should be separated: (1) Max Dubrinsky's identity and GitHub handle as an NVIDIA/OpenShell maintainer, and (2) his contribution method (via fork, not direct push access). These are separate retrievable facts with different use cases.

### `cd59e47469ff3772`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.45, necessity=0.50

**Original entry:**

> Thinks architecturally before implementing — considers whether ideas are "in step with project direction" and evaluates second-order implications. Prefers to ground discussions in actual code before reasoning about design.

**Refined text proposed:**

> Thinks architecturally before implementing — considers whether ideas are 'in step with project direction' and evaluates second-order implications before committing to an approach.

**Justification:** The entry combines two distinct behavioral signals that should be separated: (1) architectural thinking / evaluating second-order implications before implementing, and (2) preferring to ground discussions in actual code before reasoning about design. These are independent preferences that could be retrieved in different contexts.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.45, necessity=0.50, 3.4s)
  - The entry combines two distinct behavioral signals that should be separated: (1) architectural thinking / evaluating second-order implications before implementing, and (2) preferring to ground discussions in actual code before reasoning about design. These are independent preferences that could be retrieved in different contexts.

### `da5498e4affca2a0`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> Expects verification of claims before making breaking changes. Will ask "can you make sure of that" and wants downstream impact checked (e.g., grepping for field usage before removing from public schema). 
> 
> ## Technical preferences — architecture and design
> 
> Data model evolution: prefer to omit fields until there's a concrete consumer. "Easier to add a field than remove one." Keep surface area small in initial implementations rather than pre-emptively adding fields that might be useful later.

**Justification:** The entry combines two distinct topics — verification/impact-checking behavior (with a direct quote) and data model evolution philosophy — which should be separate entries for precise retrieval. The defect is multiple distinct topics merged together.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.80, 3.5s)
  - The entry combines two distinct topics — verification/impact-checking behavior (with a direct quote) and data model evolution philosophy — which should be separate entries for precise retrieval. The defect is multiple distinct topics merged together.

### `e626e4bbb2861be3`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.90

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

**Justification:** The entry combines three distinct topics (shell startup performance preferences, beads memory tool workflow, and tmux team session preferences) into one entry, which is the 'multiple distinct topics' defect. Each topic should be a separate entry for clean retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.70, necessity=0.90, 3.7s)
  - The entry combines three distinct topics (shell startup performance preferences, beads memory tool workflow, and tmux team session preferences) into one entry, which is the 'multiple distinct topics' defect. Each topic should be a separate entry for clean retrieval.

### `ef4733acc96c530e`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.80

**Original entry:**

> Manages dotfiles with GNU Stow for both work and personal machines. Spins up new machines rarely. Prefers declarative, in-repo configuration over implicit machine-local setup. Values shell startup performance, especially in Python repos.

**Refined text proposed:**

> Manages dotfiles with GNU Stow for both work and personal machines. Spins up new machines rarely. Prefers declarative, in-repo configuration over implicit machine-local setup.

**Justification:** The entry combines two distinct topics (dotfile/machine setup philosophy and shell startup performance preference) that should be separate entries for cleaner retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.60, necessity=0.80, 4.2s)
  - The entry combines two distinct topics (dotfile/machine setup philosophy and shell startup performance preference) that should be separate entries for cleaner retrieval.

### `fa248bb8026a7f3e`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.80

**Original entry:**

> Prefers interactive, incremental onboarding when exploring new codebases. Wants information "fed" in chunks rather than large reports. Starts exploration by examining types and contracts first to understand how data is structured and used.

**Justification:** The entry combines two distinct topics that should be separated: (1) a presentation/interaction preference (chunked, incremental delivery) and (2) a technical methodology preference (exploring types/contracts first). Splitting them makes each retrievable and actionable on its own.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.60, necessity=0.80, 4.1s)
  - The entry combines two distinct topics that should be separated: (1) a presentation/interaction preference (chunked, incremental delivery) and (2) a technical methodology preference (exploring types/contracts first). Splitting them makes each retrievable and actionable on its own.

### `ffebf77904896ae7`

- **verdict:** `refine` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.85

**Original entry:**

> Works with NVIDIA projects (NeMo, Studio, Omnipush, etc.) and tests cmux integration. Has access to NVIDIA Omnistations. Working on NeMo Platform agentic-use benchmarking. Has access to NVIDIA NGC/inference API keys.

**Justification:** The entry combines multiple distinct topics (NVIDIA project involvement, cmux integration testing, Omnistations access, NeMo Platform benchmarking work, and NGC/inference API key access) that would be more useful and retrievable as separate entries. This is the 'combines multiple distinct topics' defect.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `refine` (quality=0.75, necessity=0.85, 3.3s)
  - The entry combines multiple distinct topics (NVIDIA project involvement, cmux integration testing, Omnistations access, NeMo Platform benchmarking work, and NGC/inference API key access) that would be more useful and retrievable as separate entries. This is the 'combines multiple distinct topics' defect.

## `promote_to_prompt` (21)

### `07b56fbdcc233913`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.85

**Original entry:**

> Prefers distilled, compact memories over verbose ones. When memories accumulate specific implementation details (file paths, class names, line numbers), wants them trimmed to essential decisions/principles and pointers to canonical sources. Asks for memory cleanup proactively to reduce context load.

**Justification:** This entry describes a consistent, broad preference that should govern every memory-writing and cleanup interaction—not just recalled occasionally. It directly changes agent behavior (trimming specifics, proactive cleanup proposals) and applies universally enough to warrant always-on inclusion rather than retrieval-based access.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 3.9s)
  - This entry describes a consistent, broad preference that should govern every memory-writing and cleanup interaction—not just recalled occasionally. It directly changes agent behavior (trimming specifics, proactive cleanup proposals) and applies universally enough to warrant always-on inclusion rather than retrieval-based access.

### `0f7fb9245ec9337d`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.90, necessity=1.00

**Original entry:**

> Dislikes "techno-jargon" (e.g., "forcing function," "load-bearing") and em-dashes in written docs — these make text sound AI-generated. Wants their own voice to shine through in RFCs and technical writing.

**Justification:** This entry is highly specific (named phrases, named formatting elements, named artifact type), directly actionable, and applies to virtually every writing task the agent assists with. It should be in the always-on system prompt so the agent never needs to retrieve it to avoid banned patterns.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.90, necessity=1.00, 4.0s)
  - This entry is highly specific (named phrases, named formatting elements, named artifact type), directly actionable, and applies to virtually every writing task the agent assists with. It should be in the always-on system prompt so the agent never needs to retrieve it to avoid banned patterns.

### `1afa1e62e8955f70`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.80

**Original entry:**

> Prefers interactive sessions with think-out-loud reasoning. Wants to be included in the reasoning process, not just presented with conclusions. Values collaborative decision-making over being handed finished answers.

**Justification:** This describes a fundamental interaction style preference that applies to every session, not just retrievable in specific contexts. It should be always-on so the agent never defaults to presenting finished conclusions without showing reasoning.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.60, necessity=0.80, 3.3s)
  - This describes a fundamental interaction style preference that applies to every session, not just retrievable in specific contexts. It should be always-on so the agent never defaults to presenting finished conclusions without showing reasoning.

### `225dfc15f4624267`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.90

**Original entry:**

> When monitoring PRs for code review feedback: Apply good CodeRabbit suggestions automatically, but justify and reply to unhelpful ones before resolving. Team member feedback carries more weight — flag those for user review instead of fixing automatically.

**Justification:** This entry defines a concrete decision-making protocol for PR review behavior that would directly change agent actions (auto-apply vs. flag vs. justify-and-resolve). It applies broadly to all PR-related interactions, making it a good candidate for the always-on system prompt rather than a retrieval-dependent memory.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.90, 4.1s)
  - This entry defines a concrete decision-making protocol for PR review behavior that would directly change agent actions (auto-apply vs. flag vs. justify-and-resolve). It applies broadly to all PR-related interactions, making it a good candidate for the always-on system prompt rather than a retrieval-dependent memory.

### `2c52e8806ac9ede6`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.95

**Original entry:**

> ## Collaboration style
> 
> Keeps user in the development loop — "Be vocal if you are missing information or could use another set of eyes from me." Wants gaps and uncertainties surfaced explicitly rather than having the agent make assumptions. When uncertain, do less not more — pause before spawning ceremony. Values being asked questions when the path is unclear.

**Justification:** This entry has 8-session corroboration, contains a direct quote, and defines a concrete behavioral rule (pause before acting when uncertain, surface gaps explicitly) that should govern every interaction—not just retrieved when contextually relevant. It directly changes agent decisions about when to proceed vs. ask.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.95, 6.5s)
  - This entry has 8-session corroboration, contains a direct quote, and defines a concrete behavioral rule (pause before acting when uncertain, surface gaps explicitly) that should govern every interaction—not just retrieved when contextually relevant. It directly changes agent decisions about when to proceed vs. ask.

### `2d5005c7ea8c6a13`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.95

**Original entry:**

> Values critical thinking and evidence-based pushback. "If there is anything said above that you take issue with, please push back. Think critically!" Expects substantive engagement over deference. When presenting architectural proposals or recommendations, wants validation with concrete evidence from codebase/docs and grounded reasoning. Will explicitly ask "push back on this read and verify this claim" before bringing ideas to coworkers.

**Justification:** This entry is corroborated across 6 sessions, contains direct quotes, and describes a core interaction style that should govern every response involving recommendations or architectural proposals—not just retrieved situationally. Removing it would cause the agent to default to deferential validation rather than substantive pushback.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.95, 4.1s)
  - This entry is corroborated across 6 sessions, contains direct quotes, and describes a core interaction style that should govern every response involving recommendations or architectural proposals—not just retrieved situationally. Removing it would cause the agent to default to deferential validation rather than substantive pushback.

### `33490df8bf4790b5`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.90

**Original entry:**

> For bug reports, user wants diagnostic findings without fix recommendations ("avoid making fix recommendations since this is a bug"). Keep bug issues descriptive of the problem, not prescriptive of the solution.

**Justification:** This is a clear, actionable instruction with a direct quote from the user that would meaningfully change agent behavior on every bug report interaction. It applies broadly enough to warrant always-on inclusion rather than retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 21.8s)
  - This is a clear, actionable instruction with a direct quote from the user that would meaningfully change agent behavior on every bug report interaction. It applies broadly enough to warrant always-on inclusion rather than retrieval.

### `3a4f5eb974a14f65`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.90

**Original entry:**

> Challenges assumptions and expects evidence-based verification. When told something about code or workflow (e.g., "the rebase didn't change anything"), user will question it ("That cannot be right") and expects concrete proof (git range-diff, patch-ids, byte-level diffs) rather than accepting claims at face value. Provide verifiable evidence, not assertions.

**Justification:** This entry captures a concrete, high-impact behavioral expectation (provide verifiable evidence like git range-diff/patch-ids rather than assertions) that applies to virtually every technical interaction with this user. Its broad applicability and direct effect on agent behavior make it a strong candidate for the always-on system prompt rather than retrieval-only memory.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.90, 4.6s)
  - This entry captures a concrete, high-impact behavioral expectation (provide verifiable evidence like git range-diff/patch-ids rather than assertions) that applies to virtually every technical interaction with this user. Its broad applicability and direct effect on agent behavior make it a strong candidate for the always-on system prompt rather than retrieval-only memory.

### `3adf210f1341a445`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.85

**Original entry:**

> When asking about architecture decisions, user wants concrete reusability analysis ("who is consumer #3") rather than speculative abstraction. Values YAGNI principle and practical justification for shared libraries.

**Justification:** This captures a concrete, actionable preference ('who is consumer #3') that would materially change how the agent responds to architecture questions—pushing toward concrete consumer enumeration and YAGNI justification rather than speculative abstraction. It's specific enough and broadly applicable enough to belong in the always-on system prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 4.1s)
  - This captures a concrete, actionable preference ('who is consumer #3') that would materially change how the agent responds to architecture questions—pushing toward concrete consumer enumeration and YAGNI justification rather than speculative abstraction. It's specific enough and broadly applicable enough to belong in the always-on system prompt.

### `3b633c1de36c5c76`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.85

**Original entry:**

> When user provides explicit design decisions or answers to questions, proceed with those answers rather than continuing extensive exploration. Values efficiency when decisions are already made. When scoping work, prefers to clarify intent if the request is ambiguous rather than having agent guess. Often refines scope or clarifies intent rather than picking from menus. Prefers narrow, well-scoped iterations over committing to large sweeps upfront.

**Justification:** This entry captures a consistent, high-signal behavioral preference (accept explicit decisions, clarify ambiguity, prefer narrow iterations) observed across 3 sessions that would meaningfully alter agent behavior if absent. It applies broadly enough to every interaction that it belongs in the always-on system prompt rather than being retrieved situationally.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.72, necessity=0.85, 3.5s)
  - This entry captures a consistent, high-signal behavioral preference (accept explicit decisions, clarify ambiguity, prefer narrow iterations) observed across 3 sessions that would meaningfully alter agent behavior if absent. It applies broadly enough to every interaction that it belongs in the always-on system prompt rather than being retrieved situationally.

### `5312e5c7aaf8d182`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.90

**Original entry:**

> Evaluates code review findings critically with justification. Expects "FIX" vs "DON'T FIX" decisions with clear reasoning, not blind acceptance of all suggestions. Uses cost/benefit analysis for proposed changes. Expects critical evaluation with justification for every decision — prefers seeing reasoning for both what gets applied and what gets rejected.

**Justification:** This entry captures a concrete, actionable behavioral preference (FIX vs DON'T FIX with cost/benefit reasoning) that would directly change how the agent handles every code review interaction. It applies broadly enough to warrant always-on presence rather than retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.90, 3.7s)
  - This entry captures a concrete, actionable behavioral preference (FIX vs DON'T FIX with cost/benefit reasoning) that would directly change how the agent handles every code review interaction. It applies broadly enough to warrant always-on presence rather than retrieval.

### `55a644cd8f6ff2c0`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.90

**Original entry:**

> Action-oriented when path is clear. "Don't have time to dawdle" — wants implementation over extended discussion when requirements are understood and context is available. Trusts recommended paths when offered choices during complex operations. Will choose autonomous completion of git workflows when given the choice. But: "If you have any questions/concerns, stop and ask." Values getting it right over getting it done fast.

**Justification:** This entry captures a precise, multi-faceted behavioral contract with direct quotes that should govern nearly every interaction involving implementation decisions, git workflows, or discussion vs. action tradeoffs — making it broadly applicable enough for the always-on system prompt rather than retrieval. The 3-session corroboration and specific quotes confirm its reliability.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.90, 4.7s)
  - This entry captures a precise, multi-faceted behavioral contract with direct quotes that should govern nearly every interaction involving implementation decisions, git workflows, or discussion vs. action tradeoffs — making it broadly applicable enough for the always-on system prompt rather than retrieval. The 3-session corroboration and specific quotes confirm its reliability.

### `5e218e8023703797`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.90

**Original entry:**

> When filing bugs, user prefers minimal investigation — capture the repro and symptoms, don't deep-dive into root cause. User said "Don't work too hard, the person fixing it can dig" when asked not to over-investigate code during bug filing.

**Justification:** This is a concrete, actionable preference backed by a direct quote that would meaningfully change agent behavior during bug-filing tasks. It applies broadly enough to any bug-filing interaction that it belongs in the always-on system prompt rather than relying on retrieval.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.85, necessity=0.90, 187.4s)
  - This is a concrete, actionable preference backed by a direct quote that would meaningfully change agent behavior during bug-filing tasks. It applies broadly enough to any bug-filing interaction that it belongs in the always-on system prompt rather than relying on retrieval.

### `84d3ccff688a9114`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.90

**Original entry:**

> Tighten text in prompts/instructions — "more text is sometimes less impactful." Values distilled, essential content over verbose explanations. Prefers condensed, to-the-point communication. "Don't try to explain the world" when asking for summaries — wants informative but focused content.

**Justification:** This entry has 3-session corroboration, contains specific quotes, and describes a core communication preference that would affect nearly every agent response. It belongs in the always-on system prompt rather than retrieved on demand.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 3.3s)
  - This entry has 3-session corroboration, contains specific quotes, and describes a core communication preference that would affect nearly every agent response. It belongs in the always-on system prompt rather than retrieved on demand.

### `8936920730d38570`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.90

**Original entry:**

> Uses dotfiles across multiple platforms (macOS, Ubuntu, Debian, Arch, CentOS). Cannot rely on consistent package managers like homebrew. Prefers cross-platform solutions using shell scripts and git clone over package-manager-specific approaches.

**Justification:** This entry names specific platforms (macOS, Ubuntu, Debian, Arch, CentOS) and prescribes concrete solution approaches (shell scripts and git clone over package managers). It would change agent behavior on nearly every dotfiles/tooling question, making it always-on system prompt material rather than a retrieved hint.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.80, necessity=0.90, 3.6s)
  - This entry names specific platforms (macOS, Ubuntu, Debian, Arch, CentOS) and prescribes concrete solution approaches (shell scripts and git clone over package managers). It would change agent behavior on nearly every dotfiles/tooling question, making it always-on system prompt material rather than a retrieved hint.

### `9cd72c55fda5ded2`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.90

**Original entry:**

> Prefers deliberate investigation over trial-and-error. When introducing a new tool, wants agent to "brush up" on how to use it before firing off commands. Values understanding complexity/scope before implementing. Slow at architectural boundaries; iteration speed never substitutes for thinking.

**Justification:** This entry captures a consistent, high-impact working style preference (deliberate investigation before action, understanding before implementing) that should govern every interaction rather than being retrieved situationally. With 4-session corroboration it is well-established and directly changes agent behavior at every tool introduction or architectural decision point.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.90, 3.9s)
  - This entry captures a consistent, high-impact working style preference (deliberate investigation before action, understanding before implementing) that should govern every interaction rather than being retrieved situationally. With 4-session corroboration it is well-established and directly changes agent behavior at every tool introduction or architectural decision point.

### `ccd19a2fa2414c49`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> Values consistency across the codebase — when fixing bugs or implementing features, prefers to match broader codebase patterns rather than keeping one-off exceptions ("do whatever is most consistent").

**Justification:** This is a clear, actionable preference that should govern every code-related decision the agent makes, not just ones where it happens to retrieve this memory. It captures a specific behavioral directive ('do whatever is most consistent') that would meaningfully change agent behavior if absent.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.70, necessity=0.80, 4.9s)
  - This is a clear, actionable preference that should govern every code-related decision the agent makes, not just ones where it happens to retrieve this memory. It captures a specific behavioral directive ('do whatever is most consistent') that would meaningfully change agent behavior if absent.

### `daa44d66c1c0e810`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.85

**Original entry:**

> When user explicitly asks for a specific tool or approach (e.g., "use tmux" not just "parallel subagents"), follow it literally — there's always a reason. Don't substitute with "equivalent" alternatives without asking first.

**Justification:** This is a broadly applicable behavioral directive that should govern every interaction where the user specifies a tool or method — not just occasionally retrieved ones. The concrete example ('use tmux' vs 'parallel subagents') grounds it well, and removing it would likely cause the agent to substitute tools it deems 'equivalent' without asking.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 5.0s)
  - This is a broadly applicable behavioral directive that should govern every interaction where the user specifies a tool or method — not just occasionally retrieved ones. The concrete example ('use tmux' vs 'parallel subagents') grounds it well, and removing it would likely cause the agent to substitute tools it deems 'equivalent' without asking.

### `ecbfeb8c7243fb9d`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.80

**Original entry:**

> Skills are "capabilities and conventions the agent draws on, not scripts it executes" — avoid making skills overly rigid. Every rigid rule added is future maintenance cost. Prefers to "rely on larger skill routing and context, not rigid skills."

**Justification:** This entry encodes a clear, actionable design philosophy about skill authoring with a direct quote — it would actively prevent the agent from over-constraining skills. Its broad applicability across all interactions makes it a strong candidate for the always-on system prompt rather than a retrieved memory.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.80, necessity=0.80, 4.0s)
  - This entry encodes a clear, actionable design philosophy about skill authoring with a direct quote — it would actively prevent the agent from over-constraining skills. Its broad applicability across all interactions makes it a strong candidate for the always-on system prompt rather than a retrieved memory.

### `f4a359b3859edf3d`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.90, necessity=1.00

**Original entry:**

> Prefers Python-style pseudocode over LaTeX/mathematical notation for expressing formulas and algorithms. "Prefer python to math since it's been 15 years since I've used LaTeX."

**Justification:** This preference directly and concretely affects how the agent formats every formula or algorithm explanation—always use Python-style pseudocode instead of LaTeX math notation. The direct quote and clear rationale make it high quality, and the broad applicability across all technical interactions warrants promotion to the always-on system prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.90, necessity=1.00, 3.6s)
  - This preference directly and concretely affects how the agent formats every formula or algorithm explanation—always use Python-style pseudocode instead of LaTeX math notation. The direct quote and clear rationale make it high quality, and the broad applicability across all technical interactions warrants promotion to the always-on system prompt.

### `ffccf834cf1224a4`

- **verdict:** `promote_to_prompt` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.85

**Original entry:**

> Prefers minimal, deliberate solutions over adding configuration mechanisms — "don't want to add that mechanism" when rejecting a sidecar config approach. Favors starting small with explicit overrides and iterating from there.

**Justification:** This is a consistent, actionable design philosophy with a direct quote that would influence proposal framing across many sessions — the agent should default to minimal/explicit solutions and avoid suggesting configuration mechanisms without this needing to be retrieved. It applies broadly enough to warrant always-on presence.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `promote_to_prompt` (quality=0.75, necessity=0.85, 4.2s)
  - This is a consistent, actionable design philosophy with a direct quote that would influence proposal framing across many sessions — the agent should default to minimal/explicit solutions and avoid suggesting configuration mechanisms without this needing to be retrieved. It applies broadly enough to warrant always-on presence.

## `keep` (32)

### `09d03f0713454d63`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.70

**Original entry:**

> Dislikes overly clinical/medical language in documentation headings — rejected "Anatomy of an Agent" in favor of "Agent Definition" when drafting public docs for the NeMo Platform agents page.

**Justification:** The entry is specific and verifiable, citing a concrete rejected phrase ('Anatomy of an Agent') and the preferred alternative ('Agent Definition') in a named context (NeMo Platform agents page). It would meaningfully guide heading choices in future documentation drafting tasks.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.85, necessity=0.70, 4.8s)
  - The entry is specific and verifiable, citing a concrete rejected phrase ('Anatomy of an Agent') and the preferred alternative ('Agent Definition') in a named context (NeMo Platform agents page). It would meaningfully guide heading choices in future documentation drafting tasks.

### `1f841c1e54060e46`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When filing GitHub issues, user prefers to "leave the labeling for someone else" — apply only obviously correct labels, leave discretionary labels to human reviewers.

**Justification:** The entry contains a direct quote and a specific behavioral rule about GitHub issue labeling that would concretely change agent behavior — it prevents over-labeling when filing issues. Quality is slightly below 1.0 only because it's a single-session observation, but the content is specific and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 4.4s)
  - The entry contains a direct quote and a specific behavioral rule about GitHub issue labeling that would concretely change agent behavior — it prevents over-labeling when filing issues. Quality is slightly below 1.0 only because it's a single-session observation, but the content is specific and actionable.

### `24883461872a7245`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.90

**Original entry:**

> Prefers explicit credential mapping between services. Does not want automatic substitution of credentials meant for one API provider as fallback credentials for a different provider, even when upstream code has such fallback chains.

**Justification:** This captures a specific, non-obvious preference about credential isolation that would directly change agent behavior when setting up multi-provider API configurations or debugging authentication fallback chains. It's concrete enough to be actionable and unlikely to be inferred from general principles.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.90, 4.9s)
  - This captures a specific, non-obvious preference about credential isolation that would directly change agent behavior when setting up multi-provider API configurations or debugging authentication fallback chains. It's concrete enough to be actionable and unlikely to be inferred from general principles.

### `27ab19ee42afc820`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.90

**Original entry:**

> Prefers condensed, action-oriented UIs. Asked to remove verbose descriptions from skill previews and replace Y/n confirmations with clear multi-choice menus (e.g., "1. Install all 2. Select which 3. Skip"). Likes hierarchical multiselect UIs with sublabels showing structure (plugin name > skill names).

**Justification:** This entry contains concrete, specific UI preferences with named examples (numbered multi-choice menus, hierarchical multiselect with plugin>skill sublabels) that would directly change how the agent designs or recommends UI flows. The specificity is high enough to be actionable and unambiguously retrievable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.80, necessity=0.90, 3.7s)
  - This entry contains concrete, specific UI preferences with named examples (numbered multi-choice menus, hierarchical multiselect with plugin>skill sublabels) that would directly change how the agent designs or recommends UI flows. The specificity is high enough to be actionable and unambiguously retrievable.

### `2b3f32758b063f73`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.60

**Original entry:**

> When reviewing council/multi-reviewer feedback, user wants balanced reasoning that doesn't overweight obvious mechanical fixes (e.g., "vendoring would of course have been fixed"). Focus on substantive issues that require judgment.

**Justification:** The entry captures a specific preference about how to weight feedback types when reviewing council/multi-reviewer outputs, with a concrete example quote that anchors it. It's retrievable in that context and would meaningfully shape how the agent frames its analysis, though it applies narrowly enough that it belongs in memory rather than the system prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 4.0s)
  - The entry captures a specific preference about how to weight feedback types when reviewing council/multi-reviewer outputs, with a concrete example quote that anchors it. It's retrievable in that context and would meaningfully shape how the agent frames its analysis, though it applies narrowly enough that it belongs in memory rather than the system prompt.

### `2b7aab650de6b343`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.90

**Original entry:**

> Finds hour markers in progress indicators "demoralizing" and prefers MM:SS format over H:MM:SS for elapsed time displays, even when duration exceeds 60 minutes (shows 73:21 instead of 1:13:21).

**Justification:** Highly specific preference with a concrete example (73:21 vs 1:13:21) and a quoted emotional reaction ('demoralizing'); this would directly change how the agent formats elapsed time displays above 60 minutes.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.85, necessity=0.90, 3.6s)
  - Highly specific preference with a concrete example (73:21 vs 1:13:21) and a quoted emotional reaction ('demoralizing'); this would directly change how the agent formats elapsed time displays above 60 minutes.

### `3362ba488cf7a744`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.80

**Original entry:**

> When selecting LLM models for configurations, user prefers "frontier chat across all providers" — comprehensive coverage of high-quality chat models from multiple providers (Anthropic, OpenAI, Google, DeepSeek, Qwen, etc.).

**Justification:** The entry captures a specific named preference ('frontier chat across all providers') with concrete provider examples, making it retrievable and actionable when the agent assists with LLM configuration decisions. Single-session observation reduces confidence but the specificity warrants retention.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.75, necessity=0.80, 5.0s)
  - The entry captures a specific named preference ('frontier chat across all providers') with concrete provider examples, making it retrievable and actionable when the agent assists with LLM configuration decisions. Single-session observation reduces confidence but the specificity warrants retention.

### `41503ab4453d0474`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When reviewing PRs that have been open for a while: wants thorough audit across the codebase, not just quick fixes. Appreciates being asked to "be discerning and fan out your team as necessary" when investigating scope/completeness. Values comprehensive investigation of what the PR might have missed or what main has changed since the merge base.

**Justification:** The entry captures a specific, actionable preference with a direct quote ('be discerning and fan out your team as necessary') that would concretely guide how the agent approaches PR review tasks—defaulting to broad codebase audits rather than narrow fixes. Removing it would likely cause the agent to default to more surface-level PR feedback.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.7s)
  - The entry captures a specific, actionable preference with a direct quote ('be discerning and fan out your team as necessary') that would concretely guide how the agent approaches PR review tasks—defaulting to broad codebase audits rather than narrow fixes. Removing it would likely cause the agent to default to more surface-level PR feedback.

### `4c3b54653e36b0a0`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.90

**Original entry:**

> When macOS sandbox causes permission errors with local services, user wants commands run without sandbox immediately (no need to ask first).

**Justification:** This entry encodes a specific behavioral preference (skip asking, run without sandbox immediately) in a concrete, retrievable scenario. It would directly change agent behavior when macOS sandbox permission errors arise with local services.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.90, 3.2s)
  - This entry encodes a specific behavioral preference (skip asking, run without sandbox immediately) in a concrete, retrievable scenario. It would directly change agent behavior when macOS sandbox permission errors arise with local services.

### `4fe0da7c8b7f985f`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When CodeRabbit suggests a Ruff rule violation, check the project's ruff.toml first — if the rule isn't enabled, the suggestion may be unhelpful. Justify by noting the rule isn't enforced and that fixing creates inconsistency with existing production patterns. Check project lint config before applying style/rule suggestions.

**Justification:** This entry provides actionable, specific guidance about CodeRabbit + ruff.toml interactions that would meaningfully change how the agent evaluates and responds to lint suggestions. The named tools (CodeRabbit, Ruff, ruff.toml) and the concrete workflow (check config before applying) make it retrievable and non-obvious.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 6.1s)
  - This entry provides actionable, specific guidance about CodeRabbit + ruff.toml interactions that would meaningfully change how the agent evaluates and responds to lint suggestions. The named tools (CodeRabbit, Ruff, ruff.toml) and the concrete workflow (check config before applying) make it retrievable and non-obvious.

### `552517c9122f43f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When resolving conflicts between openshell-sdk refactors and upstream changes: prefer extending the SDK to accept new parameters rather than falling back to inline implementations in consumers like openshell-cli. Keep shared logic in the SDK.

**Justification:** This entry names specific components (openshell-sdk, openshell-cli) and encodes a concrete architectural preference that would directly influence decisions about where to place shared logic. Removing it would cause the agent to miss a stated preference and potentially recommend inline implementations in consumers instead of extending the SDK.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.9s)
  - This entry names specific components (openshell-sdk, openshell-cli) and encodes a concrete architectural preference that would directly influence decisions about where to place shared logic. Removing it would cause the agent to miss a stated preference and potentially recommend inline implementations in consumers instead of extending the SDK.

### `59c8938da3dfc3dc`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.70

**Original entry:**

> Prefers all project outputs in consistent locations under REPO_ROOT (e.g., nat-jobs/, eval-out/, optimizer_results/). When adding new output directories, check existing stages first to match the pattern.

**Justification:** The entry provides concrete, named directory examples (nat-jobs/, eval-out/, optimizer_results/) and a specific behavioral rule (check existing stages before adding new output dirs) that would meaningfully guide agent decisions about file placement in this project.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.70, 3.1s)
  - The entry provides concrete, named directory examples (nat-jobs/, eval-out/, optimizer_results/) and a specific behavioral rule (check existing stages before adding new output dirs) that would meaningfully guide agent decisions about file placement in this project.

### `7350bebdc6f86fbf`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.40, necessity=0.50

**Original entry:**

> Proponent of good module separation in code organization, even when it differs from existing patterns in the codebase.

**Justification:** The entry captures a meaningful preference (willingness to deviate from existing codebase patterns in favor of proper module separation) that could influence architectural suggestions. It's somewhat vague but specific enough to distinguish this user from one who always follows existing patterns.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.40, necessity=0.50, 4.7s)
  - The entry captures a meaningful preference (willingness to deviate from existing codebase patterns in favor of proper module separation) that could influence architectural suggestions. It's somewhat vague but specific enough to distinguish this user from one who always follows existing patterns.

### `7bb47dba9a7be92c`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.60

**Original entry:**

> Prefers proper tool/API usage over guessing: "please use your skills/mcp server (don't just randomly set stuff)" when working with external systems like NVBugs.

**Justification:** The entry includes a direct quote and names NVBugs as the context, making it specific and retrievable. It signals a concrete user preference that could change agent behavior when deciding whether to use MCP tools versus guessing at system state.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.60, 3.5s)
  - The entry includes a direct quote and names NVBugs as the context, making it specific and retrievable. It signals a concrete user preference that could change agent behavior when deciding whether to use MCP tools versus guessing at system state.

### `7d5cfef6e3046c40`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.85, necessity=0.90

**Original entry:**

> Branch naming convention: `md/<issue-number>-<short-description>`. Prefers `/md` as branch suffix when creating worktrees (not `+md` or other variants).

**Justification:** This entry captures a specific, verifiable naming convention with concrete format (`md/<issue-number>-<short-description>`) and disambiguates a precise preference (`/md` over `+md`), which would directly affect branch and worktree creation decisions if removed.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.85, necessity=0.90, 3.4s)
  - This entry captures a specific, verifiable naming convention with concrete format (`md/<issue-number>-<short-description>`) and disambiguates a precise preference (`/md` over `+md`), which would directly affect branch and worktree creation decisions if removed.

### `81d7a0d390ee897d`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.70

**Original entry:**

> Uses @filename syntax to reference files (e.g., "@RFC-migrate-off-stainless.md"). When user mentions a document by name or reference, ask for location/path rather than searching blindly.

**Justification:** The entry captures a specific syntax pattern (@filename) with a concrete example, and the behavioral guidance (ask for path rather than searching) is actionable and would change agent behavior if removed. Single-session corroboration is the main weakness, but the specificity makes it worth retaining.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.70, 4.1s)
  - The entry captures a specific syntax pattern (@filename) with a concrete example, and the behavioral guidance (ask for path rather than searching) is actionable and would change agent behavior if removed. Single-session corroboration is the main weakness, but the specificity makes it worth retaining.

### `8f83115f4850f5ef`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> Prefers accepting Python tracebacks for rare edge cases (e.g., stat-able but not list-able directories) over defensive TOCTOU permission checks. Values clean error paths for expected failures, tolerates crashes for truly exceptional conditions.

**Justification:** This captures a specific, non-obvious engineering philosophy about error handling trade-offs (TOCTOU checks vs. letting exceptions propagate) that would meaningfully change how the agent structures file-system code suggestions. The concrete example of stat-able but not list-able directories makes it retrievable and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 4.0s)
  - This captures a specific, non-obvious engineering philosophy about error handling trade-offs (TOCTOU checks vs. letting exceptions propagate) that would meaningfully change how the agent structures file-system code suggestions. The concrete example of stat-able but not list-able directories makes it retrievable and actionable.

### `aa59a8b701389ed4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.80

**Original entry:**

> Has extensive experience writing OpenAPI parsers/utils. Previously worked at Gretel where he used OpenAPI Generator and had to hack internals to get good bindings. This background informs his skepticism about off-the-shelf OpenAPI generators.

**Justification:** This entry contains specific named entities (Gretel, OpenAPI Generator) and explains the experiential basis for the user's skepticism about off-the-shelf OpenAPI generators, which would meaningfully affect how the agent frames recommendations in that domain.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.75, necessity=0.80, 3.0s)
  - This entry contains specific named entities (Gretel, OpenAPI Generator) and explains the experiential basis for the user's skepticism about off-the-shelf OpenAPI generators, which would meaningfully affect how the agent frames recommendations in that domain.

### `afee580c9feb00bf`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.90

**Original entry:**

> When writing docstrings and comments, avoid leaking development details: no references to "earlier code", "existing implementations", "coverage gaps", meta-commentary on test suite state, or vestigial wording from removed features. Documentation should describe current behavior cleanly, not expose how it evolved. User will ask to "audit docstrings for leakage" and expects patterns like "the existing X tests" or "closes a coverage gap" to be removed.

**Justification:** This entry provides specific, actionable guidance with concrete examples of prohibited patterns ('the existing X tests', 'closes a coverage gap') and a named task trigger ('audit docstrings for leakage'). It would directly change agent behavior when reviewing or writing documentation, and this type of domain-specific housekeeping rule is unlikely to be covered by a general system prompt.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.80, necessity=0.90, 4.3s)
  - This entry provides specific, actionable guidance with concrete examples of prohibited patterns ('the existing X tests', 'closes a coverage gap') and a named task trigger ('audit docstrings for leakage'). It would directly change agent behavior when reviewing or writing documentation, and this type of domain-specific housekeeping rule is unlikely to be covered by a general system prompt.

### `b287eaa965ce9712`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When evaluating review feedback (like coderabbit comments), prefers to "fan out and get multiple opinions" — have multiple independent reviewers assess each point with different lenses, then synthesize their consensus.

**Justification:** This is a specific, retrievable workflow preference (multi-reviewer synthesis for code review feedback like coderabbit) that would concretely change how the agent responds when asked to evaluate review comments. The named tool (coderabbit) and the described process ('fan out and get multiple opinions') make it specific enough to be actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.8s)
  - This is a specific, retrievable workflow preference (multi-reviewer synthesis for code review feedback like coderabbit) that would concretely change how the agent responds when asked to evaluate review comments. The named tool (coderabbit) and the described process ('fan out and get multiple opinions') make it specific enough to be actionable.

### `bd67f4f43e9c9694`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.60

**Original entry:**

> Identity-shaped prompts ("you are a deliberate collaborator who...") belong at the very top of CLAUDE.md/AGENTS.md, not buried in bullet lists. They set the lens through which all other rules are read. Placement matters: framing at the top establishes character; the same content as rule #7 just gets weighted alongside everything else.

**Justification:** This is specific actionable guidance about file structure (CLAUDE.md/AGENTS.md) with a concrete named location ('top vs rule #7') and a clear rationale about framing effects. It would meaningfully influence how the agent structures identity/character instructions in agent configuration files.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 4.4s)
  - This is specific actionable guidance about file structure (CLAUDE.md/AGENTS.md) with a concrete named location ('top vs rule #7') and a clear rationale about framing effects. It would meaningfully influence how the agent structures identity/character instructions in agent configuration files.

### `c39e32157fe70312`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.90

**Original entry:**

> Assigns Tyler Bray (GitHub: tylersbray, email: tbray@nvidia.com) as reviewer for CLI and agent-related work on NeMo Platform.

**Justification:** This entry contains concrete, named-entity-rich information (GitHub handle, email, domain scope) that would directly change agent behavior when assigning reviewers for CLI/agent work on NeMo Platform. Removing it would cause the agent to miss a specific reviewer assignment.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.90, necessity=0.90, 3.6s)
  - This entry contains concrete, named-entity-rich information (GitHub handle, email, domain scope) that would directly change agent behavior when assigning reviewers for CLI/agent work on NeMo Platform. Removing it would cause the agent to miss a specific reviewer assignment.

### `c793c6c82dacdb5e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.80

**Original entry:**

> Uses marker file pattern for machine-specific config: `touch ~/.config/zsh/.work` on work machines, then conditionally source work config with `[[ -f $ZDOTDIR/.work ]] && source ...`. Prefers this over hostname matching or untracked machine-local files because it's explicit and visible in the repo flow.

**Justification:** Highly specific entry with concrete commands and a named pattern (`touch ~/.config/zsh/.work`, `[[ -f $ZDOTDIR/.work ]] && source ...`), plus an explicit rationale for choosing this approach over alternatives. Would directly inform any zsh config or dotfile advice the agent gives this user.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.90, necessity=0.80, 6.5s)
  - Highly specific entry with concrete commands and a named pattern (`touch ~/.config/zsh/.work`, `[[ -f $ZDOTDIR/.work ]] && source ...`), plus an explicit rationale for choosing this approach over alternatives. Would directly inform any zsh config or dotfile advice the agent gives this user.

### `d78b6a695264b8f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.70

**Original entry:**

> Prefers dropping features entirely when their value proposition weakens rather than maintaining stopgap solutions or adding CLI complexity to preserve them. Applies "re-evaluate dependent features" principle consistently. Example: removed `--model` flag from usage CLI because richer artifact data (trajectory.json) will eventually provide authoritative model identity, avoiding two-sources-of-truth problems.

**Justification:** The entry captures a specific, named design principle with a concrete example (removing `--model` flag, trajectory.json as authoritative source) that would guide future feature-removal decisions. Two-session corroboration and the specific artifact names make this retrievable and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.75, necessity=0.70, 18.5s)
  - The entry captures a specific, named design principle with a concrete example (removing `--model` flag, trajectory.json as authoritative source) that would guide future feature-removal decisions. Two-session corroboration and the specific artifact names make this retrievable and actionable.

### `d79b57fd26ea50c1`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.60

**Original entry:**

> Prefers critical evaluation of automated suggestions (CodeRabbit, linters) — willing to reject suggestions that don't align with actual project config or that introduce unnecessary complexity, even when they come from automated tools.

**Justification:** The entry names a specific tool (CodeRabbit) and captures a meaningful behavioral preference — rejecting automated suggestions that conflict with project config or add unnecessary complexity — which would usefully guide the agent when reviewing or responding to linter/code-review output. It's not purely generic, though it sits at moderate specificity.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 184.1s)
  - The entry names a specific tool (CodeRabbit) and captures a meaningful behavioral preference — rejecting automated suggestions that conflict with project config or add unnecessary complexity — which would usefully guide the agent when reviewing or responding to linter/code-review output. It's not purely generic, though it sits at moderate specificity.

### `e37c64430111426a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When drafting technical content for the user to share with others (team messages, announcements), provide plain editable text rather than trying to match their voice. User explicitly asked for "a couple lines of text that I can edit to sound like me."

**Justification:** This entry captures a specific, quoted user preference that would directly change agent behavior—providing plain editable text instead of polished, voice-matched copy for team-facing content. The direct quote anchors the guidance concretely and it is not obviously covered by system prompt defaults.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 4.6s)
  - This entry captures a specific, quoted user preference that would directly change agent behavior—providing plain editable text instead of polished, voice-matched copy for team-facing content. The direct quote anchors the guidance concretely and it is not obviously covered by system prompt defaults.

### `e85750de7b7fc4fa`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> Prefers canonical specifications to live in language-agnostic artifacts (reviewer prompts, synthesis templates, shell scripts) with each runtime (Claude Code, deepagents-cli) wrapping them with runtime-specific dispatch glue. Reason: keeps substance in one place and isolates runtime quirks, avoiding drift when maintaining parallel implementations in different systems.

**Justification:** This entry captures a specific architectural preference with named systems (Claude Code, deepagents-cli) and named artifact types (reviewer prompts, synthesis templates, shell scripts), making it retrievable and actionable. It would meaningfully change how the agent structures multi-runtime workflows.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 3.3s)
  - This entry captures a specific architectural preference with named systems (Claude Code, deepagents-cli) and named artifact types (reviewer prompts, synthesis templates, shell scripts), making it retrievable and actionable. It would meaningfully change how the agent structures multi-runtime workflows.

### `eb06022f0c6cec7a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.80

**Original entry:**

> When blocked on unmerged dependencies (PRs, branches), prefers to check out the branch in a worktree and start iterating rather than waiting. Wants action over planning delays.

**Justification:** This entry captures a concrete, actionable workflow preference (git worktree checkout of unmerged dependency branches) that would directly change agent behavior when blocked on PRs—specifically choosing to proceed with iteration over waiting. Specific enough to be retrievable and actionable.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.80, 4.9s)
  - This entry captures a concrete, actionable workflow preference (git worktree checkout of unmerged dependency branches) that would directly change agent behavior when blocked on PRs—specifically choosing to proceed with iteration over waiting. Specific enough to be retrievable and actionable.

### `f06b7cf3228f3384`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.70

**Original entry:**

> When evaluating architectural decisions or migration costs, prefers concrete data: LOC counts, file counts, time estimates broken down by work area. Wants "how many can we delete?" answered with measurements, not speculation.

**Justification:** The entry captures a specific, actionable preference—quantitative measurements (LOC, file counts, time estimates) over speculation when evaluating architectural decisions—and includes a direct quote that anchors the signal. It would concretely change how the agent frames migration/cost analyses.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.70, 3.8s)
  - The entry captures a specific, actionable preference—quantitative measurements (LOC, file counts, time estimates) over speculation when evaluating architectural decisions—and includes a direct quote that anchors the signal. It would concretely change how the agent frames migration/cost analyses.

### `f5632decb7fda7e1`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.60

**Original entry:**

> Prefers "easy stuff first" when tackling problems. Will explicitly call out this approach when breaking down work.

**Justification:** This captures a specific, actionable working-style preference (tackling easy tasks first) that would influence how the agent structures and presents work breakdowns. It's reasonably concrete and retrievable, though single-session corroboration makes it tentative.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.60, necessity=0.60, 3.8s)
  - This captures a specific, actionable working-style preference (tackling easy tasks first) that would influence how the agent structures and presents work breakdowns. It's reasonably concrete and retrievable, though single-session corroboration makes it tentative.

### `fb1a3473bef6711a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.50

**Original entry:**

> Treats RFC review feedback as peer input to evaluate, not gospel: "view it through the lens of a peer with whom you might not agree on everything."

**Justification:** The entry captures a specific, quoted attitude toward RFC review feedback that is concrete and retrievable, anchored by a direct quote. It describes a nuanced stance that could influence how the agent frames responses to review feedback, though it doesn't change hard decisions so much as tone and framing.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.70, necessity=0.50, 3.4s)
  - The entry captures a specific, quoted attitude toward RFC review feedback that is concrete and retrievable, anchored by a direct quote. It describes a nuanced stance that could influence how the agent frames responses to review feedback, though it doesn't change hard decisions so much as tone and framing.

### `fe3b38f60055f95f`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.90

**Original entry:**

> When reviewing PRs, user wants to distinguish between issues caused by the PR (net-new) vs issues that were pre-existing on main. Asked explicitly: "Are there any issues created by this PR or are these problems present on the current implementation?"

**Justification:** This entry captures a specific, actionable preference with a direct quote: when reviewing PRs, the agent must distinguish net-new issues from pre-existing ones on main. Without it, the agent would likely not make this distinction unprompted.

**Judge votes:**

- `azure-anthropic-claude-sonnet-4-6` -> `keep` (quality=0.80, necessity=0.90, 4.2s)
  - This entry captures a specific, actionable preference with a direct quote: when reviewing PRs, the agent must distinguish net-new issues from pre-existing ones on main. Without it, the agent would likely not make this distinction unprompted.
