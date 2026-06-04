# Disagreement review — sonnet vs nemotron-nano (Phase 1 smoke)

**Source:** `phase1-smoke/triage-user.json` (71 entries total, 40 disagreements between sonnet and nano)

**Goal:** for each entry, decide which hypothesis is winning:

1. The prompt is the problem (Nano reads `refine` more liberally than Sonnet)
2. Nano hallucinates problems (its refines are diff-for-diff, not real improvements)
3. Sonnet under-engages (Nano is catching real issues Sonnet misses)

Pick **one** per entry. Add notes for any pattern you spot.

## Disagreement shapes

| sonnet              | nemotron-nano       | count |
| ------------------- | ------------------- | ----: |
| `keep`              | `refine`            |    24 |
| `promote_to_prompt` | `refine`            |     5 |
| `refine`            | `keep`              |     4 |
| `drop`              | `refine`            |     3 |
| `keep`              | `promote_to_prompt` |     2 |
| `refine`            | `promote_to_prompt` |     2 |

---

## Group: sonnet `keep` vs nemotron-nano `refine` (24)

### Entry 1 / 40 — `bd67f4f43e9c` (council aggregate: `keep`)

**Original:**

> Identity-shaped prompts ("you are a deliberate collaborator who...") belong at the very top of CLAUDE.md/AGENTS.md, not buried in bullet lists. They set the lens through which all other rules are read. Placement matters: framing at the top establishes character; the same content as rule #7 just gets weighted alongside everything else.

**sonnet** -> `keep` (q=0.75, n=0.70)

- Entry provides specific, actionable guidance about document structure: identity-shaped prompts belong at the top of CLAUDE.md/AGENTS.md, not in bullet lists. This is concrete enough to guide document organization decisions and explains the 'why' (framing vs. rule-weighting), making it retrievable and behaviorally relevant for agent configuration work.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry offers useful guidance on positioning identity‑shaped prompts but lacks precise wording and could be clarified.
- _Proposed refined text:_
  > Place identity‑shaped prompts (e.g., "You are a deliberate collaborator who...") at the very top of CLAUDE.md/AGENTS.md, before any bullet lists, to establish character upfront and ensure proper weighting of these rules.

**kimi** -> `keep` (q=0.80, n=0.70) — Entry gives specific structural guidance tied to named files (CLAUDE.md/AGENTS.md) with a clear rationale for top-of-file placement of identity prompts. Its removal would change concrete formatting decisions when the agent authors or edits these documents.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [x] toss-up (either is defensible)

**Hypothesis vote**: other

**Notes:**

I agree that the `keep` result is correct, but I appreciate somewhat how nano condensed it. One of my concerns about those files are them getting too big, so if we can get the same result with less text, I'm all in. Maybe this deserves its own bit of research.

---

### Entry 2 / 40 — `1afa1e62e895` (council aggregate: `keep`)

**Original:**

> Prefers interactive sessions with think-out-loud reasoning. Wants to be included in the reasoning process, not just presented with conclusions. Values collaborative decision-making over being handed finished answers.

**sonnet** -> `keep` (q=0.60, n=0.70)

- This entry captures a specific interaction preference that would materially affect agent behavior (showing reasoning vs. hiding it). While not maximally concrete, it's actionable enough to change how responses are structured. The preference for collaborative decision-making is verifiable through interaction style.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry expresses a clear but generic preference for interactive, collaborative reasoning and should be refined for precision.
- _Proposed refined text:_
  > Prefers interactive sessions that use think-out-loud reasoning, actively involve the user in the reasoning process, and favor collaborative decision-making rather than delivering finished answers without explanation.

**kimi** -> `keep` (q=0.50, n=0.50) — Captures a distinct interaction preference that would meaningfully shift agent style toward collaborative, expository reasoning. Reasonably retrievable though it lacks domain or situational specificity.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [x] toss-up (either is defensible)

**Hypothesis vote**: other

**Notes:**

Like the previous entry, `keep` would be correct but the `refine` version is cleaner. How heaviliy do we need to optimize this?

---

### Entry 3 / 40 — `2b7aab650de6` (council aggregate: `keep`)

**Original:**

> Finds hour markers in progress indicators "demoralizing" and prefers MM:SS format over H:MM:SS for elapsed time displays, even when duration exceeds 60 minutes (shows 73:21 instead of 1:13:21).

**sonnet** -> `keep` (q=0.85, n=0.90)

- This is a highly specific UI preference with concrete examples (73:21 vs 1:13:21) that would directly change how the agent formats time displays in progress indicators. The preference is verifiable and actionable, with clear emotional context ('demoralizing') that explains the rationale.

**nano** -> `refine` (q=0.60, n=0.30)

- The observation is specific enough to be meaningful but could be clearer in phrasing and formatting.
- _Proposed refined text:_
  > Prefer displaying elapsed time in MM:SS format rather than H:MM:SS, even for durations over 60 minutes (e.g., shows 73:21 instead of 1:13:21), and finds hour markers in progress indicators demoralizing.

**kimi** -> `keep` (q=0.90, n=0.90) — The entry records a precise, actionable display preference tied to a specific emotional trigger ('demoralizing') and includes an exact formatting example, making it highly retrievable and behavior-changing when the agent renders elapsed time.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [x] both wrong (real verdict: `drop`)
- [ ] toss-up (either is defensible)

**Hypothesis vote**: other

**Notes:**

This probably should be dropped since it was from a specific project experience. We were showing a full HH:MM:SS timestamp in a progress indicator that should never reach the 60 minute mark (in fact it would time out long before that). I was being glib with the agent and should not have said "demoralizing" since it was almost certainly going to pick up on that as a learning. Not sure if we can incorporate a signal for "this was a specific experience that doesn't hold relevance in the larger picture".

---

### Entry 4 / 40 — `552517c9122f` (council aggregate: `keep`)

**Original:**

> When resolving conflicts between openshell-sdk refactors and upstream changes: prefer extending the SDK to accept new parameters rather than falling back to inline implementations in consumers like openshell-cli. Keep shared logic in the SDK.

**sonnet** -> `keep` (q=0.75, n=0.85)

- This entry provides specific architectural guidance for a concrete codebase (openshell-sdk and openshell-cli) with a clear decision rule: extend the SDK rather than implement inline in consumers. It's retrievable when working on these specific projects and would meaningfully change design decisions if absent.

**nano** -> `refine` (q=0.60, n=0.50)

- The guidance is specific to extending the SDK rather than inlining logic, but it could be clearer and more precise.
- _Proposed refined text:_
  > When reconciling open-shell-sdk refactorings with upstream changes, extend the SDK to accept new parameters instead of implementing them inline in consumers like openshell-cli, and keep shared logic within the SDK.

