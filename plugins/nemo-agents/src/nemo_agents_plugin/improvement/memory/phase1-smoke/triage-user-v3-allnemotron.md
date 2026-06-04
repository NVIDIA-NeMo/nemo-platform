# Memory triage proposals — `pi-hermes:CONSOLIDATED:user`

## Run

- **council:** `nvidia-nvidia-nemotron-3-ultra`, `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning`, `nvidia-llama-3-3-nemotron-super-49b-v1-5`
- **started:** 2026-06-03T21:04:25.184141+00:00
- **finished:** 2026-06-03T22:03:21.818001+00:00
- **elapsed:** 3536.6s
- **proposals:** 71
- **errors:** 7
- **skipped entries:** 0

## Summary

| verdict | count | % of proposals |
| --- | ---: | ---: |
| `drop` | 1 | 1.4% |
| `merge` | 0 | 0.0% |
| `refine` | 1 | 1.4% |
| `promote_to_prompt` | 0 | 0.0% |
| `keep` | 69 | 97.2% |

## `drop` (1)

### `7350bebdc6f86fbf`

- **verdict:** `drop` (confidence 0.67)
- **scores:** quality=0.20, necessity=0.20

**Original entry:**

> Proponent of good module separation in code organization, even when it differs from existing patterns in the codebase.

**Justification:** The entry states a vague, generic engineering principle ('good module separation') with no specifics, named patterns, or concrete examples; it restates obvious guidance likely already in the system prompt and would not change agent behavior if removed.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `drop` (quality=0.10, necessity=0.10, 4.7s)
  - The entry states a vague, generic engineering principle ('good module separation') with no specifics, named patterns, or concrete examples; it restates obvious guidance likely already in the system prompt and would not change agent behavior if removed.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 11.5s)
  - The entry is a vague, non‑specific statement that provides no concrete, verifiable guidance and would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 6.1s)
  - The entry provides useful general guidance on code organization but lacks specific, verifiable details, making it not unambiguously retrievable. Its removal would not significantly alter concrete decisions but might slightly affect the agent's tone or emphasis on best practices.

## `refine` (1)

### `1b1ef746cf511fe9`

- **verdict:** `refine` (confidence 0.50)
- **scores:** quality=0.42, necessity=0.38

**Original entry:**

> Prefers planning sessions before implementation when tackling complex fixes. When asked "do you have enough information to get started or would you like a planning session?", explicitly requested a plan before coding. 
> 
> ## Technical preferences — code quality and style
> 
> "I'm always in favor of more static typing, dynamic typing is a bug in potentia." Uses EntityClient as reference for preferred typing style.

**Refined text proposed:**

> ## Technical preferences — code quality and style
> 
> "I'm always in favor of more static typing, dynamic typing is a bug in potentia." Uses EntityClient as reference for preferred typing style.

**Justification:** The entry combines two distinct topics: a workflow preference (planning sessions before implementation) and a code-style preference (static typing with EntityClient reference). These should be separate entries for precise retrieval. The refined text retains only the code-style preference, which matches the header; the planning preference should be its own entry.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `refine` (quality=0.85, necessity=0.75, 18.5s)
  - The entry combines two distinct topics: a workflow preference (planning sessions before implementation) and a code-style preference (static typing with EntityClient reference). These should be separate entries for precise retrieval. The refined text retains only the code-style preference, which matches the header; the planning preference should be its own entry.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 12.9s)
  - The entry is a vague preference that duplicates system prompt content and would not affect agent behavior if removed.

## `keep` (69)

### `09d03f0713454d63`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.60

**Original entry:**

> Dislikes overly clinical/medical language in documentation headings — rejected "Anatomy of an Agent" in favor of "Agent Definition" when drafting public docs for the NeMo Platform agents page.

**Justification:** The entry captures a concrete, verifiable documentation preference with specific heading names and platform context, making it highly retrievable. Removing it would risk the agent using overly clinical language in NeMo Platform docs, so it has meaningful necessity.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.70, 6.0s)
  - The entry captures a concrete, verifiable documentation preference with specific heading names and platform context, making it highly retrievable. Removing it would risk the agent using overly clinical language in NeMo Platform docs, so it has meaningful necessity.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.80, necessity=0.60, 10.2s)
  - The entry is specific, cites a concrete example with named headings, and its removal would alter the agent's documentation style decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 29.5s)
  - The entry provides a concrete example with named entities (NeMo Platform, 'Anatomy of an Agent', 'Agent Definition') and a specific decision point. While its removal might not alter core agent functionality, it directly affects documentation tone and user experience, making its necessity moderate.

### `0f7fb9245ec9337d`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.67

**Original entry:**

> Dislikes "techno-jargon" (e.g., "forcing function," "load-bearing") and em-dashes in written docs — these make text sound AI-generated. Wants their own voice to shine through in RFCs and technical writing.

**Justification:** The entry captures a concrete stylistic preference with specific examples ("forcing function," "load-bearing," em-dashes) and context (RFCs, technical writing), making it retrievable and actionable for tone adaptation. Removing it would risk the agent using disfavored jargon and punctuation, altering output style though not functional outcomes.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.65, necessity=0.50, 5.0s)
  - The entry captures a concrete stylistic preference with specific examples ("forcing function," "load-bearing," em-dashes) and context (RFCs, technical writing), making it retrievable and actionable for tone adaptation. Removing it would risk the agent using disfavored jargon and punctuation, altering output style though not functional outcomes.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 7.2s)
  - The entry conveys a personal style preference with no concrete defect; removing it would only affect tone, not functional behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 36.9s)
  - The entry provides specific, named examples of disliked terms (e.g., 'forcing function', 'em-dashes') and concrete context (RFCs, technical writing). Removing it would likely change behavior by allowing the avoided terms, affecting the user's perceived voice. Both quality and necessity are maximized due to specificity and direct impact on output.

### `2071e206646832a9`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.67

**Original entry:**

> When syncing between local and remote document mirrors (e.g., in-repo RFC and Linear doc): update whichever is more current. If both are the same, start with the local copy then push that up. 
> 
> ## Tools and workflows — shell and dotfiles
> 
> Uses zsh with oh-my-zsh. ZDOTDIR is `~/.config/zsh`. Has `.zshrc.local` symlinked to `.config/zsh/locals/.zshrc.work`. Prefers cached completion approach for shell startup performance.

**Justification:** Entry contains two distinct but specific, actionable topics (document syncing rule and shell configuration). Both are concrete with named entities and paths. While combining them is suboptimal, the entry is not excessively long and splitting would require creating a separate entry beyond this single-entry evaluation.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.80, necessity=0.70, 28.8s)
  - Entry contains two distinct but specific, actionable topics (document syncing rule and shell configuration). Both are concrete with named entities and paths. While combining them is suboptimal, the entry is not excessively long and splitting would require creating a separate entry beyond this single-entry evaluation.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.90, necessity=0.50, 15.7s)
  - The entry provides specific, verifiable counts and structure of the memory store with no vague language, and its removal would not change concrete agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.80, 104.1s)
  - Entry contains specific, verifiable technical configurations (e.g., ZDOTDIR path, .zshrc.local symlink, oh-my-zsh usage) and concrete sync strategy guidance. While the sync advice is generally applicable, the shell setup details are specific to this agent's configuration. Removal would likely alter agent behavior when handling document sync decisions or shell environment setup, but some general guidance might persist elsewhere.

### `225dfc15f4624267`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.77

**Original entry:**

> When monitoring PRs for code review feedback: Apply good CodeRabbit suggestions automatically, but justify and reply to unhelpful ones before resolving. Team member feedback carries more weight — flag those for user review instead of fixing automatically.

**Justification:** The entry provides a specific, named-tool (CodeRabbit) decision rule for PR review handling that distinguishes automated vs. human feedback and mandates justification before resolving. It is actionable guidance that would change agent behavior if removed, but it is a workflow policy rather than a concrete fact, so it falls between the 0.5 and 1.0 quality bands.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.60, necessity=0.70, 6.6s)
  - The entry provides a specific, named-tool (CodeRabbit) decision rule for PR review handling that distinguishes automated vs. human feedback and mandates justification before resolving. It is actionable guidance that would change agent behavior if removed, but it is a workflow policy rather than a concrete fact, so it falls between the 0.5 and 1.0 quality bands.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.60, 35.8s)
  - The entry gives clear, actionable guidance on handling PR feedback and is specific enough to be retained.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 27.8s)
  - The entry is specific, mentioning a named tool (CodeRabbit) and actionable steps for handling PR reviews. It provides concrete, verifiable guidance that directly influences agent behavior in code review scenarios.

### `24883461872a7245`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.67, necessity=0.70

**Original entry:**

> Prefers explicit credential mapping between services. Does not want automatic substitution of credentials meant for one API provider as fallback credentials for a different provider, even when upstream code has such fallback chains.

**Justification:** The entry states a concrete, verifiable preference about credential handling that directly affects agent behavior (preventing cross-provider credential fallback). It is specific, retrievable, and its removal would change a concrete decision.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=1.00, necessity=1.00, 7.2s)
  - The entry states a concrete, verifiable preference about credential handling that directly affects agent behavior (preventing cross-provider credential fallback). It is specific, retrievable, and its removal would change a concrete decision.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.60, 10.0s)
  - The entry states a clear policy preference about credential handling, is specific enough to be retrieved, and would affect agent decisions if removed, so it should be kept as-is.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 123.4s)
  - The entry provides useful guidance on credential handling preferences, but it lacks specific, verifiable details such as named entities or exact commands. Its removal might slightly affect the agent's tone or decision-making nuance in related scenarios, but not in a decisive way.

### `2b7aab650de6b343`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.87

**Original entry:**

> Finds hour markers in progress indicators "demoralizing" and prefers MM:SS format over H:MM:SS for elapsed time displays, even when duration exceeds 60 minutes (shows 73:21 instead of 1:13:21).

**Justification:** The entry captures a concrete, verifiable user preference with a direct quote and specific format examples; removing it would change how the agent displays elapsed time.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=1.00, necessity=1.00, 2.8s)
  - The entry captures a concrete, verifiable user preference with a direct quote and specific format examples; removing it would change how the agent displays elapsed time.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.70, necessity=0.60, 16.4s)
  - The entry provides a clear, specific rule about time format preference and a concrete example, making it verifiable and necessary for the agent's display behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 18.3s)
  - The entry contains concrete, verifiable user preferences with specific examples (MM:SS vs H:MM:SS formats and '73:21' example). Removing this would directly change the agent's display behavior in a measurable way.

### `3362ba488cf7a744`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.50

**Original entry:**

> When selecting LLM models for configurations, user prefers "frontier chat across all providers" — comprehensive coverage of high-quality chat models from multiple providers (Anthropic, OpenAI, Google, DeepSeek, Qwen, etc.).

