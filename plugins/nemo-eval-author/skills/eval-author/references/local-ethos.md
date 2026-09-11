<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Local Ethos for Eval Author

The repository's `ETHOS.md` is the source of truth. Creating, reading, reviewing,
and validating it are local operations. Never upload it, create a Fileset, check
NeMo service health, require a workspace or account, or ask the user to restore
a platform service for this flow. Do not invoke `nemo-explore`, `nemo-ethos`, or
model selection as prerequisites: their platform-oriented workflow is not this
local procedure. No installed NeMo skills, CLI, Harbor, or credentials are needed
to capture intended behavior.

## Locate or resume

Use the caller's explicit Ethos path first. Otherwise prefer root `ETHOS.md`,
then an existing `agents/<name>-ethos/ETHOS.md` matching the selected agent. Read
it rather than treating existence as proof of completeness. Resolve ambiguous
agent identity or multiple matching files with the user. Preserve existing
content, custom sections, and user edits.

For new files, default to `<repo-root>/ETHOS.md`; use another in-repo location
when the user specifies it. This is the narrow exception to Eval Author's
`.eval-author/` output boundary: only the requested Ethos may be written there.
Do not modify application source or `.gitignore`, and do not commit automatically.

If an earlier attempt saved `.eval-author/intent-notes.md` or interview answers
in the conversation, reuse them. A failed upload does not invalidate the local
file or the user's decisions. Do not repeat answered questions or re-request
permission to make changes already authorized in those answers. Permission to
change prompts later belongs in Change Scope; recording it does not change them.

## Capture intended behavior

Before the first intent question, explain that Ethos records the agent's purpose,
boundaries, and success criteria so its evals have a target. Use the caller's
onboarding guidance. Read source and docs for implementation facts; ask the user
for intent that those files cannot establish. Ask focused questions about desired
outcomes, boundaries, principles, and future direction only where answers are
missing. Keep the current agent, model, and runtime unless the user asks to change
them. End ordinary intent messages with the question, not procedural footnotes.

Use [the local template](../templates/ETHOS.md). Fill it with actual answers and
repository evidence; do not present implementation as approved intent. A concrete
Role and Purpose & Outcomes are needed to design useful evals. Record other
unresolved details in Open Questions rather than inventing them. Where a section
has no applicable requirements, write `_(none)_`; do not leave placeholder text.

Describe demo policies as demo fixtures when that is the user's scope. Missing
real-world airline approval, production SLAs, or business metrics need not block
a demo Ethos. If the user wants production behavior, record the missing policy
authority and resolve the relevant intent before claiming production readiness.
Do not silently convert demo expectations into real-world policy guarantees.

## Save, check, and review

Write the complete file locally from the template. Use `schema_version: 1`, the
actual agent name, current ISO 8601 creation timestamp, and actual author. Retain
creation metadata on edits; add `updated_timestamp` for the edit. Preserve unknown
frontmatter keys and custom body sections. Do not overwrite a supplied Ethos with
a fresh template; propose targeted edits when clarification is needed.

Read back the exact saved file and check:

1. The file is nonempty and at the selected in-repo path.
2. YAML frontmatter is a mapping with version 1, nonempty `name` and `author`,
   and an ISO 8601 `created_timestamp`; optional update timestamps are valid.
3. Each of the template's fifteen `##` headings occurs exactly once. Additional
   headings are allowed. Role and Purpose & Outcomes contain concrete intent;
   other sections contain real content or an honest `_(none)_` with uncertainties
   recorded in Open Questions. No angle-bracket template placeholders remain.
4. The recorded purpose, boundaries, and change permissions agree with the user's
   answers. Code references support implementation claims, not inferred approval.

These are local file and content checks, not proof of evaluation coverage. If an
existing local interpreter provides YAML parsing, use its safe loader to verify
frontmatter; do not install NeMo or contact a service to validate the document.
Report what was actually checked and distinguish structural inspection from a
parser-backed check. Do not claim platform or schema-parser validation you did
not run. Fix local structural errors before calling the file complete.

Summarize the agent's intended role, outcome, and boundaries in a short paragraph,
link the saved file, and ask the user to confirm or correct that summary unless
they already approved the exact content. Keep a written draft while awaiting
review. After local checks and content review, return the exact path to the
calling first-eval or audit flow. No upload step follows.

## Recovery

If writing fails, preserve the confirmed answers in the conversation or the
existing writable `.eval-author/intent-notes.md`, identify the specific local
error, and provide the [Ethos documentation](https://docs.nvidia.com/nemo-platform/documentation/agents/optimize-agents/ethos)
along with the complete proposed content when available. The user can save it
in the repo and provide its path. Explain that Eval Author uses the document
locally even if the linked platform documentation describes other integrations.
Missing intent calls for a concrete question; missing filesystem access calls
for a local recovery step. Neither calls for a platform restart or upload.
