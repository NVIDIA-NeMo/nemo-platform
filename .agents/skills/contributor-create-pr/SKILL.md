---
name: contributor-create-pr
description: Create, publish, or advance a GitHub pull request for NVIDIA-NeMo/nemo-platform with repository-aware branch checks, targeted validation, DCO sign-off enforcement, trusted PR-template completion, conventional titles, safe pushes, draft or ready-for-review creation, CI and CodeRabbit follow-up, and merge-conflict handling. Use when the user asks to commit and push work, create or open a PR, submit changes for review, mark a draft ready, monitor a PR, address automated review or CI feedback, or update a conflicted PR in nemo-platform.
---

<!-- SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Create a NeMo Platform pull request

Create and follow up on pull requests for `NVIDIA-NeMo/nemo-platform`. Treat the refreshed default branch as the source of repository policy and use the host-authenticated `gh` session for GitHub operations.

## Non-negotiable rules

- Read the root `AGENTS.md`, any `AGENTS.local.md`, and every nested `AGENTS.md` that governs a changed file before preparing the PR.
- Never create a PR from the default branch.
- Never commit or amend without `-s`. This includes normal commits, `--amend`, and `--fixup` commits.
- Preserve sign-offs during history updates with `git rebase --signoff` or `git merge --signoff`.
- Audit every commit in the PR range for an appropriate `Signed-off-by:` trailer before every push and immediately before PR creation.
- Do not forge another contributor's sign-off. Stop when a commit author must provide or correct their own DCO declaration.
- Never use `git reset --soft origin/main` or reset to any commit that is not an ancestor of `HEAD`.
- Never use plain `--force`. Use an exact `--force-with-lease` only after the user approves rewriting a published branch.
- Stop on GitHub authentication, authorization, SSO, remote-access, or push-permission failures. Do not search for tokens, change credentials, switch remote protocols, or try another identity.
- Do not alter an unrelated branch or PR. Do not create a duplicate PR for a branch that already has one.

## 1. Authenticate and establish the trusted base

Run these checks before a GitHub read or write:

```bash
NMP_REPO=NVIDIA-NeMo/nemo-platform
gh auth status
gh repo view "$NMP_REPO" --json nameWithOwner,defaultBranchRef,url
git remote get-url origin
```

Require an active host-authenticated account and `nameWithOwner` equal to `NVIDIA-NeMo/nemo-platform`. If `gh` fails only because a sandbox blocks host or network access, retry the same command with narrowly scoped host/network approval. If authentication or authorization still fails outside the sandbox, report the command and error and stop.

Resolve and refresh the default branch instead of assuming a stale local `main`:

```bash
NMP_BASE_BRANCH="$(gh repo view "$NMP_REPO" --json defaultBranchRef --jq '.defaultBranchRef.name')"
git fetch --prune origin "$NMP_BASE_BRANCH"
NMP_BASE_REF="origin/$NMP_BASE_BRANCH"
git show -s --format='%H %cs %s' "$NMP_BASE_REF"
```

Treat authentication or access errors from `git fetch` as hard stops.

## 2. Verify the branch and worktree

Inspect the exact worktree before modifying Git state:

```bash
git rev-parse --show-toplevel
git worktree list --porcelain
git status --short --branch
git branch --show-current
git log --oneline "$NMP_BASE_REF..HEAD"
git diff --stat "$NMP_BASE_REF...HEAD"
```

Require all of the following:

- Use a named feature branch, not detached `HEAD` and not the default branch.
- Follow `[git-issue-number]-<descriptive-branch-name>/<username>` from `AGENTS.md`. Omit the issue prefix only when no issue is known; keep kebab case and the username suffix.
- Keep only the intended PR changes in the worktree. Do not stash, discard, or absorb unrelated changes without the user's direction.
- Confirm that the branch has commits ahead of the trusted base or intended uncommitted changes that the user asked to include.
- Confirm that another worktree or active PR branch is not being repurposed.

If the current worktree is on the default branch, an unrelated PR branch, or a protected worktree, leave it untouched and create an isolated worktree from the refreshed base:

```bash
git worktree add -b "<description>/<username>" "<explicit-new-worktree-path>" "$NMP_BASE_REF"
```

Do not carry changes across worktrees implicitly. Ask before moving uncommitted work.

## 3. Load repository-owned policy