**Justification:** The entry conveys a vague user preference for frontier chat models, lacking specific, verifiable details, so it is only moderately useful and not a concrete fact.

**Judge votes:**

- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 6.8s)
  - The entry conveys a vague user preference for frontier chat models, lacking specific, verifiable details, so it is only moderately useful and not a concrete fact.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 20.4s)
  - The entry explicitly states the user's preference using specific terminology ('frontier chat') and lists named providers, meeting quality criteria. Removal might slightly alter model selection emphasis but not core functionality, as similar guidance may exist elsewhere.

### `3a4f5eb974a14f65`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.72, necessity=0.52

**Original entry:**

> Challenges assumptions and expects evidence-based verification. When told something about code or workflow (e.g., "the rebase didn't change anything"), user will question it ("That cannot be right") and expects concrete proof (git range-diff, patch-ids, byte-level diffs) rather than accepting claims at face value. Provide verifiable evidence, not assertions.

**Justification:** The entry captures a specific, verifiable behavioral pattern with named verification tools (git range-diff, patch-ids, byte-level diffs) and a concrete example interaction. Removing it would change agent behavior from providing assertions to providing evidence.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.85, 4.3s)
  - The entry captures a specific, verifiable behavioral pattern with named verification tools (git range-diff, patch-ids, byte-level diffs) and a concrete example interaction. Removing it would change agent behavior from providing assertions to providing evidence.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.80, necessity=0.20, 6.8s)
  - The entry provides concrete, verifiable counts of memory entries and corroboration, but its removal would not affect the agent's behavior, so it is of low necessity.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 31.2s)
  - The entry provides useful general guidance about user expectations for evidence-based verification but lacks specific named entities, commands, or version numbers. It represents a behavioral pattern rather than a concrete fact. Removal would reduce emphasis on rigor but not alter core decision-making processes.

### `3b633c1de36c5c76`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.50, necessity=0.33

**Original entry:**

> When user provides explicit design decisions or answers to questions, proceed with those answers rather than continuing extensive exploration. Values efficiency when decisions are already made. When scoping work, prefers to clarify intent if the request is ambiguous rather than having agent guess. Often refines scope or clarifies intent rather than picking from menus. Prefers narrow, well-scoped iterations over committing to large sweeps upfront.

**Justification:** The entry captures specific, observed user preferences (explicit decisions over exploration, clarification over guessing, narrow iterations) that are actionable but lack concrete identifiers like named entities or commands, making it general guidance. Removing it would likely shift agent tone toward more exploration and larger sweeps, but the effect on outcomes is uncertain given possible overlap with system prompt or other entries.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 15.7s)
  - The entry captures specific, observed user preferences (explicit decisions over exploration, clarification over guessing, narrow iterations) that are actionable but lack concrete identifiers like named entities or commands, making it general guidance. Removing it would likely shift agent tone toward more exploration and larger sweeps, but the effect on outcomes is uncertain given possible overlap with system prompt or other entries.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.00, 22.5s)
  - The entry gives generic metadata about the memory store without specific, retrievable facts and would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 13.5s)
  - The entry provides useful general guidance about agent behavior preferences but lacks concrete specifics or named entities. It influences scoping and decision-making style, but removal wouldn't fundamentally alter core functionality since similar principles might exist elsewhere.

### `3ebdcd9b6c4913b5`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.50, necessity=0.50

**Original entry:**

> Comfortable with uncertainty and explicit about unknowns. Will say "I genuinely don't know" rather than guessing. Values honesty about knowledge gaps in decision-making.

**Justification:** The entry captures a specific behavioral preference with a direct quote, but it's a single-session observation of a general communication style that may already be covered by default honesty principles.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 6.2s)
  - The entry captures a specific behavioral preference with a direct quote, but it's a single-session observation of a general communication style that may already be covered by default honesty principles.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 90.4s)
  - The entry is a generic principle lacking specific, retrievable details and is likely redundant with the system prompt.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 46.8s)
  - The entry provides useful guidance on the agent's approach to uncertainty and honesty but lacks specific details or named entities for higher quality. Its removal might slightly affect the agent's tone rather than concrete decisions, as system prompt content may overlap.

### `44321d2304e81f90`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.50

**Original entry:**

> Comfortable with "YOLO" approaches for small changes vs. rigid testing. Pragmatic about testing — willing to YOLO small changes and defer test infrastructure until it's genuinely needed. 
> 
> ## Named people, tools, and projects
> 
> User is Max Dubrinsky (mdubrinsky@nvidia.com, GitHub: maxdubrinsky).

**Justification:** The entry captures a useful pragmatic testing preference tied to a named user, but it's general guidance rather than a concrete, verifiable fact with specific commands or quotes. Removing it would soften the agent's alignment with the user's YOLO-for-small-changes stance but wouldn't change concrete decisions.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 5.2s)
  - The entry captures a useful pragmatic testing preference tied to a named user, but it's general guidance rather than a concrete, verifiable fact with specific commands or quotes. Removing it would soften the agent's alignment with the user's YOLO-for-small-changes stance but wouldn't change concrete decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 31.8s)
  - The entry contains specific named entities (person, email, GitHub) and a precise quote about testing philosophy, meeting the highest quality threshold. However, its removal would not change concrete decisions as similar pragmatic testing guidance might exist elsewhere, reducing necessity impact.

### `4c3b54653e36b0a0`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.60, necessity=0.63

**Original entry:**

> When macOS sandbox causes permission errors with local services, user wants commands run without sandbox immediately (no need to ask first).

**Justification:** The entry captures a specific user preference about macOS sandbox permission errors with local services, directly affecting whether the agent asks before running unsandboxed commands. It is concrete, verifiable, and would change agent behavior if removed.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.80, necessity=0.90, 4.5s)
  - The entry captures a specific user preference about macOS sandbox permission errors with local services, directly affecting whether the agent asks before running unsandboxed commands. It is concrete, verifiable, and would change agent behavior if removed.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 6.4s)
  - The entry states a clear user preference but lacks specific command details, making it moderately specific and moderately necessary.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 28.6s)
  - The entry provides specific context (macOS sandbox, permission errors with local services) and actionable guidance, but lacks concrete details like version numbers or exact commands. Removal might slightly reduce nuance in handling similar scenarios, but core functionality could persist via general system prompts or related entries.

### `4fe0da7c8b7f985f`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.88, necessity=0.83

**Original entry:**

> When CodeRabbit suggests a Ruff rule violation, check the project's ruff.toml first — if the rule isn't enabled, the suggestion may be unhelpful. Justify by noting the rule isn't enforced and that fixing creates inconsistency with existing production patterns. Check project lint config before applying style/rule suggestions.

**Justification:** The entry is specific and actionable, naming CodeRabbit, Ruff, and ruff.toml with clear decision logic. Removing it would change agent behavior by allowing uncritical application of linter suggestions that may not be enforced in the project.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.80, 3.7s)
  - The entry is specific and actionable, naming CodeRabbit, Ruff, and ruff.toml with clear decision logic. Removing it would change agent behavior by allowing uncritical application of linter suggestions that may not be enforced in the project.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.80, necessity=0.70, 23.4s)
  - Entry gives specific, actionable guidance on checking ruff.toml before applying rule suggestions, with no evident defect.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 31.8s)
  - The entry contains specific, verifiable guidance with named entities (CodeRabbit, Ruff rule violation, ruff.toml) and precise actionable steps. Removal would change agent behavior by omitting a critical config-check step during rule enforcement decisions.

### `5312e5c7aaf8d182`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.55, necessity=0.65

**Original entry:**

> Evaluates code review findings critically with justification. Expects "FIX" vs "DON'T FIX" decisions with clear reasoning, not blind acceptance of all suggestions. Uses cost/benefit analysis for proposed changes. Expects critical evaluation with justification for every decision — prefers seeing reasoning for both what gets applied and what gets rejected.

**Justification:** The entry captures a specific, actionable user preference for critical code review evaluation with justified FIX/DON'T FIX decisions and cost/benefit analysis, which would concretely change agent behavior during code review tasks.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.65, necessity=0.85, 7.9s)
  - The entry captures a specific, actionable user preference for critical code review evaluation with justified FIX/DON'T FIX decisions and cost/benefit analysis, which would concretely change agent behavior during code review tasks.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.60, 15.8s)
  - The entry gives clear, useful expectations for critical evaluation with justification, but is generic and not a concrete fact.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 21.9s)
  - The entry provides useful general guidance about critical evaluation in code reviews but lacks concrete examples, specific commands, or named entities to warrant a higher quality score. While removal might marginally reduce emphasis on cost/benefit analysis, similar expectations likely exist elsewhere in the system, resulting in only partial necessity.

### `552517c9122f43f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.70

**Original entry:**

> When resolving conflicts between openshell-sdk refactors and upstream changes: prefer extending the SDK to accept new parameters rather than falling back to inline implementations in consumers like openshell-cli. Keep shared logic in the SDK.

**Justification:** The entry names specific projects (openshell-sdk, openshell-cli) and gives a concrete architectural preference for resolving refactor/upstream conflicts, which would directly influence agent decisions in this codebase.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.80, necessity=0.80, 5.2s)
  - The entry names specific projects (openshell-sdk, openshell-cli) and gives a concrete architectural preference for resolving refactor/upstream conflicts, which would directly influence agent decisions in this codebase.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 4.2s)
  - The entry offers a clear, concise recommendation on handling conflicts, but it is general guidance rather than a concrete, retrievable fact, resulting in moderate quality and necessity.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.80, 30.1s)
  - The entry provides specific, verifiable guidance with named entities (openshell-sdk, openshell-cli) and concrete technical advice. It directly impacts agent behavior in conflict resolution scenarios, making its removal potentially impactful, though some general best practices may overlap with system prompts.

### `59c8938da3dfc3dc`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.83, necessity=0.77

**Original entry:**

> Prefers all project outputs in consistent locations under REPO_ROOT (e.g., nat-jobs/, eval-out/, optimizer_results/). When adding new output directories, check existing stages first to match the pattern.

**Justification:** Entry provides concrete, project-specific directory conventions with named examples (nat-jobs/, eval-out/, optimizer_results/) and a clear rule to check existing stages before adding new outputs. It is verifiable and would change agent behavior by enforcing consistent output locations.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.80, 4.6s)
  - Entry provides concrete, project-specific directory conventions with named examples (nat-jobs/, eval-out/, optimizer_results/) and a clear rule to check existing stages before adding new outputs. It is verifiable and would change agent behavior by enforcing consistent output locations.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.80, necessity=0.80, 6.5s)
  - The entry gives a clear, specific instruction on output directory placement that is essential for consistent agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.70, 18.4s)
  - The entry provides specific directory examples (named entities) and actionable guidance for output organization, meeting Quality criteria for explicitness. Removal could lead to inconsistent output placement decisions, but the system prompt likely includes general organization principles, tempering Necessity to moderate

