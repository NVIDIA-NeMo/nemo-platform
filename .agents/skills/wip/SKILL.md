---
name: wip
description: "Snapshot work state across all branches and stashes into ~/work-tracker.md. Focus: what exists where, what's blocked, what can be cleaned up. Run before stashing, switching branches, or ending a session."
---

# WIP — Cross-Branch Work Tracker

Maintain `~/work-tracker.md` as a map of all in-progress work across branches and stashes — not a drill-down into the current branch, but a bird's-eye view of everything that exists and needs attention.

## When to use

- Before stashing or switching branches
- At the start of a session ("where was I?")
- When the user asks what's in progress, what's stashed, or what can be cleaned up
- Periodically to prune orphaned stashes and dead branches

## Steps

1. **Read the existing tracker** so existing notes (blocked items, recovery flags) are preserved:
   ```
   Read ~/work-tracker.md
   ```

2. **Gather state** — run all of these:
   ```bash
   git branch | grep htolentino          # all personal branches
   git stash list                         # all stashes
   git worktree list                      # active worktrees
   ```
   Then for each branch that looks active, run:
   ```bash
   git rev-list --count origin/main..<branch>   # commits ahead
   git log --oneline origin/main..<branch> | head -3
   ```

3. **Write `~/work-tracker.md`** using this structure — keep it terse:

```markdown
# Work Tracker

> Run `/wip` to refresh. Focus: what exists where, what needs attention, what can be dropped.

Last updated: YYYY-MM-DD

---

## Branches with in-progress work

| Branch | Commits ahead | Status | Notes |
|--------|--------------|--------|-------|
| `branch-name` | N | active / paused / blocked | one-liner |

---

## Stash inventory

| # | Label | Was on branch | Recover? |
|---|-------|--------------|---------|
| 0 | `label` | `branch` | Yes/No/Maybe — why |

---

## Blocked items

| Item | Blocked on |
|------|-----------|
| feature | what's needed to unblock |

---

## Can probably be cleaned up

- stash@{N}: reason it's probably safe to drop
- branch: why it looks dead
```

4. **Rules:**
   - Never silently remove a stash entry or branch row — mark as "probably drop" and let the user decide
   - Status column: `active` (current focus), `in progress` (has commits, being worked on), `paused` (has commits, not being touched), `blocked` (waiting on something external)
   - When the user is about to stash, add the new stash@{0} row first and shift all existing numbers down
   - Keep the "Can probably be cleaned up" section honest — stashes on non-existent branches are usually safe to drop; stashes on merged branches should be verified
   - Absolute dates only

5. **Confirm** with one line: `"Tracker updated — N branches active, M stashes, K items to clean up."`