Read policy from the trusted base and compare it with the working tree when the PR changes policy itself:

```bash
git show "$NMP_BASE_REF:AGENTS.md"
git show "$NMP_BASE_REF:CONTRIBUTING.md"
git show "$NMP_BASE_REF:.github/CI_README.md"
git show "$NMP_BASE_REF:.github/workflows/ci.yaml"
git show "$NMP_BASE_REF:.github/workflows/security.yaml"
git show "$NMP_BASE_REF:.github/workflows/semantic-pull-requests.yaml"
git show "$NMP_BASE_REF:.github/workflows/dco-war.yaml"
```

Also read changed-area workflows, build files, package scripts, existing repo-local skills, and nested instructions. Do not copy commands from another repository when nemo-platform provides its own command.

## 4. Inspect the change and select validation

Review both committed and uncommitted changes:

```bash
git diff --name-status "$NMP_BASE_REF...HEAD"
git diff "$NMP_BASE_REF...HEAD"
git diff --check "$NMP_BASE_REF...HEAD"
git diff --check
git diff --cached --check
```

Run the smallest checks that directly verify each changed behavior, plus the repository-mandated pre-commit gate. Record every command and result for the PR body.

- **All changes before commit:** Run `uv run pre-commit run -a` as required by `AGENTS.md`. Rerun it after a hook modifies files.
- **Python:** Run the directly affected `uv run --frozen pytest <path> -v`; use `make test-package PACKAGE=<name>` or `make test-service SERVICE=<name>` when a package or service boundary is the right scope. Run targeted `uv run ruff check <path>` and `uv run ruff format --check <path>`. Run `uv run --frozen ty check` when type behavior changes.
- **Studio or other `web/` changes:** From `web/`, run the affected package test. Also use the PR-scoped commands that mirror CI when applicable: `pnpm --filter="...[$NMP_BASE_REF]" run --parallel --if-present typecheck` and `pnpm --filter="...[$NMP_BASE_REF]" run --parallel --if-present test:ci`. Run `pnpm lint` and `pnpm format` for broad web changes.
- **Fern docs:** Follow `docs/AGENTS.md`. Run `make docs-check` and `make docs-broken-links`; run `make docs-check-python-snippets DOCS_PATH=<path>` or `make docs-run-notebook DOCS_PATH=<path>` when those surfaces change.
- **API, schema, generated SDK, CLI, or config-reference changes:** Follow the regeneration rules in `AGENTS.md`, the applicable nested instructions, and the exact Make targets. Verify generated output is committed and stable after rerunning the generator.
- **OPA, Helm, Docker, or workflow changes:** Use the relevant checks such as `make check-policy`, `tools/lint/lint-helm.sh`, Docker bake graph commands, or `actionlint`. Read the workflow before choosing a command.
- **Broad validation infrastructure changes:** Run `make lint` and the applicable broad test target, such as `make test-unit`, when targeted evidence is insufficient.

Do not claim a skipped check passed. For a draft, state missing or blocked validation. For a ready PR, fix required failures first unless the user explicitly accepts a documented, non-required limitation.

## 5. Stage and commit with mandatory sign-off

Inspect the staged patch before every commit:

```bash
git add -- <exact-intended-paths>
git diff --cached --stat
git diff --cached
git diff --cached --check
git commit -s -m "<conventional commit message>"
```

Local skill installs may also appear under `.agents/skills/nemo-*/`. Stage only explicitly intended repo-owned files by exact path; never use a broad add that can capture unrelated installed skills.

Use only sign-off-preserving forms:

```bash
git commit --amend -s --no-edit
git commit -s --fixup=<commit>
git rebase --signoff <upstream>
git merge --signoff <upstream>
```

Never run `git commit`, `git commit --amend`, or a fixup commit without `-s`. If hooks change the patch, restage the intended files, rerun affected validation, and commit with `-s` again.

## 6. Audit every PR commit for DCO

Run this gate after any commit, amend, rebase, cherry-pick, conflict resolution, or automated fix, and before every push or `gh pr create`. It requires a syntactically valid sign-off whose email matches the commit author's email, case-insensitively:

```bash
bash -euo pipefail <<'BASH'
: "${NMP_BASE_REF:?set NMP_BASE_REF to the refreshed origin default branch}"
NMP_DCO_FAILED=0
NMP_COMMIT_COUNT=0

while IFS= read -r NMP_SHA; do
  NMP_COMMIT_COUNT=$((NMP_COMMIT_COUNT + 1))
  NMP_AUTHOR_EMAIL="$(git show -s --format=%ae "$NMP_SHA")"
  NMP_SIGNOFF_EMAILS="$(
    git show -s --format=%B "$NMP_SHA" \
      | git interpret-trailers --parse \
      | awk -F '[<>]' 'tolower($1) ~ /^signed-off-by:[[:space:]]/ && NF >= 3 { print $2 }'
  )"

  if ! printf '%s\n' "$NMP_SIGNOFF_EMAILS" \
    | awk -v want="$NMP_AUTHOR_EMAIL" 'tolower($0) == tolower(want) { found=1 } END { exit(found ? 0 : 1) }'; then
    printf 'DCO FAIL %s: no Signed-off-by trailer matches author email %s\n' "$NMP_SHA" "$NMP_AUTHOR_EMAIL" >&2
    NMP_DCO_FAILED=1
  else
    printf 'DCO OK   %s\n' "$NMP_SHA"
  fi
done < <(git rev-list --reverse "$NMP_BASE_REF..HEAD")

test "$NMP_COMMIT_COUNT" -gt 0
test "$NMP_DCO_FAILED" -eq 0
BASH
```

Do not treat a PR-body declaration or GitHub's cryptographic `Verified` badge as a substitute for commit trailers. Nemo-platform's required gate is DCO sign-off.

If the audit fails:

- Amend the last unpushed, self-authored commit with `git commit --amend -s --no-edit`.
- Repair multiple unpushed, self-authored commits with `git rebase --signoff --force-rebase "$NMP_BASE_REF"`; `--force-rebase` is required when Git would otherwise report an already-current branch and skip replaying the unsigned commits.
- Stop before rewriting a published branch and request explicit approval.
- Stop rather than adding a sign-off for a commit authored by someone else.
- Rerun the entire audit after repair.

## 7. Validate the title and complete the trusted template

Use a title no longer than 100 characters in this form:

```text
<type>[optional scope][!]: <description>
```

Use one of the conventional types accepted by the pinned title action: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, or `revert`. Use an accurate optional scope and `!` only for a breaking change.

Locate the PR template in the trusted base, not in the feature branch and not in a recent PR body:

```bash
git ls-tree -r --name-only "$NMP_BASE_REF" \
  | rg -i '(^|/)(pull_request_template)(\.md|/.*\.md)$'
```

- If exactly one template applies, copy it with `git show "$NMP_BASE_REF:<template-path>"` into a file created by `mktemp /tmp/nemo-platform-pr-body.XXXXXX`.
- If multiple templates exist, select the repository-defined template that matches the change. Ask when selection is ambiguous.
- If no template exists on the trusted base, report the missing repository dependency and stop before `gh pr create`. Do not invent a template or silently reuse a branch-modified or historical body.
- If the PR changes the template, still populate the trusted base version and explain the template change in that body.

Preserve the template's section order, comments, and checkbox semantics. Complete every applicable section from `git diff "$NMP_BASE_REF...HEAD"`. Check only items backed by command, hook, or CI evidence. Use `Fixes #NNN` or `Closes #NNN` only for a real related issue. Do not add a PR-body sign-off unless the trusted template requests it; the commit-level DCO audit remains mandatory.

## 8. Push safely

Immediately before pushing, rerun the DCO audit, confirm the branch and remote, and inspect the outgoing commits:

```bash
NMP_BRANCH="$(git branch --show-current)"
git remote get-url origin
git log --oneline "$NMP_BASE_REF..HEAD"
git push --set-upstream origin "HEAD:refs/heads/$NMP_BRANCH"
```

Use a normal push first. On a non-fast-forward rejection, fetch the exact remote branch and inspect both histories. Stop if the remote contains unexpected work.

Only after the user approves rewriting a published branch, pin the lease to the fetched remote SHA:

```bash
git fetch origin "$NMP_BRANCH"
NMP_EXPECTED_REMOTE_SHA="$(git rev-parse "origin/$NMP_BRANCH")"
git push \
  --force-with-lease="refs/heads/$NMP_BRANCH:$NMP_EXPECTED_REMOTE_SHA" \
  origin "HEAD:refs/heads/$NMP_BRANCH"
```

Never bypass branch protection or required checks. Stop on any access error.