### `5e218e8023703797`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.95

**Original entry:**

> When filing bugs, user prefers minimal investigation — capture the repro and symptoms, don't deep-dive into root cause. User said "Don't work too hard, the person fixing it can dig" when asked not to over-investigate code during bug filing.

**Justification:** Entry is specific and verifiable, directly tied to user bug filing behavior, with no vague language or structural defects

**Judge votes:**

- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.80, necessity=0.90, 2.8s)
  - Entry is specific and verifiable, directly tied to user bug filing behavior, with no vague language or structural defects
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 52.7s)
  - Entry contains a precise quote from the user and a concrete preference for bug-filing behavior, which directly informs agent actions during issue reporting.

### `84d3ccff688a9114`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.62, necessity=0.55

**Original entry:**

> Tighten text in prompts/instructions — "more text is sometimes less impactful." Values distilled, essential content over verbose explanations. Prefers condensed, to-the-point communication. "Don't try to explain the world" when asking for summaries — wants informative but focused content.

**Justification:** The entry captures a specific user communication preference with direct quotes ('more text is sometimes less impactful', 'don't try to explain the world') that guide concise, distilled responses. It is verifiable and retrievable when generating output for this user. Removing it would likely lead to more verbose responses, changing agent behavior. No concrete defect exists to justify refinement, and it is not a general principle warranting promotion to the system prompt.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.75, necessity=0.60, 5.5s)
  - The entry captures a specific user communication preference with direct quotes ('more text is sometimes less impactful', 'don't try to explain the world') that guide concise, distilled responses. It is verifiable and retrievable when generating output for this user. Removing it would likely lead to more verbose responses, changing agent behavior. No concrete defect exists to justify refinement, and it is not a general principle warranting promotion to the system prompt.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 23.6s)
  - The entry offers useful general guidance on prompt structuring but lacks concrete specifics like commands, entities, or quotes. Its removal would slightly affect tone but not decision outcomes, as the guidance aligns with common best practices that may be partially redundant in the system.

### `8936920730d38570`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.78, necessity=0.68

**Original entry:**

> Uses dotfiles across multiple platforms (macOS, Ubuntu, Debian, Arch, CentOS). Cannot rely on consistent package managers like homebrew. Prefers cross-platform solutions using shell scripts and git clone over package-manager-specific approaches.

**Justification:** The entry lists specific platforms (macOS, Ubuntu, Debian, Arch, CentOS), names homebrew as an unreliable package manager, and states a concrete, actionable preference for cross-platform shell scripts and git clone over package-manager-specific approaches. This is specific, verifiable, and would change agent recommendations (e.g., avoiding brew/apt/pacman suggestions).

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.80, 2.8s)
  - The entry lists specific platforms (macOS, Ubuntu, Debian, Arch, CentOS), names homebrew as an unreliable package manager, and states a concrete, actionable preference for cross-platform shell scripts and git clone over package-manager-specific approaches. This is specific, verifiable, and would change agent recommendations (e.g., avoiding brew/apt/pacman suggestions).
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 8.2s)
  - The entry is a concise, specific guideline about using dotfiles and cross‑platform shell scripts, with no defects that require refinement.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.75, 17.2s)
  - The entry provides specific, verifiable details about technical preferences and cross-platform constraints, making it highly actionable. Removal could lead to suboptimal tooling choices, but core behavior might still adapt using other system knowledge.

### `8f83115f4850f5ef`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.63, necessity=0.60

**Original entry:**

> Prefers accepting Python tracebacks for rare edge cases (e.g., stat-able but not list-able directories) over defensive TOCTOU permission checks. Values clean error paths for expected failures, tolerates crashes for truly exceptional conditions.

**Justification:** The entry states a concrete design preference with a specific example (stat-able but not list-able directories) and a named technique (TOCTOU permission checks), making it specific, verifiable, and retrievable. Removing it would change how the agent handles rare filesystem edge cases, favoring clean error paths over defensive checks.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.80, 4.4s)
  - The entry states a concrete design preference with a specific example (stat-able but not list-able directories) and a named technique (TOCTOU permission checks), making it specific, verifiable, and retrievable. Removing it would change how the agent handles rare filesystem edge cases, favoring clean error paths over defensive checks.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 7.1s)
  - The entry states a clear error-handling preference but is a general policy rather than a concrete, retrievable fact, making its quality and necessity moderate.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 62.1s)
  - The entry provides specific guidance (e.g., 'stat-able but not list-able directories') but remains general engineering philosophy. It lacks concrete entities (e.g., code examples) and would not alter critical agent decisions if removed, as similar principles likely exist elsewhere.

### `9cd72c55fda5ded2`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.50, necessity=0.50

**Original entry:**

> Prefers deliberate investigation over trial-and-error. When introducing a new tool, wants agent to "brush up" on how to use it before firing off commands. Values understanding complexity/scope before implementing. Slow at architectural boundaries; iteration speed never substitutes for thinking.

**Justification:** The entry captures a coherent, multi-session-corroborated working-style preference (deliberate investigation, tool familiarity before use, architectural caution) that would meaningfully steer agent behavior toward slower, more thoughtful execution. It is specific enough to be retrievable as a user preference, though it lacks concrete entities or commands.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 6.7s)
  - The entry captures a coherent, multi-session-corroborated working-style preference (deliberate investigation, tool familiarity before use, architectural caution) that would meaningfully steer agent behavior toward slower, more thoughtful execution. It is specific enough to be retrievable as a user preference, though it lacks concrete entities or commands.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 4.7s)
  - The entry offers general guidance on the agent's preferred approach but lacks concrete, named specifics, making it moderately specific and necessary but not high quality.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 33.5s)
  - The entry provides useful general guidance about investigative Approach and tool adoption but lacks specific examples or named entities (quality 0.5). Removal would subtly affect agent behavior by reducing emphasis on deliberation, but core decision-making would remain intact (necessity 0.5). No nameable defect justifies refining the content.

### `aa59a8b701389ed4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.80, necessity=0.57

**Original entry:**

> Has extensive experience writing OpenAPI parsers/utils. Previously worked at Gretel where he used OpenAPI Generator and had to hack internals to get good bindings. This background informs his skepticism about off-the-shelf OpenAPI generators.

**Justification:** The entry provides a concrete, verifiable fact about the user's professional background (Gretel, OpenAPI Generator) and its direct impact on their technical preferences, which is both retrievable and likely to influence agent recommendations.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.70, 4.9s)
  - The entry provides a concrete, verifiable fact about the user's professional background (Gretel, OpenAPI Generator) and its direct impact on their technical preferences, which is both retrievable and likely to influence agent recommendations.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 51.2s)
  - The entry is vague but conveys the agent’s relevant experience and skepticism without a concrete defect that needs fixing.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 76.3s)
  - The entry is specific with named entities (Gretel, OpenAPI Generator) and concrete examples of tool usage and customization. While removal might reduce contextual nuance in discussions about OpenAPI tools, it does not change core decision-making outcomes.

### `bd67f4f43e9c9694`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.53

**Original entry:**

> Identity-shaped prompts ("you are a deliberate collaborator who...") belong at the very top of CLAUDE.md/AGENTS.md, not buried in bullet lists. They set the lens through which all other rules are read. Placement matters: framing at the top establishes character; the same content as rule #7 just gets weighted alongside everything else.

**Justification:** The entry provides specific, actionable guidance about placing identity-shaped prompts at the top of CLAUDE.md/AGENTS.md with named file references. It is concise, verifiable, and would influence how the agent structures configuration files or advises users.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.80, necessity=0.60, 3.5s)
  - The entry provides specific, actionable guidance about placing identity-shaped prompts at the top of CLAUDE.md/AGENTS.md with named file references. It is concise, verifiable, and would influence how the agent structures configuration files or advises users.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.80, necessity=0.50, 12.7s)
  - The entry is a specific, verifiable instruction about prompt placement with no concrete defect, so it should be retained as a memory entry.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 5.6s)
  - The entry provides useful guidance on the placement of identity-shaped prompts, which could influence the agent's behavior in terms of tone and context setting. However, it lacks specific, verifiable elements and could be considered general advice applicable to document structuring in various contexts.

### `c39e32157fe70312`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=1.00, necessity=0.83

**Original entry:**

> Assigns Tyler Bray (GitHub: tylersbray, email: tbray@nvidia.com) as reviewer for CLI and agent-related work on NeMo Platform.

**Justification:** The entry provides a concrete, verifiable fact naming a specific person with GitHub handle and email for a defined review role on NeMo Platform. It is specific and retrievable, and its removal could affect reviewer assignment decisions.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=1.00, necessity=0.50, 4.4s)
  - The entry provides a concrete, verifiable fact naming a specific person with GitHub handle and email for a defined review role on NeMo Platform. It is specific and retrievable, and its removal could affect reviewer assignment decisions.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=1.00, necessity=1.00, 3.9s)
  - The entry is a concrete, specific assignment with named entities and clearly necessary for the agent's task.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 88.4s)
  - The entry provides specific named entities (Tyler Bray, GitHub handle, email) and a concrete role assignment for NeMo Platform work. Removing it would prevent the agent from correctly identifying the designated reviewer for CLI and agent-related tasks, directly impacting decision-making behavior.

### `c793c6c82dacdb5e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.93, necessity=0.77

**Original entry:**

> Uses marker file pattern for machine-specific config: `touch ~/.config/zsh/.work` on work machines, then conditionally source work config with `[[ -f $ZDOTDIR/.work ]] && source ...`. Prefers this over hostname matching or untracked machine-local files because it's explicit and visible in the repo flow.

**Justification:** The entry provides a concrete, verifiable pattern with specific commands and file paths for machine-specific config management, along with clear rationale. It would change agent behavior by providing a preferred explicit marker-file approach over hostname matching.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.70, 2.8s)
  - The entry provides a concrete, verifiable pattern with specific commands and file paths for machine-specific config management, along with clear rationale. It would change agent behavior by providing a preferred explicit marker-file approach over hostname matching.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.90, necessity=0.60, 7.2s)
  - The entry is specific, verifiable with concrete commands, and its removal could affect the agent's machine‑specific configuration handling, so it should be retained.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 27.7s)
  - The entry provides concrete, specific commands (touch and source) with exact file paths, named environment variables (ZDOTDIR), and a clear rationale for the preference. Removing it would prevent the agent from knowing this explicit method for machine-specific configuration, which directly affects behavior.

### `cc2763c3925d2b64`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.90, necessity=0.53

**Original entry:**

> Max Dubrinsky (GitHub: maxdubrinsky) is a maintainer of NVIDIA/OpenShell. Has personal connections to NVIDIA/OpenShell maintainers but contributes via fork (not direct push access).