**kimi** -> `keep` (q=0.65, n=0.55) — Specific project-level architectural rule tied to named entities (openshell-sdk, openshell-cli) that would steer concrete conflict-resolution decisions, yet it is prescriptive guidance rather than an unambiguous fact.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [x] both wrong (real verdict: `promote_to_prompt`)
- [ ] toss-up (either is defensible)

**Hypothesis vote:** prompt

**Notes:**

This is a good example of a project-specific memory that we probably don't want to store at the top-level USER.md memory. I'm thinking we might want to refine the prompt a bit here to escape-hatch to the driver for input here.

---

### Entry 5 / 40 — `3adf210f1341` (council aggregate: `keep`)

**Original:**

> When asking about architecture decisions, user wants concrete reusability analysis ("who is consumer #3") rather than speculative abstraction. Values YAGNI principle and practical justification for shared libraries.

**sonnet** -> `keep` (q=0.65, n=0.75)

- This entry captures a specific user preference about architecture discussions - demanding concrete evidence for abstraction decisions rather than theoretical benefits. The YAGNI reference and concrete example ('who is consumer #3') make it actionable enough to influence how the agent frames architectural recommendations, though it could be slightly more specific about contexts where this applies.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry conveys a useful user intent but is phrased generally; refining it will make the requirement clearer for retrieval and application.
- _Proposed refined text:_
  > When discussing architecture decisions, the user explicitly requests a concrete reusability analysis identifying the particular consumer (e.g., consumer #3) and expects a practical justification for shared libraries, adhering to YAGNI and avoiding speculative abstraction.

**kimi** -> `keep` (q=0.80, n=0.80) — The entry contains a precise user quote ('who is consumer #3') and explicitly names the YAGNI principle, making it specific and retrievable, while its removal would change concrete architecture decisions regarding shared libraries.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [x] toss-up (either is defensible)

**Hypothesis vote**: other

**Notes:**

Either really feels fine, I'd be curious if nano keeps trying to refine it.

---

### Entry 6 / 40 — `f06b7cf3228f` (council aggregate: `keep`)

**Original:**

> When evaluating architectural decisions or migration costs, prefers concrete data: LOC counts, file counts, time estimates broken down by work area. Wants "how many can we delete?" answered with measurements, not speculation.

**sonnet** -> `keep` (q=0.70, n=0.80)

- This entry captures a specific, actionable preference for data-driven decision-making with concrete examples (LOC counts, file counts, time estimates). It's retrievable when architectural or migration discussions arise and would meaningfully change agent behavior by prompting quantitative analysis rather than qualitative speculation.

**nano** -> `refine` (q=0.50, n=0.30)

- The guidance is useful but somewhat vague and not uniquely retrievable. It can be sharpened to be more actionable.
- _Proposed refined text:_
  > When assessing architectural decisions or migration costs, rely on concrete metrics such as lines of code, file counts, and task‑by‑task time estimates; answer how many can we delete? with measured numbers rather than speculation.

**kimi** -> `keep` (q=0.70, n=0.70) — Captures a distinct, domain-specific preference for quantitative metrics in architectural and migration discussions with concrete examples, making it actionable and retrievable.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 7 / 40 — `e85750de7b7f` (council aggregate: `keep`)

**Original:**

> Prefers canonical specifications to live in language-agnostic artifacts (reviewer prompts, synthesis templates, shell scripts) with each runtime (Claude Code, deepagents-cli) wrapping them with runtime-specific dispatch glue. Reason: keeps substance in one place and isolates runtime quirks, avoiding drift when maintaining parallel implementations in different systems.

**sonnet** -> `keep` (q=0.75, n=0.85)

- This entry captures a specific architectural pattern with concrete examples (reviewer prompts, synthesis templates, shell scripts) and named runtimes (Claude Code, deepagents-cli). It would directly influence decisions about where to place specifications and how to structure multi-runtime systems, making it actionable and necessary.

**nano** -> `refine` (q=0.50, n=0.50)

- Provides useful architectural guidance but is ambiguous and could affect several implementations, so we need clarification.
- _Proposed refined text:_
  > Prefers canonical specifications to be stored in language-agnostic artifacts such as reviewer prompts, synthesis templates, and shell scripts. Each runtime (e.g., Claude Code, deepagents-cli) should wrap these specifications with runtime-specific dispatch code to isolate quirks and avoid duplication.

**kimi** -> `keep` (q=0.75, n=0.65) — It names specific runtimes (Claude Code, deepagents-cli) and artifact types, capturing a concrete architectural preference with rationale that would steer how the agent organizes specifications across multiple systems.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 8 / 40 — `777f85f2c2a6` (council aggregate: `keep`)

**Original:**

> Framework distinction: **skills are primitives** (single-invocation, single deliverable, no session state), **agents are sessions** (multi-round, collaborative, durable state across turns). Council-of-elders is a primitive so should stay a skill.
>
> ## Documentation and writing style
>
> For RFC and design docs: wants concise text, avoids "puff language," not looking for word count. Prefers "broad strokes" to iterate on rather than deep detail up front.

**sonnet** -> `keep` (q=0.75, n=0.85)

- Entry contains specific architectural distinctions (skills vs agents, council-of-elders classification) and concrete documentation preferences (concise text, no puff language, broad strokes). These are actionable guidance that would affect design decisions and writing style, not generic preferences.

**nano** -> `refine` (q=0.50, n=0.60)

- Clear conceptual distinction but could be expressed more concisely and without markup.
- _Proposed refined text:_
  > Treat Council-of-elders as a skill (primitive, single-invocation, no state); agents are multi-turn sessions with durable state.

**kimi** -> `keep` (q=0.70, n=0.60) — Contains two specific, actionable signals—an architectural distinction with named entity 'Council-of-elders' and distinctive writing-style preferences ('puff language,' 'broad strokes')—that would measurably change agent output if removed.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 9 / 40 — `0f7fb9245ec9` (council aggregate: `keep`)

**Original:**

> Dislikes "techno-jargon" (e.g., "forcing function," "load-bearing") and em-dashes in written docs — these make text sound AI-generated. Wants their own voice to shine through in RFCs and technical writing.

**sonnet** -> `keep` (q=0.75, n=0.85)

- This entry contains specific, actionable writing preferences with concrete examples ("forcing function," "load-bearing," em-dashes) that would directly influence how the agent drafts technical documents. The specificity of disliked terms and punctuation makes it highly retrievable and likely to change agent behavior when writing RFCs or documentation.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry expresses a clear stylistic preference but is somewhat generic, needing clearer articulation.
- _Proposed refined text:_
  > Rejects techno‑jargon such as "forcing function" or "load‑bearing" and avoids em‑dashes, to ensure RFCs and technical docs reflect an authentic human voice.

**kimi** -> `keep` (q=0.70, n=0.80) — The entry gives concrete examples of disliked jargon and punctuation, tied to specific document types (RFCs, technical writing), making it actionable and retrievable. Without it, the agent would likely use those exact phrasings and stylistic choices.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 10 / 40 — `09d03f071345` (council aggregate: `keep`)

**Original:**

> Dislikes overly clinical/medical language in documentation headings — rejected "Anatomy of an Agent" in favor of "Agent Definition" when drafting public docs for the NeMo Platform agents page.

**sonnet** -> `keep` (q=0.85, n=0.65)

- This entry captures a specific, verifiable preference with concrete examples (rejected 'Anatomy of an Agent' for 'Agent Definition'). It represents a documented stylistic decision that could influence future documentation choices, though its impact is limited to tone and word choice rather than functional outcomes.

**nano** -> `refine` (q=0.90, n=0.50)

- The entry records a clear stylistic preference, but it could be phrased more precisely to capture the rule.
- _Proposed refined text:_
  > Prefer non‑clinical headings (e.g., "Agent Definition" instead of "Anatomy of an Agent") for public documentation of NeMo Platform agents.

**kimi** -> `keep` (q=0.85, n=0.70) — Concrete stylistic preference backed by exact rejected and accepted headings and the named NeMo Platform project; removing it would risk repeating the disliked clinical phrasing in future documentation tasks.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 11 / 40 — `afee580c9feb` (council aggregate: `keep`)

**Original:**

> When writing docstrings and comments, avoid leaking development details: no references to "earlier code", "existing implementations", "coverage gaps", meta-commentary on test suite state, or vestigial wording from removed features. Documentation should describe current behavior cleanly, not expose how it evolved. User will ask to "audit docstrings for leakage" and expects patterns like "the existing X tests" or "closes a coverage gap" to be removed.

**sonnet** -> `keep` (q=0.75, n=0.85)

- This entry captures a specific, actionable user preference with concrete examples of patterns to avoid ('earlier code', 'existing implementations', 'coverage gaps', 'closes a coverage gap') and includes a retrieval trigger phrase ('audit docstrings for leakage'). It describes behavior that would not be obvious from general engineering principles and would likely change the agent's concrete editing decisions when reviewing documentation.

**nano** -> `refine` (q=0.60, n=0.50)

- Provides useful guidance on avoiding docstring leakage but is somewhat generic; a clearer formulation will improve compliance.
- _Proposed refined text:_
  > When writing docstrings and comments, avoid mentioning earlier code, existing implementations, coverage gaps, test‑suite meta‑commentary, or remnants of removed features. Describe only the current behavior.

**kimi** -> `keep` (q=0.80, n=0.75) — Captures a specific user workflow with a concrete trigger phrase ('audit docstrings for leakage') and precise examples of prohibited patterns ('closes a coverage gap', 'existing X tests'), making it highly actionable and retrievable.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 12 / 40 — `33490df8bf47` (council aggregate: `keep`)

**Original:**

> For bug reports, user wants diagnostic findings without fix recommendations ("avoid making fix recommendations since this is a bug"). Keep bug issues descriptive of the problem, not prescriptive of the solution.

**sonnet** -> `keep` (q=0.75, n=0.85)

- This entry captures a specific, actionable user preference about bug report formatting with a direct quote. It would materially change agent behavior by preventing solution suggestions in bug contexts, which differs from general problem-solving instructions.

**nano** -> `refine` (q=0.60, n=0.30)

- The instruction is useful but somewhat generic and could be clarified for consistent application.
- _Proposed refined text:_
  > When handling bug reports, output only diagnostic findings and avoid any fix recommendations or solution suggestions.

**kimi** -> `keep` (q=0.80, n=0.80) — Entry captures a precise, quoted user instruction about bug-report style that would directly change agent output if removed; it is concrete and not obviously duplicated.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 13 / 40 — `1f841c1e5406` (council aggregate: `keep`)

**Original:**

> When filing GitHub issues, user prefers to "leave the labeling for someone else" — apply only obviously correct labels, leave discretionary labels to human reviewers.

**sonnet** -> `keep` (q=0.75, n=0.80)

- This is a specific, actionable preference about GitHub workflow behavior that would directly change how the agent labels issues. The preference is clear and verifiable, though it could be slightly more precise about what constitutes 'obviously correct' vs 'discretionary' labels.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry captures a useful user preference but is vague and could be clarified.
- _Proposed refined text:_
  > When filing GitHub issues, apply only obviously correct labels and defer discretionary labeling to human reviewers.

**kimi** -> `keep` (q=0.70, n=0.80) — This is a specific, behavioral preference about GitHub issue labeling that would change concrete decisions the agent makes. It is clearly scoped and retrievable.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 14 / 40 — `b6d1a2581c4f` (council aggregate: `keep`)

**Original:**

> For NVIDIA/OpenShell issues/PRs, user prefers casual, conversational, first-person tone over formal third-person language. Example: "I'm thinking we just add the command" rather than "Adding the command is the better fix." Avoid referring to "maintainers" in third person since the user is part of that group — use inclusive language like "we" or direct proposals. Prefers tight, conversational prose over verbose academic/formal writing. User replaced a 4-paragraph feature-request body with ~3 sentences in first-person. Avoid walls of text in issue/PR drafts — show the minimal viable version first.

**sonnet** -> `keep` (q=0.85, n=0.75)

- Highly specific guidance for NVIDIA/OpenShell context with concrete examples of preferred tone ('I'm thinking we just add' vs 'Adding the command is the better fix'), actionable rules (avoid 'maintainers' in third person, use 'we'), and verifiable behavioral change (replacing 4-paragraph text with ~3 sentences). This would meaningfully alter agent output in this specific repository context.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry offers useful style guidance but is wordy and could be clarified.
- _Proposed refined text:_
  > For NVIDIA/OpenShell issues/PRs, use a casual first-person tone and inclusive language like "we" (e.g., "I think we should add the command") instead of formal third‑person phrasing. Keep it concise and avoid lengthy prose.

**kimi** -> `keep` (q=0.90, n=0.80) — Contains named repository context, precise preferred/dispreferred language examples, and concrete drafting behavior; removing it would cause the agent to revert to a more formal, verbose default style for issues/PRs.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 15 / 40 — `eb06022f0c6c` (council aggregate: `keep`)

**Original:**

> When blocked on unmerged dependencies (PRs, branches), prefers to check out the branch in a worktree and start iterating rather than waiting. Wants action over planning delays.

**sonnet** -> `keep` (q=0.70, n=0.75)

- This entry captures a specific behavioral preference about handling blocked work - using worktrees to work on unmerged dependencies rather than waiting. It's actionable and would influence concrete decisions about workflow when encountering blocked PRs/branches. The mention of 'worktree' as the specific solution makes it retrievable and verifiable.

**nano** -> `refine` (q=0.55, n=0.35)

- Specific enough for retrieval but can be phrased more succinctly for broader use.
- _Proposed refined text:_
  > When stalled by unmerged dependencies, checkout the relevant branch in a worktree and iterate rather than pause.

**kimi** -> `keep` (q=0.50, n=0.60) — Captures a specific workflow preference for using git worktrees when blocked on dependencies, which would change the agent's concrete recommendation rather than defaulting to waiting, though it lacks specific commands or project context.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 16 / 40 — `8936920730d3` (council aggregate: `keep`)

**Original:**

> Uses dotfiles across multiple platforms (macOS, Ubuntu, Debian, Arch, CentOS). Cannot rely on consistent package managers like homebrew. Prefers cross-platform solutions using shell scripts and git clone over package-manager-specific approaches.

**sonnet** -> `keep` (q=0.75, n=0.85)

- This entry contains specific, actionable constraints (multiple named platforms, explicit preference for shell scripts and git clone over package managers) that would directly influence tool recommendations and implementation approaches. The cross-platform requirement and package manager limitation are concrete facts that would change agent behavior when suggesting dotfile management solutions.

**nano** -> `refine` (q=0.50, n=0.60)

- The entry gives useful cross‑platform advice but is vague and could be made more concrete.
- _Proposed refined text:_
  > When managing dotfiles across macOS, Ubuntu, Debian, Arch, and CentOS, avoid reliance on platform‑specific package managers; instead, use shell scripts and git‑based tools (e.g., chezmoi, Homeshick) to clone and provision configurations.

**kimi** -> `keep` (q=0.70, n=0.80) — Captures specific cross-platform constraints and explicit toolchain preferences that would change concrete installation and setup recommendations across macOS, Ubuntu, Debian, Arch, and CentOS.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 17 / 40 — `c793c6c82dac` (council aggregate: `keep`)

**Original:**

> Uses marker file pattern for machine-specific config: `touch ~/.config/zsh/.work` on work machines, then conditionally source work config with `[[ -f $ZDOTDIR/.work ]] && source ...`. Prefers this over hostname matching or untracked machine-local files because it's explicit and visible in the repo flow.

**sonnet** -> `keep` (q=0.95, n=0.85)

- Highly specific technical detail with concrete commands, file paths, and a clear pattern preference. This describes a non-obvious configuration choice that would directly influence how the agent helps configure shell environments for multi-machine setups.

**nano** -> `refine` (q=1.00, n=0.50)

- The entry gives a concrete, retrievable technique but could be clearer and more explicit about the preferred pattern.
- _Proposed refined text:_
  > Prefer using an explicit marker file `~/.config/zsh/.work` to flag a work machine; source work‑specific config via `[[ -f $ZDOTDIR/.work ]] && source $ZDOTDIR/.work` rather than hostname matching or untracked local files, because this is visible in version control.

**kimi** -> `keep` (q=0.90, n=0.80) — Contains exact commands, paths, and rationale for a specific dotfiles workflow; losing it would lead the agent to suggest hostname matching or other alternatives instead.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 18 / 40 — `59c8938da3df` (council aggregate: `keep`)

**Original:**

> Prefers all project outputs in consistent locations under REPO_ROOT (e.g., nat-jobs/, eval-out/, optimizer_results/). When adding new output directories, check existing stages first to match the pattern.

**sonnet** -> `keep` (q=0.75, n=0.70)

- Entry provides specific, actionable guidance with concrete examples (nat-jobs/, eval-out/, optimizer_results/) that establishes a verifiable project organization pattern. This would directly influence the agent's decision about where to place new output directories, making it necessary to retain.

**nano** -> `refine` (q=0.50, n=0.40)

- General guidance on output directory placement; specific enough to be useful but could be made more concrete.
- _Proposed refined text:_
  > Prefer placing all project outputs under REPO_ROOT in dedicated subfolders such as nat-jobs/, eval-out/, and optimizer_results/. Before creating a new output directory, inspect existing stages to ensure the naming pattern is maintained.

**kimi** -> `keep` (q=0.70, n=0.60) — Provides specific, retrievable directory patterns (nat-jobs/, eval-out/, optimizer_results/) and actionable guidance for output placement that would change concrete file organization decisions.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 19 / 40 — `24883461872a` (council aggregate: `keep`)

**Original:**

> Prefers explicit credential mapping between services. Does not want automatic substitution of credentials meant for one API provider as fallback credentials for a different provider, even when upstream code has such fallback chains.

**sonnet** -> `keep` (q=0.75, n=0.85)

- This entry captures a specific architectural preference about credential handling that would directly influence agent behavior when configuring API integrations. It's concrete enough to guide decisions (no automatic credential fallback chains) and has sufficient detail to be actionable, though it could be slightly more specific with examples.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry expresses a useful design principle but is somewhat generic; refining it will clarify the required credential mapping behavior.
- _Proposed refined text:_
  > Explicitly map credentials to their intended service; do not automatically substitute credentials from one API provider as fallback credentials for a different provider, even when upstream code includes such fallback chains.

**kimi** -> `keep` (q=0.60, n=0.60) — Captures a specific, non-obvious engineering preference about credential isolation across API providers that would affect concrete decisions when working with multi-provider authentication or fallback logic.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 20 / 40 — `5e218e802370` (council aggregate: `keep`)

**Original:**

> When filing bugs, user prefers minimal investigation — capture the repro and symptoms, don't deep-dive into root cause. User said "Don't work too hard, the person fixing it can dig" when asked not to over-investigate code during bug filing.

**sonnet** -> `keep` (q=0.85, n=0.90)

- This entry captures a specific, actionable workflow preference with a direct quote that would change agent behavior during bug filing. The concrete instruction to avoid deep investigation and the supporting quote make it highly retrievable and behaviorally significant.

**nano** -> `refine` (q=0.85, n=0.70)

- The entry provides a clear, actionable guideline with a representative user quote, but the phrasing could be tightened for precision. It is worth retaining after refinement.
- _Proposed refined text:_
  > When filing bugs, prioritize minimal investigation: capture the reproduction steps and observed symptoms, and avoid deep root-cause analysis; note the user's directive: "Don't work too hard, the person fixing it can dig."

**kimi** -> `keep` (q=0.90, n=0.90) — The entry includes a precise user quote and a clear directive about bug-filing depth, making it highly specific and actionable. Removing it would change whether the agent performs deep root-cause analysis when drafting bugs, and there is no obvious duplicate or system-prompt overlap.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 21 / 40 — `ffebf7790489` (council aggregate: `keep`)

**Original:**

> Works with NVIDIA projects (NeMo, Studio, Omnipush, etc.) and tests cmux integration. Has access to NVIDIA Omnistations. Working on NeMo Platform agentic-use benchmarking. Has access to NVIDIA NGC/inference API keys.

**sonnet** -> `keep` (q=0.85, n=0.90)

- Entry contains specific named entities (NVIDIA NeMo, Studio, Omnipush, cmux, Omnistations, NGC, NeMo Platform) and concrete access credentials that would change agent behavior when discussing NVIDIA-related work or available resources. The specificity of projects and infrastructure access makes this highly retrievable and actionable.

**nano** -> `refine` (q=0.60, n=0.50)

- The entry mentions several concrete NVIDIA projects and resources but is slightly vague on specifics.
- _Proposed refined text:_
  > Works with NVIDIA projects (NeMo, Studio, Omnipush, etc.), tests cmux integration, accesses NVIDIA Omnistations, performs NeMo Platform agentic-use benchmarking, and uses NVIDIA NGC inference API keys.

**kimi** -> `keep` (q=0.75, n=0.70) — Entry contains specific named entities (NeMo, cmux, NGC, Studio) and concrete access details that directly shape technical suggestions, making it retrievable and behavior-changing.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 22 / 40 — `cc2763c3925d` (council aggregate: `keep`)

**Original:**

> Max Dubrinsky (GitHub: maxdubrinsky) is a maintainer of NVIDIA/OpenShell. Has personal connections to NVIDIA/OpenShell maintainers but contributes via fork (not direct push access).

**sonnet** -> `keep` (q=0.85, n=0.70)

- Entry contains specific, verifiable facts (named person, GitHub handle, specific repository, contribution model) that would meaningfully inform interactions about NVIDIA/OpenShell project structure and contribution workflows. The corroboration across 2 sessions suggests this is reliable information worth preserving.

**nano** -> `refine` (q=0.80, n=0.30)

- The entry is fairly specific but could be phrased more clearly to improve retrievability and precision.
- _Proposed refined text:_
  > Max Dubrinsky (GitHub: maxdubrinsky) maintains NVIDIA/OpenShell via a fork; he has personal connections to the core maintainers but does not have direct push access to the upstream repository.

**kimi** -> `keep` (q=0.75, n=0.60) — Specific named entities, GitHub handle, and repository access details with multi-session corroboration; knowing he lacks direct push access prevents incorrect workflow assumptions.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 23 / 40 — `c39e32157fe7` (council aggregate: `keep`)

**Original:**

> Assigns Tyler Bray (GitHub: tylersbray, email: tbray@nvidia.com) as reviewer for CLI and agent-related work on NeMo Platform.

**sonnet** -> `keep` (q=0.95, n=0.85)

- Highly specific entry with concrete named entities (Tyler Bray), verifiable contact information (GitHub handle, email), and clear scope (CLI and agent-related work on NeMo Platform). This would directly influence reviewer assignment decisions and is appropriately narrow for retrieval-based memory rather than system prompt.

**nano** -> `refine` (q=0.90, n=0.20)

- The entry is specific but could be clearer about the scope of the reviewer role and platform version.
- _Proposed refined text:_
  > Assign Tyler Bray (GitHub: tylersbray, email: tbray@nvidia.com) as reviewer for CLI and agent-related work on the NeMo Platform.

**kimi** -> `keep` (q=0.90, n=0.90) — The entry contains concrete named entities, a GitHub handle, email, and precise scope (CLI and agent-related work on NeMo Platform), making it highly retrievable and directly actionable for reviewer-assignment decisions.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 24 / 40 — `aa59a8b70138` (council aggregate: `keep`)

**Original:**

> Has extensive experience writing OpenAPI parsers/utils. Previously worked at Gretel where he used OpenAPI Generator and had to hack internals to get good bindings. This background informs his skepticism about off-the-shelf OpenAPI generators.

**sonnet** -> `keep` (q=0.85, n=0.75)

- Entry contains specific, verifiable information about the user's professional experience (worked at Gretel, used OpenAPI Generator, hacked internals) that directly explains their technical perspective and skepticism. This context could influence how an agent frames recommendations about OpenAPI tooling or interprets the user's technical opinions.

**nano** -> `refine` (q=0.60, n=0.50)

- The entry provides useful background but could be clearer and more specific.
- _Proposed refined text:_
  > Worked extensively on OpenAPI parser and utility development; at Gretel used OpenAPI Generator and had to modify its internals to produce suitable bindings, which fuels his distrust of generic OpenAPI generators.

**kimi** -> `keep` (q=0.80, n=0.70) — Specific, verifiable professional background at Gretel with concrete technical detail (hacking OpenAPI Generator internals) that directly shapes tooling recommendations and avoids generic suggestions.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

## Group: sonnet `promote_to_prompt` vs nemotron-nano `refine` (5)

### Entry 25 / 40 — `2c52e8806ac9` (council aggregate: `keep`)

**Original:**

> ## Collaboration style
>
> Keeps user in the development loop — "Be vocal if you are missing information or could use another set of eyes from me." Wants gaps and uncertainties surfaced explicitly rather than having the agent make assumptions. When uncertain, do less not more — pause before spawning ceremony. Values being asked questions when the path is unclear.

**sonnet** -> `promote_to_prompt` (q=0.70, n=0.90)

- This entry captures specific, actionable behavioral guidance with high corroboration (8 sessions). It defines concrete interaction patterns: surface gaps explicitly, ask questions when unclear, do less when uncertain, and avoid assumptions. The high session count and behavioral specificity suggest this is a core interaction principle that should apply universally rather than being retrieved contextually.

**nano** -> `refine` (q=0.50, n=0.50)

- Provides useful guidance but is vague and could be clearer.
- _Proposed refined text:_
  > Maintain an open development loop: explicitly surface any gaps or uncertainties, pause before initiating new ceremonies, and ask clarifying questions when the path forward is unclear.

**kimi** -> `keep` (q=0.90, n=0.90) — Highly corroborated across 8 sessions with specific behavioral guidance and a direct quote; removing it would change concrete decisions about when to pause, ask questions, or spawn ceremony.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 26 / 40 — `9cd72c55fda5` (council aggregate: `keep`)

**Original:**

> Prefers deliberate investigation over trial-and-error. When introducing a new tool, wants agent to "brush up" on how to use it before firing off commands. Values understanding complexity/scope before implementing. Slow at architectural boundaries; iteration speed never substitutes for thinking.

**sonnet** -> `promote_to_prompt` (q=0.60, n=0.80)

- This entry captures a consistent, actionable working preference observed across 4 sessions: deliberate investigation and understanding before implementation. While not citing specific tools or commands, it describes a meta-approach to problem-solving that should shape all agent behavior. It's better suited as permanent system-prompt guidance than as a retrieved fact.

**nano** -> `refine` (q=0.50, n=0.50)

- The guidance is useful but too general; it can be made clearer and more actionable.
- _Proposed refined text:_
  > Before executing new commands, verify familiarity with the tool by reviewing its documentation or recent usage; assess architectural impact and complexity; prioritize thoughtful design over rapid iteration.

**kimi** -> `keep` (q=0.50, n=0.70) — Well-corroborated (4 sessions) behavioral preference that directly opposes default rapid-iteration patterns and would change concrete decisions about researching tools before use and pacing at architectural boundaries. Lacks named entities but contains retrievable, distinctive phrasing.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 27 / 40 — `07b56fbdcc23` (council aggregate: `keep`)

**Original:**

> Prefers distilled, compact memories over verbose ones. When memories accumulate specific implementation details (file paths, class names, line numbers), wants them trimmed to essential decisions/principles and pointers to canonical sources. Asks for memory cleanup proactively to reduce context load.

**sonnet** -> `promote_to_prompt` (q=0.70, n=0.80)

- This entry describes a clear, actionable preference about memory management style that should inform all agent interactions. It's specific enough to guide behavior (trim implementation details, keep principles, reduce context load) and applies broadly enough that it belongs in the system prompt rather than being retrieved situationally.

**nano** -> `refine` (q=0.60, n=0.50)

- The entry captures a useful heuristic but is phrased loosely and lacks concrete triggers.
- _Proposed refined text:_
  > Agent prefers concise, distilled memories; when detailed implementation information (e.g., file paths, class names, line numbers) accumulates, it should be compressed to core decisions and references to canonical sources, and memory should be cleaned proactively to limit context load.

**kimi** -> `keep` (q=0.60, n=0.70) — Captures a specific meta-preference about memory compaction and proactive cleanup that would concretely change how the agent records and maintains memories, though it lacks a verbatim example or named entity.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 28 / 40 — `5312e5c7aaf8` (council aggregate: `refine`)

**Original:**

> Evaluates code review findings critically with justification. Expects "FIX" vs "DON'T FIX" decisions with clear reasoning, not blind acceptance of all suggestions. Uses cost/benefit analysis for proposed changes. Expects critical evaluation with justification for every decision — prefers seeing reasoning for both what gets applied and what gets rejected.

**sonnet** -> `promote_to_prompt` (q=0.60, n=0.80)

- This entry captures a specific behavioral preference for code review evaluation that would meaningfully change agent behavior (requiring justified FIX/DON'T FIX decisions with cost/benefit analysis). However, it's a general methodological principle that should apply to all code review contexts, making it better suited for the system prompt than retrieval-based memory.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry offers useful guidance but remains vague; it can be made more concrete and actionable.
- _Proposed refined text:_
  > Require agents to critically evaluate code review suggestions, explicitly distinguish between "FIX" and "DON'T FIX" decisions, provide justification, and perform cost/benefit analysis; document reasoning for accepted and rejected changes.

**kimi** -> `refine` (q=0.50, n=0.50) — The entry captures a real, corroborated preference for explicit FIX/DON'T FIX reasoning during code reviews, but the text is highly redundant. A concise rewrite will improve retrieval precision without losing signal.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 29 / 40 — `daa44d66c1c0` (council aggregate: `keep`)

**Original:**

> When user explicitly asks for a specific tool or approach (e.g., "use tmux" not just "parallel subagents"), follow it literally — there's always a reason. Don't substitute with "equivalent" alternatives without asking first.

**sonnet** -> `promote_to_prompt` (q=0.60, n=0.80)

- This captures an important behavioral principle about respecting explicit user requests for specific tools rather than substituting alternatives. While it uses an example (tmux) rather than being a concrete fact, the underlying principle is broadly applicable and should influence all agent interactions, making it better suited for the system prompt than episodic retrieval.

**nano** -> `refine` (q=0.50, n=0.50)

- The rule is useful but phrased vaguely; refining will make it clearer and more actionable.
- _Proposed refined text:_
  > When a user explicitly requests a specific tool or approach (e.g., "use tmux" rather than "parallel subagents"), follow that request literally. Do not substitute an equivalent without first asking the user for confirmation.

**kimi** -> `keep` (q=0.80, n=0.90) — Actionable behavioral rule with specific examples (tmux, parallel subagents) that directly shapes tool-selection decisions and is unlikely to be duplicated in the base system prompt.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

## Group: sonnet `refine` vs nemotron-nano `keep` (4)

### Entry 30 / 40 — `da5498e4affc` (council aggregate: `keep`)

**Original:**

> Expects verification of claims before making breaking changes. Will ask "can you make sure of that" and wants downstream impact checked (e.g., grepping for field usage before removing from public schema).
>
> ## Technical preferences — architecture and design
>
> Data model evolution: prefer to omit fields until there's a concrete consumer. "Easier to add a field than remove one." Keep surface area small in initial implementations rather than pre-emptively adding fields that might be useful later.

**sonnet** -> `refine` (q=0.65, n=0.75)

- The entry captures concrete behavioral preferences (verification before breaking changes, omitting fields until needed) with a specific quote and example action (grepping for usage). However, the structure mixes two related but distinct concepts that would be clearer if separated and more precisely stated.
- _Proposed refined text:_
  > Development practices: Before making breaking changes (e.g., removing fields from public schemas), expects verification of downstream impact with specific checks like "can you make sure of that" and grepping for field usage across the codebase.
  >
  > Data model design philosophy: Prefer to omit optional fields from initial implementations until there's a concrete consumer. Rationale: "Easier to add a field than remove one." Keep API surface area minimal rather than pre-emptively adding speculative fields.

**nano** -> `keep` (q=0.70, n=0.90)

- The entry gives a specific, actionable guideline for verifying claims and managing schema changes, which is not redundant.

**kimi** -> `keep` (q=0.80, n=0.70) — Contains specific behavioral quotes and concrete examples (e.g., grepping for field usage) that would steer schema design and breaking-change recommendations; worth keeping as a retrievable preference.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 31 / 40 — `4fe0da7c8b7f` (council aggregate: `keep`)

**Original:**

> When CodeRabbit suggests a Ruff rule violation, check the project's ruff.toml first — if the rule isn't enabled, the suggestion may be unhelpful. Justify by noting the rule isn't enforced and that fixing creates inconsistency with existing production patterns. Check project lint config before applying style/rule suggestions.

**sonnet** -> `refine` (q=0.65, n=0.70)

- The entry captures a specific, actionable pattern (check ruff.toml before accepting CodeRabbit suggestions) with clear justification logic. However, it's somewhat verbose and could be more concise while retaining the key procedural insight.
- _Proposed refined text:_
  > Before accepting CodeRabbit Ruff rule suggestions, verify the rule is enabled in the project's ruff.toml. If not enabled, reject the suggestion noting the rule isn't enforced and fixing it would create inconsistency with existing codebase patterns.

**nano** -> `keep` (q=1.00, n=0.90)

- The entry gives a concrete, verifiable instruction about checking ruff.toml before applying Ruff suggestions, which would affect agent decisions if removed.

**kimi** -> `keep` (q=0.75, n=0.60) — Contains specific named tools (CodeRabbit, Ruff, ruff.toml) and an actionable conditional workflow that would change how the agent handles automated lint suggestions, distinguishing it from generic linting advice.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 32 / 40 — `bb0d40fa9755` (council aggregate: `keep`)

**Original:**

> When asked to investigate refactoring opportunities (fixtures/parameterization), user wants thoughtful analysis with clear recommendations of what to apply vs skip, not automatic application. Prefers to understand trade-offs ("merging would be more bytes, not fewer") before proceeding.
>
> ## Tools and workflows — Linear
>
> Works in Linear desktop app. Rewrite URLs from `https://linear.app/...` to `linear://...` in all outputs (chat, commits, PR/issue bodies, dev journals, and links returned by Linear MCP tools). `linear://` opens directly in desktop app; `https://` forces a browser detour.
>
> ## Tools and workflows — git
>
> Prefers clean git workflow with feature branches even when personally "play fast and loose on main" — explicitly requested dev branch instead of committing to main for SDK work.

**sonnet** -> `refine` (q=0.75, n=0.85)

- The entry contains specific, actionable preferences (Linear URL rewriting, git workflow) and a concrete quote demonstrating analytical preference. However, it combines three distinct topics under unclear headings that should be separated for better retrievability.
- _Proposed refined text:_

  > ## Code analysis and refactoring
  >
  > When asked to investigate refactoring opportunities (e.g., fixtures/parameterization), user wants thoughtful analysis with clear recommendations of what to apply vs skip, not automatic application. Prefers to understand trade-offs before proceeding. Example: appreciated nuanced advice like "merging would be more bytes, not fewer" when evaluating test consolidation.
  >
  > ## Linear workflow
  >
  > Works in Linear desktop app. Always rewrite URLs from `https://linear.app/...` to `linear://...` in all outputs including chat messages, commits, PR/issue bodies, dev journals, and links returned by Linear MCP tools. The `linear://` protocol opens directly in desktop app; `https://` forces an unnecessary browser detour.
  >
  > ## Git workflow
  >
  > Prefers clean git workflow with feature branches for collaborative or SDK work, even though user personally may "play fast and loose on main" in solo contexts. Explicitly requested dev branch instead of committing to main for SDK work.

**nano** -> `keep` (q=0.50, n=1.00)

- Specific user preferences about analysis, URL rewriting, and git workflow that affect agent behavior.

**kimi** -> `keep` (q=0.90, n=0.90) — Entry contains three distinct, high-signal preferences with named tools, specific URL protocols, and exact quotes that would change concrete agent decisions if removed.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 33 / 40 — `2071e2066468` (council aggregate: `keep`)

**Original:**

> When syncing between local and remote document mirrors (e.g., in-repo RFC and Linear doc): update whichever is more current. If both are the same, start with the local copy then push that up.
>
> ## Tools and workflows — shell and dotfiles
>
> Uses zsh with oh-my-zsh. ZDOTDIR is `~/.config/zsh`. Has `.zshrc.local` symlinked to `.config/zsh/locals/.zshrc.work`. Prefers cached completion approach for shell startup performance.

**sonnet** -> `refine` (q=0.85, n=0.75)

- Entry contains highly specific, verifiable details (ZDOTDIR path, symlink structure, oh-my-zsh) that would change agent behavior when working with this user's shell configuration. However, it combines two unrelated topics (document syncing and shell setup) which should be separated for better retrieval.
- _Proposed refined text:_

  > ## Shell and dotfiles configuration
  >
  > Uses zsh with oh-my-zsh. ZDOTDIR is `~/.config/zsh`. Has `.zshrc.local` symlinked to `.config/zsh/locals/.zshrc.work`. Prefers cached completion approach for shell startup performance.
  >
  > ## Document sync workflow (local ↔ remote mirrors)
  >
  > When syncing between local and remote document mirrors (e.g., in-repo RFC and Linear doc): update whichever is more current. If both are the same, start with the local copy then push that up.

**nano** -> `keep` (q=0.80, n=0.30)

- Specific details about sync strategy and zsh configuration, but not critical enough to warrant promotion or removal.

**kimi** -> `keep` (q=0.90, n=0.90) — Contains concrete, personal setup details (exact ZDOTDIR paths, symlinks, shell tools) and a specific document-sync workflow rule that would directly change agent behavior; not generic knowledge.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

## Group: sonnet `drop` vs nemotron-nano `refine` (3)

### Entry 34 / 40 — `3ebdcd9b6c49` (council aggregate: `drop`)

**Original:**

> Comfortable with uncertainty and explicit about unknowns. Will say "I genuinely don't know" rather than guessing. Values honesty about knowledge gaps in decision-making.

**sonnet** -> `drop` (q=0.20, n=0.10)

- This entry describes general epistemic virtue (admitting unknowns, honesty about limits) that should already be part of any competent AI agent's base behavior. It lacks specific retrievable details about the user's preferences or context, and appears to restate default assistant behavior rather than capture meaningful user-specific information.

**nano** -> `refine` (q=0.50, n=0.50)

- The statement is a useful guideline but could be more specific and actionable.
- _Proposed refined text:_
  > Explicitly acknowledge uncertainty and say "I genuinely don't know" rather than guessing, ensuring honesty about knowledge gaps in decisions.

**kimi** -> `drop` (q=0.50, n=0.00) — Admitting uncertainty rather than guessing is default behavior already enforced by standard system prompts; the entry restates a universal baseline without adding a user-specific preference or phrasing requirement that would change outcomes.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 35 / 40 — `7350bebdc6f8` (council aggregate: `refine`)

**Original:**

> Proponent of good module separation in code organization, even when it differs from existing patterns in the codebase.

**sonnet** -> `drop` (q=0.20, n=0.10)

- This entry is too vague and could apply to any competent software engineer. It lacks specificity about what constitutes 'good module separation' for this particular user, what patterns they prefer, or concrete examples of when they've advocated for this. Without actionable detail, it won't meaningfully change agent behavior.

**nano** -> `refine` (q=0.50, n=0.50)

- The entry offers a general principle but lacks concrete details or verifiable specifics, making it overly vague.
- _Proposed refined text:_
  > Advocate for clean module separation in code structure, even when it conflicts with existing codebase conventions.

**kimi** -> `refine` (q=0.50, n=0.70) — The entry conveys a durable preference that overrides the default mimicry of existing patterns, but the indirect 'proponent of' phrasing makes it less retrievable and actionable. Rewriting it as a direct preference sharpens the signal without loss of meaning.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 36 / 40 — `ccd19a2fa241` (council aggregate: `keep`)

**Original:**

> Values consistency across the codebase — when fixing bugs or implementing features, prefers to match broader codebase patterns rather than keeping one-off exceptions ("do whatever is most consistent").

**sonnet** -> `drop` (q=0.30, n=0.10)

- This entry describes a general software engineering best practice (consistency over one-off exceptions) that any competent engineer would follow by default. It lacks specificity about what patterns, which codebase contexts, or concrete examples where this preference matters, and would not meaningfully change agent behavior if removed.

**nano** -> `refine` (q=0.50, n=0.20)

- The guidance is vague and not specific enough for reliable retrieval, but it conveys a useful principle that could be clarified.
- _Proposed refined text:_
  > Prefer to align code changes with existing patterns in the codebase; avoid introducing one‑off exceptions unless absolutely necessary.

**kimi** -> `keep` (q=0.60, n=0.60) — Contains a verifiable user quote and a concrete decision heuristic that steers bug fixes and feature work toward global codebase consistency rather than minimal local diffs.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

## Group: sonnet `keep` vs nemotron-nano `promote_to_prompt` (2)

### Entry 37 / 40 — `f4a359b3859e` (council aggregate: `keep`)

**Original:**

> Prefers Python-style pseudocode over LaTeX/mathematical notation for expressing formulas and algorithms. "Prefer python to math since it's been 15 years since I've used LaTeX."

**sonnet** -> `keep` (q=0.85, n=0.90)

- This entry contains a specific, actionable preference with concrete context (Python vs LaTeX, 15-year gap in LaTeX usage) and a direct quote. It would materially change how the agent presents technical content—choosing Python code examples over mathematical notation—which directly impacts user comprehension and satisfaction.

**nano** -> `promote_to_prompt` (q=0.80, n=0.60)

- Clear preference for Python pseudocode over LaTeX, specific to output style and would affect agent behavior if removed.

**kimi** -> `keep` (q=0.90, n=0.90) — Contains a concrete, actionable presentation preference backed by a direct quote; removing it would likely cause the agent to default to LaTeX/mathematical notation when explaining algorithms or formulas.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 38 / 40 — `fe3b38f60055` (council aggregate: `keep`)

**Original:**

> When reviewing PRs, user wants to distinguish between issues caused by the PR (net-new) vs issues that were pre-existing on main. Asked explicitly: "Are there any issues created by this PR or are these problems present on the current implementation?"

**sonnet** -> `keep` (q=0.75, n=0.80)

- This entry captures a specific, actionable preference for PR review methodology with an exact quote demonstrating the user's concern. It will materially affect how the agent structures PR analysis by ensuring it explicitly distinguishes new issues from pre-existing ones, rather than presenting all findings without context.

**nano** -> `promote_to_prompt` (q=0.90, n=0.90)

- The entry captures a precise user instruction for distinguishing net‑new from pre‑existing issues in PR reviews, making it both specific and valuable enough to be part of the system prompt. Removing it would cause the agent to miss this explicit line of questioning.

**kimi** -> `keep` (q=0.90, n=0.80) — Contains a direct, verifiable quote and describes a concrete workflow preference for PR reviews that would change how the agent categorizes and reports issues.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

## Group: sonnet `refine` vs nemotron-nano `promote_to_prompt` (2)

### Entry 39 / 40 — `d78b6a695264` (council aggregate: `keep`)

**Original:**

> Prefers dropping features entirely when their value proposition weakens rather than maintaining stopgap solutions or adding CLI complexity to preserve them. Applies "re-evaluate dependent features" principle consistently. Example: removed `--model` flag from usage CLI because richer artifact data (trajectory.json) will eventually provide authoritative model identity, avoiding two-sources-of-truth problems.

**sonnet** -> `refine` (q=0.75, n=0.80)

- The entry captures a specific, verifiable design principle with a concrete example (--model flag removal), but the phrasing is somewhat verbose and could be tightened for better retrieval. The principle is actionable and would influence future feature decisions.
- _Proposed refined text:_
  > Design principle: Remove features entirely when value proposition weakens rather than maintaining stopgaps or adding CLI complexity. When considering feature removal, re-evaluate dependent features. Example: Removed `--model` flag from usage CLI because trajectory.json will provide authoritative model identity, avoiding dual sources of truth.

**nano** -> `promote_to_prompt` (q=0.80, n=0.90)

- The entry provides a concrete, actionable principle with a specific example, making it both specific enough for retrieval and influential on the agent's decisions, thus warranting promotion to the system prompt.

**kimi** -> `keep` (q=0.80, n=0.80) — Corroborated preference backed by a concrete CLI example (`--model` flag, trajectory.json) that directly shapes whether the agent recommends dropping features or maintaining stopgaps.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---

### Entry 40 / 40 — `81d7a0d390ee` (council aggregate: `keep`)

**Original:**

> Uses @filename syntax to reference files (e.g., "@RFC-migrate-off-stainless.md"). When user mentions a document by name or reference, ask for location/path rather than searching blindly.

**sonnet** -> `refine` (q=0.70, n=0.60)

- The entry captures a specific user preference (@filename syntax) and a useful behavioral guidance (ask for path rather than searching), but combines two distinct concepts that could be clearer and more actionable.
- _Proposed refined text:_
  > User references files using @filename syntax (e.g., '@RFC-migrate-off-stainless.md'). When user mentions a document without providing its path, always ask for the location/path explicitly rather than attempting to search or guess the file location.

**nano** -> `promote_to_prompt` (q=0.70, n=0.90)

- Clear, specific instruction that would change agent behavior and is broadly applicable, so it should be part of the system prompt.

**kimi** -> `keep` (q=0.80, n=0.70) — Concrete user-specific workflow pattern with a precise example; removing it risks the agent searching blindly instead of requesting a path for @-referenced documents.

**My read:**

- [ ] sonnet is right
- [ ] nano is right
- [ ] both wrong (real verdict: \_\_\_ )
- [ ] toss-up (either is defensible)

**Hypothesis vote:** (1) prompt / (2) nano hallucinates / (3) sonnet under-engages / (other: \_\_\_ )

**Notes:**

---
