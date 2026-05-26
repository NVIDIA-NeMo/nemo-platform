# Welcome to AIRE Studio

## How We Use Claude

Based on mschwab's usage over the last 30 days:

Work Type Breakdown:
  Build Feature      ████████████░░░░░░░░  60%
  Debug Fix          ████░░░░░░░░░░░░░░░░  20%
  Improve Quality    ███░░░░░░░░░░░░░░░░░  15%
  Plan Design        █░░░░░░░░░░░░░░░░░░░   5%

Top Skills & Commands:
  /clear                                ████████████████████  47x/month
  /mcp                                  ██████░░░░░░░░░░░░░░  15x/month
  /linear-ticket-for-current-branch     ███░░░░░░░░░░░░░░░░░   9x/month
  /skills                               ██░░░░░░░░░░░░░░░░░░   7x/month
  /vercel-react-best-practices          █░░░░░░░░░░░░░░░░░░░   4x/month
  /roundtable                           █░░░░░░░░░░░░░░░░░░░   4x/month
  /caveman:caveman                      █░░░░░░░░░░░░░░░░░░░   3x/month

Top MCP Servers:
  git           ████████████████████  225 calls
  linear        █████░░░░░░░░░░░░░░░   67 calls
  maas-nvbugs   █░░░░░░░░░░░░░░░░░░░   14 calls
  github        █░░░░░░░░░░░░░░░░░░░   12 calls
  context7      ░░░░░░░░░░░░░░░░░░░░    3 calls

## Your Setup Checklist

### Codebases
- [ ] platform — https://github.com/NVIDIA-NeMo/Platform (main repo — `nvidia-nemo/platform`)

### MCP Servers to Activate
- [ ] git — Local git operations (status/diff/commit/branch/checkout/log/show/reset). No external creds; runs against your worktree. Most-used by far.
- [ ] linear — Pull/create/update Linear tickets, comments, status. Sign in with your NVIDIA Linear account and grant the MCP OAuth scope.
- [ ] maas-nvbugs — Search NVBugs, pull bug details, file branches off internal bug reports. Needs an NVBugs ECI v2 token; ping the team for the current onboarding doc.
- [ ] github — PR/issue ops, code search, review reply, CI checks. `gh auth login` + the GitHub MCP server config.
- [ ] context7 — Fetches up-to-date library/framework docs (React, Next.js, etc.) instead of relying on training-data recall. No auth.

### Skills to Know About
- [ ] /clear — Drop the conversation context and start fresh. Use whenever the current thread is wandering or stale.
- [ ] /mcp — Inspect which MCP servers are connected and their tool surface.
- [ ] /linear-ticket-for-current-branch — Inspects your branch's diff, files a Linear ticket in ASTD, moves it to In Progress, and offers to rename the branch to the canonical `astd-<N>-<kebab-title>/<username>` format. Run it once you've started real work.
- [ ] /skills — List available skills in the current repo + plugins.
- [ ] /vercel-react-best-practices — Pulls Vercel's React/Next.js perf guidelines when reviewing or writing React code.
- [ ] /roundtable — Spins up three Sonnet sub-agents (Marta defensive, Devon architect, Sam pragmatic) to critique your current change from different lenses. Best after a feature lands and before opening the PR.
- [ ] /caveman:caveman — Terse output mode. Cuts roughly 75% of token spend while keeping technical substance. Toggle with "stop caveman" / "normal mode".

## Team Tips

_TODO_

## Get Started

_TODO_

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