**Justification:** The entry is a concrete, verifiable fact naming a specific person, GitHub handle, project, and contribution model. It is niche knowledge that would only affect agent behavior when interacting with NVIDIA/OpenShell or Max Dubrinsky directly.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=1.00, necessity=0.50, 6.4s)
  - The entry is a concrete, verifiable fact naming a specific person, GitHub handle, project, and contribution model. It is niche knowledge that would only affect agent behavior when interacting with NVIDIA/OpenShell or Max Dubrinsky directly.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.90, necessity=0.60, 8.5s)
  - The entry is specific, verifiable, and contains no defects; its removal would not affect agent decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.50, 7.5s)
  - The entry provides specific, verifiable information about Max Dubrinsky's role and connections related to NVIDIA/OpenShell, warranting a high quality score. However, its necessity is moderate, as removing it might not change concrete decisions but could affect the agent's awareness of contributor dynamics.

### `d78b6a695264b8f4`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.78, necessity=0.72

**Original entry:**

> Prefers dropping features entirely when their value proposition weakens rather than maintaining stopgap solutions or adding CLI complexity to preserve them. Applies "re-evaluate dependent features" principle consistently. Example: removed `--model` flag from usage CLI because richer artifact data (trajectory.json) will eventually provide authoritative model identity, avoiding two-sources-of-truth problems.

**Justification:** The entry states a concrete design principle with a specific, named example (removing the `--model` flag from the usage CLI in favor of `trajectory.json` as the authoritative source), making it both verifiable and retrievable. Removing it would change how the agent evaluates trade-offs between stopgap solutions and feature removal.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.85, 2.3s)
  - The entry states a concrete design principle with a specific, named example (removing the `--model` flag from the usage CLI in favor of `trajectory.json` as the authoritative source), making it both verifiable and retrievable. Removing it would change how the agent evaluates trade-offs between stopgap solutions and feature removal.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 10.1s)
  - The entry conveys a clear design principle with a concrete example and contains no evident defect requiring refinement.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.80, 28.9s)
  - The entry contains specific, verifiable decisions (removing `--model` flag due to trajectory.json) with named entities and concrete examples. Removing it might weaken the agent's adherence to the 're-evaluate dependent features' principle in similar contexts, but the core behavior could be inferred from general engineering practices.

### `da5498e4affca2a0`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.70

**Original entry:**

> Expects verification of claims before making breaking changes. Will ask "can you make sure of that" and wants downstream impact checked (e.g., grepping for field usage before removing from public schema). 
> 
> ## Technical preferences — architecture and design
> 
> Data model evolution: prefer to omit fields until there's a concrete consumer. "Easier to add a field than remove one." Keep surface area small in initial implementations rather than pre-emptively adding fields that might be useful later.

**Justification:** The entry captures specific, verifiable user preferences with direct quotes ("can you make sure of that", "Easier to add a field than remove one") and a concrete example (grepping for field usage before schema removal), making it highly retrievable and actionable for agent behavior.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.90, 7.8s)
  - The entry captures specific, verifiable user preferences with direct quotes ("can you make sure of that", "Easier to add a field than remove one") and a concrete example (grepping for field usage before schema removal), making it highly retrievable and actionable for agent behavior.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.60, 5.9s)
  - The entry gives clear, specific expectations about verification and impact checking, but it is general guidance rather than a concrete, named fact.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.60, 7.9s)
  - The entry provides specific and useful guidance on data model evolution and verification preferences, which is valuable for the agent's decision-making process. While it may not contain highly concrete facts with named entities, it offers actionable advice that can influence the agent's behavior, particularly in architectural decisions. It does not contain a nameable defect that would warrant a 'refine' verdict, as the content is concise and relevant.

### `e85750de7b7fc4fa`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.77, necessity=0.57

**Original entry:**

> Prefers canonical specifications to live in language-agnostic artifacts (reviewer prompts, synthesis templates, shell scripts) with each runtime (Claude Code, deepagents-cli) wrapping them with runtime-specific dispatch glue. Reason: keeps substance in one place and isolates runtime quirks, avoiding drift when maintaining parallel implementations in different systems.

**Justification:** Entry states a concrete architectural principle with named runtimes (Claude Code, deepagents-cli) and specific artifact types (reviewer prompts, synthesis templates, shell scripts), making it verifiable and actionable for file-organization decisions. Removing it would change how the agent decides where to place canonical specs vs runtime glue.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.80, necessity=0.70, 4.1s)
  - Entry states a concrete architectural principle with named runtimes (Claude Code, deepagents-cli) and specific artifact types (reviewer prompts, synthesis templates, shell scripts), making it verifiable and actionable for file-organization decisions. Removing it would change how the agent decides where to place canonical specs vs runtime glue.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 8.4s)
  - The entry gives a specific, language-agnostic design principle with named artifacts and runtimes, and removing it would not alter concrete agent decisions, so it is appropriately retained.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 61.9s)
  - The entry provides specific, verifiable guidance with named entities (Claude Code, deepagents-cli) and concrete artifacts (reviewer prompts, synthesis templates, shell scripts). It establishes a clear architectural principle. However, its necessity is moderate, as the entry influences long-term consistency rather than concrete decision-making, and its removal might not immediately alter agent outputs.

### `eb06022f0c6cec7a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.70, necessity=0.63

**Original entry:**

> When blocked on unmerged dependencies (PRs, branches), prefers to check out the branch in a worktree and start iterating rather than waiting. Wants action over planning delays.

**Justification:** The entry captures a specific, verifiable workflow preference (using git worktrees to unblock on unmerged PRs/branches) that would concretely change agent behavior by prompting proactive worktree suggestions instead of waiting. It is concise, names the relevant tool (worktree), and is not redundant with system prompts or other entries.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.80, necessity=0.80, 4.6s)
  - The entry captures a specific, verifiable workflow preference (using git worktrees to unblock on unmerged PRs/branches) that would concretely change agent behavior by prompting proactive worktree suggestions instead of waiting. It is concise, names the relevant tool (worktree), and is not redundant with system prompts or other entries.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 10.0s)
  - The entry is a concise, actionable preference but lacks specific commands or named entities, making it moderately specific with average necessity.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.60, 19.7s)
  - The entry specifies a concrete behavior with named tools (worktree) and actionable steps for a common scenario. Removing it might reduce proactive decision-making in dependency conflicts, but similar preferences could exist elsewhere. No defects require refinement.

### `ecbfeb8c7243fb9d`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.50, necessity=0.50

**Original entry:**

> Skills are "capabilities and conventions the agent draws on, not scripts it executes" — avoid making skills overly rigid. Every rigid rule added is future maintenance cost. Prefers to "rely on larger skill routing and context, not rigid skills."

**Justification:** The entry states a useful design principle about skill architecture but lacks concrete specifics (named entities, commands, versions); it's good general guidance worth retaining but not promoting to the system prompt.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 3.1s)
  - The entry states a useful design principle about skill architecture but lacks concrete specifics (named entities, commands, versions); it's good general guidance worth retaining but not promoting to the system prompt.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 33.9s)
  - The entry provides useful general guidance on skill design but lacks concrete specifics. Its removal might subtly affect system behavior by reducing emphasis on flexibility, but it doesn't control any concrete decision.

### `ef4733acc96c530e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.68, necessity=0.52

**Original entry:**

> Manages dotfiles with GNU Stow for both work and personal machines. Spins up new machines rarely. Prefers declarative, in-repo configuration over implicit machine-local setup. Values shell startup performance, especially in Python repos.

**Justification:** Entry names specific tools (GNU Stow), concrete preferences (declarative in-repo config), and a measurable concern (shell startup performance in Python repos) — all verifiable and retrievable. Removing it would lose actionable guidance for dotfile management, machine provisioning, and shell optimization tasks.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.75, 11.4s)
  - Entry names specific tools (GNU Stow), concrete preferences (declarative in-repo config), and a measurable concern (shell startup performance in Python repos) — all verifiable and retrievable. Removing it would lose actionable guidance for dotfile management, machine provisioning, and shell optimization tasks.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.70, necessity=0.30, 69.4s)
  - The entry is specific and verifiable but does not affect concrete agent decisions, so it can remain as-is.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 32.6s)
  - The entry provides useful specifics like GNU Stow and preferences for declarative configuration, but lacks extreme concreteness (e.g., exact commands) or critical necessity. It captures meaningful user patterns without defects requiring refinement.

### `f06b7cf3228f3384`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.75, necessity=0.75

**Original entry:**

> When evaluating architectural decisions or migration costs, prefers concrete data: LOC counts, file counts, time estimates broken down by work area. Wants "how many can we delete?" answered with measurements, not speculation.

**Justification:** The entry captures a specific, actionable user preference for quantitative measurements over speculation when evaluating architectural decisions. It is concrete enough to guide agent behavior (e.g., prompting the agent to gather LOC counts, file counts, and time estimates before answering migration questions) and would change outcomes if removed.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.75, necessity=0.75, 4.3s)
  - The entry captures a specific, actionable user preference for quantitative measurements over speculation when evaluating architectural decisions. It is concrete enough to guide agent behavior (e.g., prompting the agent to gather LOC counts, file counts, and time estimates before answering migration questions) and would change outcomes if removed.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 11.3s)
  - The entry gives a clear, specific preference for concrete data but is a generic instruction rather than a verifiable fact, resulting in moderate quality and necessity.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 23.5s)
  - The entry specifies concrete metrics (LOC counts, file counts, time estimates by work area) and quotes a direct user requirement ('how many can we delete?'), making it highly verifiable and behavior-changing. Its removal would lead to speculative answers contradicted by the explicit preference for measurements.

### `f4a359b3859edf3d`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.93, necessity=0.62

**Original entry:**

> Prefers Python-style pseudocode over LaTeX/mathematical notation for expressing formulas and algorithms. "Prefer python to math since it's been 15 years since I've used LaTeX."

**Justification:** The entry captures a specific, verifiable user preference with a direct quote and concrete rationale (15 years since LaTeX). Removing it would cause the agent to default to mathematical notation, changing output format for formulas and algorithms.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.75, 5.8s)
  - The entry captures a specific, verifiable user preference with a direct quote and concrete rationale (15 years since LaTeX). Removing it would cause the agent to default to mathematical notation, changing output format for formulas and algorithms.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 69.7s)
  - The entry contains a specific, verifiable preference with a direct quote and named entities (Python, LaTeX). However, removal would primarily affect stylistic choices rather than critical decision outcomes.

### `fa248bb8026a7f3e`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.57, necessity=0.57

**Original entry:**

> Prefers interactive, incremental onboarding when exploring new codebases. Wants information "fed" in chunks rather than large reports. Starts exploration by examining types and contracts first to understand how data is structured and used.