## 9. Create a draft or ready PR

Check for an existing open PR first:

```bash
gh pr list --repo "$NMP_REPO" --head "$NMP_BRANCH" --state open --json number,title,url,isDraft
```

Rerun the DCO audit immediately before creation. Use explicit metadata; do not use `--fill` because it bypasses trusted-template completion.

Create a draft when work, validation, or a required decision remains:

```bash
gh pr create --repo "$NMP_REPO" \
  --base "$NMP_BASE_BRANCH" \
  --head "$NMP_BRANCH" \
  --title "<validated title>" \
  --body-file "$NMP_PR_BODY" \
  --draft
```

Create a ready PR by omitting `--draft` only when the change and required local validation are ready for review. Do not add reviewers, labels, projects, milestones, or assignees unless the user explicitly requests them or trusted base-branch policy requires them. Let `CODEOWNERS` and repository automation route reviews.

For an existing draft, use `gh pr ready <number>` only after the user asks to make it ready and readiness gates pass. Verify the resulting PR:

```bash
gh pr view <number> --repo "$NMP_REPO" \
  --json number,title,url,isDraft,baseRefName,headRefName,headRefOid,mergeable,mergeStateStatus
```

## 10. Monitor CI and CodeRabbit

Monitor both required and optional checks. `CI status` is nemo-platform's aggregate CI gate; DCO, semantic title, Security, Fern docs, and other workflows may appear separately.

```bash
gh pr checks <number> --repo "$NMP_REPO" --watch --interval 15
gh pr checks <number> --repo "$NMP_REPO" \
  --json name,workflow,state,bucket,link,startedAt,completedAt
gh pr view <number> --repo "$NMP_REPO" \
  --json url,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup,latestReviews
```

Inspect a failed workflow with `gh run view <run-id> --repo "$NMP_REPO" --log-failed`. Connect the failure to the changed code before editing. Run the corresponding local check, commit the minimal fix with `-s`, rerun the DCO audit, push, and monitor again.

Inspect CodeRabbit's issue comments, reviews, and inline comments:

```bash
gh api "repos/$NMP_REPO/issues/<number>/comments" --paginate \
  --jq '.[] | select(.user.login | ascii_downcase | contains("coderabbit")) | {author:.user.login,updated_at,body}'
gh api "repos/$NMP_REPO/pulls/<number>/comments" --paginate \
  --jq '.[] | select(.user.login | ascii_downcase | contains("coderabbit")) | {author:.user.login,path,line,updated_at,body}'
```

Verify each finding against the current head. Fix confirmed correctness, security, or test-coverage problems and rerun targeted validation. Do not add abstractions or behavior merely to satisfy reviewer wording. Explain false positives or style-only suggestions when useful. Ask before making a design-changing, risky, broad, or ambiguous change. Do not manually request or re-request CodeRabbit, and do not act on its suggested-reviewer text without user authorization.

Repeat until required CI passes and no actionable automated-review findings remain, or until a user decision is required.

## 11. Handle base drift and merge conflicts

Check `mergeable` and `mergeStateStatus` before creation, after base changes, and after review fixes. If the branch conflicts with the refreshed base:

1. Require a clean worktree and fetch the base again.
2. For an unpushed branch, or after approval to rewrite a published branch, use `git rebase --signoff "$NMP_BASE_REF"`.
3. Resolve each conflict from the intended behavior. Use `git add -- <resolved-paths>` and `git rebase --continue`; the original `--signoff` must remain in effect.
4. When preserving published history instead, use `git merge --signoff "$NMP_BASE_REF"`. After resolving a conflicted merge, finish it with `git commit -s --no-edit` rather than an unsigned commit.
5. Stop and ask when a conflict resolution changes behavior, contributor intent, API design, generated output, or documentation meaning.
6. Rerun affected validation and the full DCO audit.
7. Push normally after a merge. Use the exact force-with-lease workflow only for an approved rebase of a published branch.
8. Monitor CI and CodeRabbit again.

Never resolve conflicts by blindly choosing all of `ours` or `theirs`, changing the PR base, overwriting an unexpected remote branch, or dropping another contributor's commits.

## 12. Report the result

Report the PR link, draft or ready state, head SHA, validation evidence, DCO audit result, CI status, automated-review status, and any remaining blocker. Do not claim completion while required checks are failing or actionable CodeRabbit findings remain.