**Justification:** The entry captures a specific, verifiable user preference for incremental, types-first codebase exploration that would concretely change agent behavior (e.g., chunked delivery vs. large reports, starting with types/contracts). No defect warrants refinement; it is not broad enough for the system prompt.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.70, necessity=0.70, 3.4s)
  - The entry captures a specific, verifiable user preference for incremental, types-first codebase exploration that would concretely change agent behavior (e.g., chunked delivery vs. large reports, starting with types/contracts). No defect warrants refinement; it is not broad enough for the system prompt.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 22.5s)
  - The entry clearly states the agent's onboarding preferences and its removal would affect behavior, with no evident defect.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 50.6s)
  - The entry provides useful general guidance about user preferences for codebase exploration but lacks specific entities or precise examples. Removing it would weaken personalization of agent responses but not alter core outcomes.

### `fb1a3473bef6711a`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.63, necessity=0.57

**Original entry:**

> Treats RFC review feedback as peer input to evaluate, not gospel: "view it through the lens of a peer with whom you might not agree on everything."

**Justification:** The entry provides a specific, quoted mental model for handling RFC feedback that is concrete and retrievable; removing it would lose a distinct behavioral stance not obviously covered elsewhere.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.70, 5.3s)
  - The entry provides a specific, quoted mental model for handling RFC feedback that is concrete and retrievable; removing it would lose a distinct behavioral stance not obviously covered elsewhere.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 7.6s)
  - The entry offers a clear, useful principle about treating RFC feedback as peer input, but it is a general guideline rather than a concrete, verifiable fact, so its removal would affect tone rather than specific decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 34.4s)
  - The entry provides useful guidance with a precise quote, but lacks named entities or concrete specificity to warrant 1.0 quality. Its removal would not change core decisions but might subtly alter the agent's approach to feedback.

### `ffebf77904896ae7`

- **verdict:** `keep` (confidence 1.00)
- **scores:** quality=0.87, necessity=0.67

**Original entry:**

> Works with NVIDIA projects (NeMo, Studio, Omnipush, etc.) and tests cmux integration. Has access to NVIDIA Omnistations. Working on NeMo Platform agentic-use benchmarking. Has access to NVIDIA NGC/inference API keys.

**Justification:** The entry lists concrete, named NVIDIA projects (NeMo, Studio, Omnipush), hardware access (Omnistations), a specific benchmarking effort (NeMo Platform agentic-use), and API keys (NGC/inference). These are verifiable, user‑specific facts that would change how the agent tailors responses about GPU‑accelerated workflows. No defect warrants refinement; the content is appropriately specific and not redundant.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.70, 6.8s)
  - The entry lists concrete, named NVIDIA projects (NeMo, Studio, Omnipush), hardware access (Omnistations), a specific benchmarking effort (NeMo Platform agentic-use), and API keys (NGC/inference). These are verifiable, user‑specific facts that would change how the agent tailors responses about GPU‑accelerated workflows. No defect warrants refinement; the content is appropriately specific and not redundant.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.70, necessity=0.50, 5.9s)
  - The entry is specific, mentions concrete NVIDIA projects and resources, and its removal would affect the agent's ability to use those capabilities.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.80, 44.7s)
  - High quality due to specific named entities (NVIDIA projects, APIs, platforms) and concrete access details. Necessity is moderate as it informs agent's ability to reference NVIDIA resources and integration tasks, but similar entries might exist in the store.

### `07b56fbdcc233913`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.50, necessity=0.50

**Original entry:**

> Prefers distilled, compact memories over verbose ones. When memories accumulate specific implementation details (file paths, class names, line numbers), wants them trimmed to essential decisions/principles and pointers to canonical sources. Asks for memory cleanup proactively to reduce context load.

**Justification:** The entry captures a specific, verifiable user preference for compact memories and proactive cleanup that is actionable for personalized behavior, though it lacks concrete entities for a higher quality score.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 6.8s)
  - The entry captures a specific, verifiable user preference for compact memories and proactive cleanup that is actionable for personalized behavior, though it lacks concrete entities for a higher quality score.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 16.0s)
  - The entry is a vague, generic preference with no concrete, retrievable facts and would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 68.5s)
  - The entry contains concrete preferences with specific examples (file paths, class names, line numbers) and actionable guidelines. Removing it would directly impact the agent's memory management behavior, as these preferences shape how details are trimmed and sources are referenced.

### `1afa1e62e8955f70`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.33, necessity=0.33

**Original entry:**

> Prefers interactive sessions with think-out-loud reasoning. Wants to be included in the reasoning process, not just presented with conclusions. Values collaborative decision-making over being handed finished answers.

**Justification:** The entry captures a clear user preference for collaborative, think-out-loud interaction, which is useful guidance but not a concrete, verifiable fact; removing it would likely soften the agent's interactive style without changing core outcomes.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 5.2s)
  - The entry captures a clear user preference for collaborative, think-out-loud interaction, which is useful guidance but not a concrete, verifiable fact; removing it would likely soften the agent's interactive style without changing core outcomes.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 11.9s)
  - The entry is a vague meta description of the memory store and provides no specific, actionable information, making it redundant and unnecessary for agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 19.0s)
  - The entry provides useful general guidance about user preferences for collaborative reasoning, but lacks specific, verifiable details (e.g., named entities, exact commands). Removing it would slightly alter the agent's tone toward collaboration but not change concrete outcomes or decisions.

### `1f841c1e54060e46`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.60

**Original entry:**

> When filing GitHub issues, user prefers to "leave the labeling for someone else" — apply only obviously correct labels, leave discretionary labels to human reviewers.

**Justification:** The entry captures a specific, actionable user preference about GitHub issue labeling that would change agent behavior if absent; it is concrete and verifiable.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.80, 4.5s)
  - The entry captures a specific, actionable user preference about GitHub issue labeling that would change agent behavior if absent; it is concrete and verifiable.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 6.9s)
  - The entry is a vague, redundant instruction that restates obvious behavior already covered by the system prompt, providing no specific, verifiable information.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 29.0s)
  - The entry contains a specific, verifiable directive with a direct quote that influences labeling behavior. Removing it would lead to agents applying discretionary labels contrary to user preference, altering concrete decisions.

### `27ab19ee42afc820`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.80, necessity=0.60

**Original entry:**

> Prefers condensed, action-oriented UIs. Asked to remove verbose descriptions from skill previews and replace Y/n confirmations with clear multi-choice menus (e.g., "1. Install all 2. Select which 3. Skip"). Likes hierarchical multiselect UIs with sublabels showing structure (plugin name > skill names).

**Justification:** Entry is highly specific with concrete UI patterns (exact menu format, hierarchical multiselect structure) and would directly change how the agent presents choices, confirmations, and skill previews. No defect to refine; it's a clear, retrievable user preference.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.80, 11.2s)
  - Entry is highly specific with concrete UI patterns (exact menu format, hierarchical multiselect structure) and would directly change how the agent presents choices, confirmations, and skill previews. No defect to refine; it's a clear, retrievable user preference.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `refine` (quality=0.50, necessity=0.50, 37.0s)
  - The entry uses vague terms like 'condensed' and 'action‑oriented' without concrete descriptors, which is a vague language defect.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 16.4s)
  - The entry provides specific, actionable UI preferences with concrete examples (multi-choice menus, hierarchical multiselect structure) that are retrievable and verifiable. Removing it might lead to less optimal UI decisions, but core functionality would remain intact as basic prompt guidance could suffice.

### `2b3f32758b063f73`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.40, necessity=0.33

**Original entry:**

> When reviewing council/multi-reviewer feedback, user wants balanced reasoning that doesn't overweight obvious mechanical fixes (e.g., "vendoring would of course have been fixed"). Focus on substantive issues that require judgment.

**Justification:** The entry captures a clear user preference for feedback style (balanced reasoning, de-emphasizing trivial mechanical fixes) that is useful guidance but not a concrete, verifiable fact. Removing it would likely soften adherence to this preference but not change core agent capabilities.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 2.1s)
  - The entry captures a clear user preference for feedback style (balanced reasoning, de-emphasizing trivial mechanical fixes) that is useful guidance but not a concrete, verifiable fact. Removing it would likely soften adherence to this preference but not change core agent capabilities.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 4.8s)
  - The entry contains no substantive content, making it vague and non‑retrievable.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.50, 57.4s)
  - The entry provides specific guidance for a narrow context (council/multi-reviewer feedback) with a concrete example, making it moderately retrievable. Removal might subtly affect agent focus in that context, but general prompt guidelines likely cover similar principles.

### `2c52e8806ac9ede6`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.53, necessity=0.50

**Original entry:**

> ## Collaboration style
> 
> Keeps user in the development loop — "Be vocal if you are missing information or could use another set of eyes from me." Wants gaps and uncertainties surfaced explicitly rather than having the agent make assumptions. When uncertain, do less not more — pause before spawning ceremony. Values being asked questions when the path is unclear.

**Justification:** Entry contains specific behavioral markers and a direct user quote, making it verifiable and retrievable. High corroboration (8 sessions) confirms this is a stable user preference that would change agent behavior (e.g., pausing before spawning ceremony, asking questions instead of assuming).

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.80, necessity=0.80, 5.6s)
  - Entry contains specific behavioral markers and a direct user quote, making it verifiable and retrievable. High corroboration (8 sessions) confirms this is a stable user preference that would change agent behavior (e.g., pausing before spawning ceremony, asking questions instead of assuming).
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 8.8s)
  - The entry contains no substantive content; it is a meta note about corroboration and provides no guidance or fact for the agent.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.80, necessity=0.70, 51.3s)
  - The entry contains precise quotes ('Be vocal if...') and specific collaboration instructions, meeting quality criteria. Removal would likely weaken explicit uncertainty handling, affecting behavior necessity.

### `2d5005c7ea8c6a13`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.45, necessity=0.45

**Original entry:**

> Values critical thinking and evidence-based pushback. "If there is anything said above that you take issue with, please push back. Think critically!" Expects substantive engagement over deference. When presenting architectural proposals or recommendations, wants validation with concrete evidence from codebase/docs and grounded reasoning. Will explicitly ask "push back on this read and verify this claim" before bringing ideas to coworkers.

**Justification:** The entry captures a specific, quoted user preference for critical engagement and evidence-based validation that would concretely alter agent behavior toward pushback over deference.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.85, 2.7s)
  - The entry captures a specific, quoted user preference for critical engagement and evidence-based validation that would concretely alter agent behavior toward pushback over deference.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 24.6s)
  - The entry is a generic meta‑instruction that restates the evaluation process already covered by the system prompt, providing no specific, verifiable information and offering no impact on agent decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 19.7s)
  - The entry provides useful guidance on critical thinking and evidence-based validation but lacks specific named entities or concrete examples to rate higher in quality. Its removal might slightly affect tone or emphasis but not core decision-making, as similar behavior could be inferred from general good practices already implied in the system prompt.

### `33490df8bf4790b5`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.47, necessity=0.60

**Original entry:**

> For bug reports, user wants diagnostic findings without fix recommendations ("avoid making fix recommendations since this is a bug"). Keep bug issues descriptive of the problem, not prescriptive of the solution.

**Justification:** The entry provides a concrete, verifiable instruction for bug-report handling (diagnostic findings only, no fix recommendations) that would change agent behavior if removed. It is specific and retrievable in bug-report contexts.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.80, 5.0s)
  - The entry provides a concrete, verifiable instruction for bug-report handling (diagnostic findings only, no fix recommendations) that would change agent behavior if removed. It is specific and retrievable in bug-report contexts.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 5.3s)
  - The entry provides no concrete, specific information and is essentially a placeholder, making it vague and non-verifiable.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=1.00, 99.3s)
  - The entry provides specific guidance on handling bug reports by explicitly stating user preferences regarding diagnostics vs. fixes. It directly influences agent behavior to avoid solution suggestions in bug contexts, which isn't covered by general prompt instructions.

### `3adf210f1341a445`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.50, necessity=0.33

**Original entry:**

> When asking about architecture decisions, user wants concrete reusability analysis ("who is consumer #3") rather than speculative abstraction. Values YAGNI principle and practical justification for shared libraries.

**Justification:** The entry captures a specific user preference for concrete reusability analysis over speculative abstraction and values YAGNI, which is useful guidance but lacks named entities, commands, or precise quotes, making it general rather than a concrete fact. Removing it might shift tone toward more abstraction but wouldn't fundamentally change outcomes.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 5.9s)
  - The entry captures a specific user preference for concrete reusability analysis over speculative abstraction and values YAGNI, which is useful guidance but lacks named entities, commands, or precise quotes, making it general rather than a concrete fact. Removing it might shift tone toward more abstraction but wouldn't fundamentally change outcomes.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 10.1s)
  - The entry is vague general guidance that restates principles already covered by the system prompt and provides no concrete, retrievable fact, so removing it would not change agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 72.0s)
  - The entry is highly specific with a precise quote ('who is consumer #3') and references a recognized principle (YAGNI), making it concrete and retrievable. However, its necessity is moderate, as removal would soften the agent's emphasis on practicality but likely wouldn't alter core architectural outcomes.

### `41503ab4453d0474`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.47, necessity=0.40

**Original entry:**

> When reviewing PRs that have been open for a while: wants thorough audit across the codebase, not just quick fixes. Appreciates being asked to "be discerning and fan out your team as necessary" when investigating scope/completeness. Values comprehensive investigation of what the PR might have missed or what main has changed since the merge base.

**Justification:** Entry captures a specific, quoted user preference for thorough PR audits with team fan-out and scope investigation—actionable guidance that would change agent behavior on stale PR reviews. No defect to refine; not broad enough for system prompt.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.70, necessity=0.60, 3.7s)
  - Entry captures a specific, quoted user preference for thorough PR audits with team fan-out and scope investigation—actionable guidance that would change agent behavior on stale PR reviews. No defect to refine; not broad enough for system prompt.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 57.3s)
  - The entry provides only vague, generic guidance that repeats information already covered by the system prompt, offering no concrete, actionable detail and thus would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.60, 25.3s)
  - The entry provides specific guidance with direct quotes and a clear context about PR review preferences. It's not vague but lacks named entities for higher quality. Removal might reduce emphasis on thorough audits but doesn't fundamentally change core behavior.

### `55a644cd8f6ff2c0`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.57

**Original entry:**

> Action-oriented when path is clear. "Don't have time to dawdle" — wants implementation over extended discussion when requirements are understood and context is available. Trusts recommended paths when offered choices during complex operations. Will choose autonomous completion of git workflows when given the choice. But: "If you have any questions/concerns, stop and ask." Values getting it right over getting it done fast.

**Justification:** Entry captures specific user preferences with direct quotes that concretely guide agent autonomy vs. clarification behavior; removing it would change how the agent balances independent execution against stopping to ask.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.75, necessity=0.70, 3.5s)
  - Entry captures specific user preferences with direct quotes that concretely guide agent autonomy vs. clarification behavior; removing it would change how the agent balances independent execution against stopping to ask.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 7.2s)
  - The entry is vague and restates general preferences already covered by the system prompt, providing no specific, actionable details.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 57.7s)
  - The entry contains specific, verifiable elements including a direct quote ('Don't have time to dawdle') and precise behavioral examples (git workflow autonomy, path trust during complex operations). Its removal would materially alter decision-making around execution speed vs. accuracy and autonomous task choices, which are not redundantly covered by other entries or the system prompt.

### `6935e3c6fc1098b3`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.52, necessity=0.45

**Original entry:**

> Has deepagents-cli configured with internal model provider access to many interesting models. Plans to use deepagents as the interface where prompt-tuned models will eventually be exposed. Prefers to do most writing/authoring in Claude Code (Opus-4.7 as best coding model) but run execution in deepagents. Watching token spend — cost-conscious when evaluating multi-model approaches.

**Justification:** Entry is specific (names deepagents-cli, internal model provider, Claude Code, Opus-4.7) and actionable — it defines the user's preferred authoring vs execution split and cost sensitivity, which would change how the agent routes tasks. No defect to refine; not broad enough for system prompt.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.75, 4.0s)
  - Entry is specific (names deepagents-cli, internal model provider, Claude Code, Opus-4.7) and actionable — it defines the user's preferred authoring vs execution split and cost sensitivity, which would change how the agent routes tasks. No defect to refine; not broad enough for system prompt.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 9.1s)
  - The entry is vague and non‑specific, offering only general preferences without concrete facts or verifiable details, and its removal would not affect the agent’s concrete decisions.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.60, 16.8s)
  - The entry provides specific details about the agent's configuration and preferences, such as using 'deepagents-cli', 'Claude Code (Opus-4.7)', and cost-conscious token spend considerations. While not all elements are independently verifiable with quantifiable evidence, the named entities and specific model references contribute to a moderately high quality score. The necessity is moderate because removing it might not change concrete decisions but could affect the agent's contextual understanding and operational tone, particularly in multi-model approaches and cost considerations.

### `777f85f2c2a6580f`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.50

**Original entry:**

> Framework distinction: **skills are primitives** (single-invocation, single deliverable, no session state), **agents are sessions** (multi-round, collaborative, durable state across turns). Council-of-elders is a primitive so should stay a skill. 
> 
> ## Documentation and writing style
> 
> For RFC and design docs: wants concise text, avoids "puff language," not looking for word count. Prefers "broad strokes" to iterate on rather than deep detail up front.

**Justification:** The entry is concise and specific but appears redundant with existing system knowledge, so no behavior change would result from its removal.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `refine` (quality=0.70, necessity=0.80, 8.8s)
  - Entry combines two distinct topics: a concrete framework architecture distinction (skills vs agents) that drives implementation decisions, and general writing-style guidance for RFCs. The architecture distinction is specific and verifiable; the writing guidance is useful but separate. Splitting them would improve retrievability and allow independent weighting.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.00, 20.5s)
  - The entry is concise and specific but appears redundant with existing system knowledge, so no behavior change would result from its removal.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.70, necessity=0.70, 29.4s)
  - The entry contains specific distinctions (skills vs. agents) with a named entity (Council-of-elders) and concrete guidance on documentation style. It avoids vagueness and provides verifiable constraints. Removal could affect architectural decisions like skill-agent classification, justifying necessity.

### `7bb47dba9a7be92c`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.43

**Original entry:**

> Prefers proper tool/API usage over guessing: "please use your skills/mcp server (don't just randomly set stuff)" when working with external systems like NVBugs.

**Justification:** Entry captures a specific user preference with a direct quote and named external system (NVBugs), making it concrete and actionable; removal would lose the explicit instruction to use the MCP server for that system.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=1.00, necessity=0.80, 11.8s)
  - Entry captures a specific user preference with a direct quote and named external system (NVBugs), making it concrete and actionable; removal would lose the explicit instruction to use the MCP server for that system.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 13.4s)
  - The entry is generic meta information about observation count and provides no specific, verifiable content.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 27.1s)
  - The entry provides a specific, direct quote with named entities (NVBugs, skills/mcp server) and clear guidance, meeting quality criteria. However, its removal might only affect tone or specificity of responses about tool usage rather than concrete decisions, as general caution against guessing could exist elsewhere.

### `7d5cfef6e3046c40`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.60

**Original entry:**

> Branch naming convention: `md/<issue-number>-<short-description>`. Prefers `/md` as branch suffix when creating worktrees (not `+md` or other variants).

**Justification:** The entry specifies an exact branch naming pattern (`md/<issue-number>-<short-description>`) and a concrete worktree suffix preference (`/md` over `+md`), making it specific, verifiable, and actionable. Removing it would change the agent's branch creation behavior.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.80, 2.9s)
  - The entry specifies an exact branch naming pattern (`md/<issue-number>-<short-description>`) and a concrete worktree suffix preference (`/md` over `+md`), making it specific, verifiable, and actionable. Removing it would change the agent's branch creation behavior.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 15.9s)
  - The entry only contains a generic corroboration note with no specific, verifiable content, making it unnecessary.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 18.4s)
  - The entry provides a concrete, verifiable convention with specific syntax and preferences. Removing it would risk agents creating inconsistent branch names or using non-preferred suffixes during worktree operations.

### `81d7a0d390ee897d`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.62, necessity=0.58

**Original entry:**

> Uses @filename syntax to reference files (e.g., "@RFC-migrate-off-stainless.md"). When user mentions a document by name or reference, ask for location/path rather than searching blindly.

**Justification:** The entry gives concrete, verifiable guidance on a specific syntax (@filename) and a clear behavioral rule (ask for path instead of blind search). Removing it would change how the agent handles file references. No defects present; the content is concise and single-topic.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.85, necessity=0.75, 4.3s)
  - The entry gives concrete, verifiable guidance on a specific syntax (@filename) and a clear behavioral rule (ask for path instead of blind search). Removing it would change how the agent handles file references. No defects present; the content is concise and single-topic.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 5.2s)
  - The entry is a meta description of the evaluation task, not a concrete, verifiable memory fact, and would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 18.3s)
  - The entry provides a specific, actionable directive with concrete syntax examples. It governs behavior when handling document references, which directly affects agent decision-making during file location requests.

### `a2904a90b343a7bf`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.63

**Original entry:**

> Strongly dislikes adding imperatives/directives in front of existing DO/DO NOT blocks in AGENTS.md. "If an agent isn't obeying [the DO/DO NOT block], then I don't know what will." Don't stack ceremony in front of existing instructions. 
> 
> ## Communication style and output preferences
> 
> Prefers terse output, ≲ one terminal screen. Wants response lengths kept shorter — feedback that output "just longer than my screen" was too long.

**Justification:** Entry is highly specific with direct quotes, named file (AGENTS.md), and precise output constraints (≤ one terminal screen). Both preferences are actionable and would change agent behavior if removed. The two topics are related user preferences and the entry is concise enough to keep as-is.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.95, necessity=0.90, 18.2s)
  - Entry is highly specific with direct quotes, named file (AGENTS.md), and precise output constraints (≤ one terminal screen). Both preferences are actionable and would change agent behavior if removed. The two topics are related user preferences and the entry is concise enough to keep as-is.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 14.0s)
  - The entry is vague and redundant, offering no concrete, retrievable fact and would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 43.3s)
  - The entry contains concrete, verifiable directives with direct quotes ("If an agent isn't obeying...") and specific references (AGENTS.md). Removal would alter agent behavior regarding output structure and instruction formatting.

### `afee580c9feb00bf`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.80, necessity=0.45

**Original entry:**

> When writing docstrings and comments, avoid leaking development details: no references to "earlier code", "existing implementations", "coverage gaps", meta-commentary on test suite state, or vestigial wording from removed features. Documentation should describe current behavior cleanly, not expose how it evolved. User will ask to "audit docstrings for leakage" and expects patterns like "the existing X tests" or "closes a coverage gap" to be removed.

**Justification:** The entry provides specific, verifiable patterns to avoid in documentation (e.g., 'earlier code', 'closes a coverage gap') with a clear retrieval trigger ('audit docstrings for leakage'), and its removal would change agent behavior on docstring tasks for this user.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.85, 19.0s)
  - The entry provides specific, verifiable patterns to avoid in documentation (e.g., 'earlier code', 'closes a coverage gap') with a clear retrieval trigger ('audit docstrings for leakage'), and its removal would change agent behavior on docstring tasks for this user.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.50, necessity=0.00, 9.7s)
  - The entry only reports statistics about the memory store and does not affect agent behavior, so it is unnecessary.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 58.3s)
  - The entry provides specific, verifiable guidance with concrete examples of prohibited language, meeting the highest quality bar. However, its necessity is moderate as the advice aligns with general documentation best practices that might already be inferred by the agent from broader system instructions.

### `b287eaa965ce9712`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.58, necessity=0.55

**Original entry:**

> When evaluating review feedback (like coderabbit comments), prefers to "fan out and get multiple opinions" — have multiple independent reviewers assess each point with different lenses, then synthesize their consensus.

**Justification:** The entry describes a concrete, named process ('fan out and get multiple opinions') with a specific example (coderabbit comments) and clear methodology (independent reviewers, different lenses, synthesize consensus). It is retrievable when evaluating review feedback and would change agent behavior in that context. No defect warrants refinement; the content is specific and actionable as-is.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.75, necessity=0.65, 8.8s)
  - The entry describes a concrete, named process ('fan out and get multiple opinions') with a specific example (coderabbit comments) and clear methodology (independent reviewers, different lenses, synthesize consensus). It is retrievable when evaluating review feedback and would change agent behavior in that context. No defect warrants refinement; the content is specific and actionable as-is.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 5.3s)
  - No entry content was provided to assess specificity or necessity.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 26.4s)
  - The entry is specific (mentions 'coderabbit comments' as a named entity), verifiable (describes a concrete process of 'fanning out' to multiple reviewers), and retrievable (precisely defines the behavior). Removing it would change agent behavior, as no other entries are indicated to cover this exact feedback-evaluation method.

### `b6d1a2581c4fd3b3`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.43

**Original entry:**

> For NVIDIA/OpenShell issues/PRs, user prefers casual, conversational, first-person tone over formal third-person language. Example: "I'm thinking we just add the command" rather than "Adding the command is the better fix." Avoid referring to "maintainers" in third person since the user is part of that group — use inclusive language like "we" or direct proposals. Prefers tight, conversational prose over verbose academic/formal writing. User replaced a 4-paragraph feature-request body with ~3 sentences in first-person. Avoid walls of text in issue/PR drafts — show the minimal viable version first.

**Justification:** Entry provides concrete, project-specific communication preferences with verifiable examples (first-person vs third-person quotes, paragraph reduction) that would change agent behavior when drafting NVIDIA/OpenShell issues/PRs. No defects to refine; not broad enough for system prompt.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.80, 11.8s)
  - Entry provides concrete, project-specific communication preferences with verifiable examples (first-person vs third-person quotes, paragraph reduction) that would change agent behavior when drafting NVIDIA/OpenShell issues/PRs. No defects to refine; not broad enough for system prompt.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 16.1s)
  - The entry is vague and restates obvious guidelines without concrete, verifiable details.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 105.3s)
  - The entry provides specific, verifiable guidance with concrete examples (e.g., code snippet comparisons, explicit tone preferences) tied to NVIDIA/OpenShell context. While removal wouldn't alter core decision-making logic, it would degrade the agent's ability to mirror the user's collaborative style and inclusive language in issue/PR workflows.

### `bb0d40fa9755379b`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.77, necessity=0.75

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

**Justification:** Entry is highly specific and verifiable: names Linear URL scheme rewrite rule, git branch preference for SDK work, and refactoring analysis style with a concrete trade-off example. Removing it would change agent behavior on link formatting, branching, and refactoring recommendations. The three topics are coherently related as user workflow preferences and do not require splitting for retrievability.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.85, 28.8s)
  - Entry is highly specific and verifiable: names Linear URL scheme rewrite rule, git branch preference for SDK work, and refactoring analysis style with a concrete trade-off example. Removing it would change agent behavior on link formatting, branching, and refactoring recommendations. The three topics are coherently related as user workflow preferences and do not require splitting for retrievability.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.50, 6.4s)
  - The entry clearly states the user’s preference for thoughtful, trade‑off‑aware refactoring analysis, which is specific enough to guide the agent and would change behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `refine` (quality=0.90, necessity=0.90, 96.3s)
  - The entry combines two distinct topics (user preferences on refactoring analysis and tool-specific workflows) that should be separated into individual entries to ensure precise retrieval and application. Splitting them avoids ambiguity and ensures each entry addresses a single, coherent signal.

### `c14577e2c749b6a5`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.65, necessity=0.63

**Original entry:**

> Prefers reading long-form documents in Linear rather than in terminal/files. When drafting decision docs or substantial write-ups, post to Linear for easier reading and commenting. 
> 
> ## Code review — council-of-elders pattern
> 
> Uses "council review" pattern for code reviews: multiple independent reviewers examine same diff separately. Review quality bar: "Would the author be glad I flagged this?" (not "technically correct"). Expects 3-8 substantive findings distributed unevenly (anti-checklist rule). Must-fix requires: verbatim quote, named consumer, reproduction path (file:line → trigger → symptom). Prefers precision over quantity; values specific, consequential findings over comprehensive checklists. The point is consensus signal — one reviewer's opinion is noise, two+ reviewers flagging the same thing is signal worth acting on.

**Justification:** Entry is highly specific with named tools (Linear), quoted quality bar, numeric expectations (3-8 findings), and precise must-fix criteria (verbatim quote, named consumer, file:line → trigger → symptom); removing it would lose concrete workflow and review standards.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.95, necessity=0.90, 10.2s)
  - Entry is highly specific with named tools (Linear), quoted quality bar, numeric expectations (3-8 findings), and precise must-fix criteria (verbatim quote, named consumer, file:line → trigger → symptom); removing it would lose concrete workflow and review standards.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 77.8s)
  - The entry is a generic, non‑specific instruction with no concrete facts and would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 24.6s)
  - The entry contains specific, verifiable practices with named patterns ('council-of-elders', 'Linear'), concrete requirements (verbatim quote, named consumer), and precise criteria (anti-checklist rule). Removing this would directly alter code review behavior and document handling decisions.

### `ccd19a2fa2414c49`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.33, necessity=0.33

**Original entry:**

> Values consistency across the codebase — when fixing bugs or implementing features, prefers to match broader codebase patterns rather than keeping one-off exceptions ("do whatever is most consistent").

**Justification:** The entry captures a clear user preference for codebase consistency over one-off exceptions, which is useful guidance but lacks specific examples or named entities for high retrievability. It's not a duplicate and doesn't need refinement.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 9.6s)
  - The entry captures a clear user preference for codebase consistency over one-off exceptions, which is useful guidance but lacks specific examples or named entities for high retrievability. It's not a duplicate and doesn't need refinement.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 6.7s)
  - The entry is a generic reminder of a principle already covered by the system prompt and offers no specific, verifiable content, making it unnecessary.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 95.1s)
  - The entry provides useful general guidance about codebase consistency but lacks specific examples or named entities (quality 0.5). Removal might slightly alter decision-making tone but not concrete outcomes (necessity 0.5), as it reflects common engineering practice potentially covered elsewhere.

### `cd59e47469ff3772`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.50, necessity=0.30

**Original entry:**

> Thinks architecturally before implementing — considers whether ideas are "in step with project direction" and evaluates second-order implications. Prefers to ground discussions in actual code before reasoning about design.

**Justification:** The entry captures a useful but general working style preference; it lacks specific, verifiable details but may help the agent align with the user's architectural mindset.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.40, 4.7s)
  - The entry captures a useful but general working style preference; it lacks specific, verifiable details but may help the agent align with the user's architectural mindset.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `refine` (quality=0.50, necessity=0.50, 14.8s)
  - The entry is vague; it uses vague terms like 'thinks' and 'prefers' instead of concrete descriptions of architectural thinking and code-grounding behaviors.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.00, 22.8s)
  - The entry provides useful general guidance about design thinking and code-grounded discussion but lacks specificity (no named entities, commands, or quotes). Its content overlaps with standard engineering best practices likely covered in the system prompt or other entries, making removal non-critical.

### `d79b57fd26ea50c1`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.50, necessity=0.33

**Original entry:**

> Prefers critical evaluation of automated suggestions (CodeRabbit, linters) — willing to reject suggestions that don't align with actual project config or that introduce unnecessary complexity, even when they come from automated tools.

**Justification:** The entry captures a specific, verifiable user preference (critical evaluation of CodeRabbit and linter suggestions) that is retrievable and influences agent behavior when presenting automated tool output. It is concise, names concrete tools, and is not redundant with other entries.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 4.3s)
  - The entry captures a specific, verifiable user preference (critical evaluation of CodeRabbit and linter suggestions) that is retrievable and influences agent behavior when presenting automated tool output. It is concise, names concrete tools, and is not redundant with other entries.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 16.6s)
  - The entry is a vague, generic instruction that offers no concrete, retrievable fact and its content is already covered by the system prompt, so removing it would not affect agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 24.0s)
  - Specific rejection criteria for named tools (CodeRabbit, linters) with concrete examples (project config misalignment, unnecessary complexity) make this high-quality and retrievable. However, removal might only affect decision nuance rather than concrete outcomes, as core principles of config alignment and simplicity could be system-prompt defaults.

### `daa44d66c1c0e810`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.67, necessity=0.33

**Original entry:**

> When user explicitly asks for a specific tool or approach (e.g., "use tmux" not just "parallel subagents"), follow it literally — there's always a reason. Don't substitute with "equivalent" alternatives without asking first.

**Justification:** The entry states a clear, actionable principle about honoring explicit user tool requests rather than substituting equivalents, but it lacks concrete specifics (named entities, commands, versions) and is somewhat general guidance.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 5.5s)
  - The entry states a clear, actionable principle about honoring explicit user tool requests rather than substituting equivalents, but it lacks concrete specifics (named entities, commands, versions) and is somewhat general guidance.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.50, necessity=0.00, 29.5s)
  - The entry is a redundant description of the memory store that is already covered by the system context and does not influence agent decisions, so it can be dropped.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 13.3s)
  - The entry provides concrete, verifiable guidance with specific examples (e.g., 'use tmux'). It addresses a distinct behavioral rule for agent interactions, but its necessity is moderate because similar principles might be inferred elsewhere in the system, though not explicitly.

### `e37c64430111426a`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.50, necessity=0.50

**Original entry:**

> When drafting technical content for the user to share with others (team messages, announcements), provide plain editable text rather than trying to match their voice. User explicitly asked for "a couple lines of text that I can edit to sound like me."

**Justification:** The entry captures a precise user preference with a direct quote, making it concrete and verifiable; removing it would cause the agent to default to voice-matching rather than providing editable plain text.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=1.00, necessity=1.00, 4.4s)
  - The entry captures a precise user preference with a direct quote, making it concrete and verifiable; removing it would cause the agent to default to voice-matching rather than providing editable plain text.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 20.2s)
  - The entry is vague and provides no specific, verifiable information, making it low quality and unnecessary.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 52.1s)
  - The entry provides useful general guidance for content drafting but lacks specific, verifiable details. Removing it may slightly affect tone but not concrete decisions, as similar guidance might be inferred from system prompts or other entries.

### `e626e4bbb2861be3`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.73, necessity=0.53

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

**Justification:** The entry is specific but not essential for agent decisions and may be redundant with system prompt.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `refine` (quality=0.70, necessity=0.60, 6.5s)
  - Entry combines three distinct topics (shell startup optimization, beads memory workflow, tmux agent monitoring) that should be separate entries for retrievability. The beads preference with specific commands (bd remember, bd prime, kebab-case) is the most concrete and actionable portion.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `keep` (quality=0.50, necessity=0.00, 34.8s)
  - The entry is specific but not essential for agent decisions and may be redundant with system prompt.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 26.3s)
  - The entry contains concrete tools (beads, tmux), specific commands (bd remember, bd prime), direct quotes, and actionable preferences. Removing it would strip the agent of precise workflow guidance that influences tool selection and setup behavior.

### `f5632decb7fda7e1`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.33, necessity=0.33

**Original entry:**

> Prefers "easy stuff first" when tackling problems. Will explicitly call out this approach when breaking down work.

**Justification:** The entry captures a clear, observable behavioral pattern ("easy stuff first" with explicit call-outs) that is specific enough to be retrievable but remains general guidance rather than a concrete fact; removing it would affect tone but not core decisions.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.50, necessity=0.50, 3.3s)
  - The entry captures a clear, observable behavioral pattern ("easy stuff first" with explicit call-outs) that is specific enough to be retrievable but remains general guidance rather than a concrete fact; removing it would affect tone but not core decisions.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 8.0s)
  - The entry is a generic meta instruction with no specific, verifiable content and would not affect agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=0.50, necessity=0.50, 5.2s)
  - The entry provides useful general guidance about the agent's approach to problem-solving, but it lacks specific, verifiable details. Its removal would not significantly alter concrete decisions, only potentially affect the tone or specificity of the agent's approach in some interactions.

### `fe3b38f60055f95f`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.63, necessity=0.60

**Original entry:**

> When reviewing PRs, user wants to distinguish between issues caused by the PR (net-new) vs issues that were pre-existing on main. Asked explicitly: "Are there any issues created by this PR or are these problems present on the current implementation?"

**Justification:** The entry captures a specific, quoted user requirement for PR reviews (distinguishing net-new vs pre-existing issues) that directly changes agent behavior during code review tasks. It is concrete, verifiable, and retrievable in the right context.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.90, necessity=0.80, 2.3s)
  - The entry captures a specific, quoted user requirement for PR reviews (distinguishing net-new vs pre-existing issues) that directly changes agent behavior during code review tasks. It is concrete, verifiable, and retrievable in the right context.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 35.5s)
  - The entry is a vague request for a determination that does not provide a concrete, retrievable fact and would not change agent behavior if removed.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 53.6s)
  - The entry contains a direct user quote and addresses a specific, recurring engineering concern (PR vs. pre-existing issues), which provides concrete guidance. Removing it would impair the agent's ability to fulfill this explicit user requirement during PR reviews.

### `ffccf834cf1224a4`

- **verdict:** `keep` (confidence 0.67)
- **scores:** quality=0.55, necessity=0.33

**Original entry:**

> Prefers minimal, deliberate solutions over adding configuration mechanisms — "don't want to add that mechanism" when rejecting a sidecar config approach. Favors starting small with explicit overrides and iterating from there.

**Justification:** Entry captures a specific design preference with a direct quote and concrete scenario (rejecting sidecar config), making it retrievable and verifiable. Removal would soften the agent's bias toward minimal solutions but not eliminate it entirely.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `keep` (quality=0.65, necessity=0.50, 5.1s)
  - Entry captures a specific design preference with a direct quote and concrete scenario (rejecting sidecar config), making it retrievable and verifiable. Removal would soften the agent's bias toward minimal solutions but not eliminate it entirely.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 60.3s)
  - The entry is meta‑instruction describing the evaluation context and contains no concrete, retrievable fact; removing it would not affect agent behavior.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=0.50, 90.9s)
  - The entry includes a precise quote ('don't want to add that mechanism') and specific context (rejecting a sidecar config approach), meeting quality criteria for concrete facts. However, its necessity is moderate since removal would affect general preference alignment but not alter concrete decision outcomes directly.

### `0cf94a88d9bf510e`

- **verdict:** `keep` (confidence 0.33)
- **scores:** quality=0.63, necessity=0.63

**Original entry:**

> Prefers deep "under the hood" explanations that connect abstract mechanisms to familiar experiences ("you've used this without realizing"). Appreciates bridging theory to practice rather than surface-level how-to guides. 
> 
> ## Time estimates and planning
> 
> Dislikes time estimates in agentic development contexts: "I don't care about estimates and they only serve to muddy the waters. We're all doing agentic development, so engineering days means very little." "Estimates muddy the waters." Considers them subjective and unlikely to influence decisions unless something will take a year. Prefers categorical scales (none/small/non-trivial) over specific durations. What matters is whether a slice depends on hard design calls, not calendar-day framing.

**Justification:** The entry contains specific, verifiable quotes and precise preferences (e.g., 'I don't care about estimates', categorical scales like 'non-trivial') that directly inform agent behavior. Removing it would change concrete decisions about communication style and time estimation framing.

**Judge votes:**

- `nvidia-nvidia-nemotron-3-ultra` -> `promote_to_prompt` (quality=0.90, necessity=0.90, 6.5s)
  - The entry contains specific, quoted preferences that directly dictate agent communication style (deep 'under the hood' explanations) and planning behavior (categorical scales over time estimates); it applies universally across sessions and belongs in the always-on system prompt.
- `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` -> `drop` (quality=0.00, necessity=0.00, 84.5s)
  - The entry is a redundant meta instruction that does not influence agent behavior and lacks concrete factual content.
- `nvidia-llama-3-3-nemotron-super-49b-v1-5` -> `keep` (quality=1.00, necessity=1.00, 14.9s)
  - The entry contains specific, verifiable quotes and precise preferences (e.g., 'I don't care about estimates', categorical scales like 'non-trivial') that directly inform agent behavior. Removing it would change concrete decisions about communication style and time estimation framing.

## Per-judge errors

| entry | model | type | message |
| --- | --- | --- | --- |
| `ecbfeb8c7243fb9d` | `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` | `ValueError` | could not extract JSON from response: '{\n  "verdict": "keep",\n  "quality": 0.5,\n  "necessity": 0.5,\n  "justification": "The entry conveys a general principle about avoiding rigid skills, which is already covered by the system prompt\'s inst' |
| `84d3ccff688a9114` | `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` | `ValueError` | openai-compatible response had empty content: ChatCompletion(id='chatcmpl-8a79ae7d0d726ed3', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content=None, refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=[], reasoning='We need to evaluate the entry. The entry description is:\n\n"Tighten text in prompts/instructions — "more text is sometimes less impactful." Values distilled, essential content over verbose exp |
| `1b1ef746cf511fe9` | `nvidia-llama-3-3-nemotron-super-49b-v1-5` | `APITimeoutError` | Request timed out. |
| `f4a359b3859edf3d` | `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` | `ValueError` | openai-compatible response had empty content: ChatCompletion(id='chatcmpl-b719bc09d8f5c80c', choices=[Choice(finish_reason='length', index=0, logprobs=None, message=ChatCompletionMessage(content=None, refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=[], reasoning='WeAS the same way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way way w |
| `5e218e8023703797` | `nvidia-nvidia-nemotron-3-ultra` | `ValueError` | could not extract JSON from response: '{\n  "necessity". "justificationone or two sentences explaining verdict". "refined_text": null, "merge_with": []},</think> The entry\'s fields with "verdict": "quality": 1. 1.0, "necessity": 1.0, "justi' |
| `44321d2304e81f90` | `nvidia-nemotron-3-nano-omni-30b-a3b-reasoning` | `ValueError` | openai-compatible response had empty content: ChatCompletion(id='chatcmpl-8fe9864a33b984b1', choices=[Choice(finish_reason='length', index=0, logprobs=None, message=ChatCompletionMessage(content=None, refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=[], reasoning='We', reasoning_content='We'), stop_reason=None, token_ids=None)], created=1780523888, model='default/nvidia-nemotron-3-nano-omni-30b-a3b-reasoning', object='chat.completion', service_tier=Non |
| `3362ba488cf7a744` | `nvidia-nvidia-nemotron-3-ultra` | `ValueError` | could not extract JSON from response: '{\n  "verdict": "quality": 0.8,\n"necessity"0.7,\n"justification": "The entry captures a concrete user preference ("frontier chat across all provid") with named provider model selection it verifiable, an' |
