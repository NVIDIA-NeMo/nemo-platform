# nemo-iron-swarm

Red-team and harden a **deployed NeMo Platform agent**. Point Iron Swarm at an agent already
registered in the platform and it runs an **attack → defend → validate** war-game against it: an
attacker swarm probes the agent, defenders generate guardrails and sandbox policy, and validators
check that the attacks are now blocked *and* that ordinary requests still work.

Two ways to drive it — [the Studio UI](#run-it-in-the-ui) or [the CLI](#run-it-from-the-cli). Both
need the same one-time setup below.

---

## What you need

Two environment variables. `nemo iron-swarm setup` installs iron-swarm itself, into its own venv.

```bash
export INFERENCE_API_KEY=<your-nvapi-key>
export NMP_BASE_URL=http://localhost:8080
```

<details>
<summary><b>Installing iron-swarm from a private index</b> — temporary, until it's on PyPI</summary>

Iron Swarm isn't on public PyPI yet, so `setup` has to be pointed at the index hosting it. Two
steps, and the first is done once per machine.

**1. Store your index credentials in `~/.netrc`.** Private indexes require authentication and the
plugin deliberately doesn't handle it — uv reads credentials from your environment. `~/.netrc` is
the least friction: set once, applies to every shell and every tool, and no secret ever appears in a
command line or your shell history.

```bash
cat >> ~/.netrc <<'EOF'
machine <index-host>
  login <username>
  password <access-token>
EOF
chmod 600 ~/.netrc
```

**2. Point `setup` at the index.**

```bash
export NEMO_IRON_SWARM_INDEX_URL="<index-url>"
```

That's all you need. The index is *additional* to PyPI, so iron-swarm resolves from it and every
dependency still comes from PyPI. (If a dependency fails to resolve, see the troubleshooting below —
don't set `NEMO_IRON_SWARM_INDEX_STRATEGY` pre-emptively, it weakens dependency-confusion protection.)

Ask whoever publishes iron-swarm for the index host, URL, and how to get a token — or see
iron-swarm's own README.

*Alternatives to `~/.netrc`, if you can't use it:*

- **`UV_INDEX_<NAME>_USERNAME` / `UV_INDEX_<NAME>_PASSWORD`** — these key off the index *name*, so
  you must use uv's named form `NEMO_IRON_SWARM_INDEX_URL="<name>=<url>"`. With a bare URL uv
  generates its own name and the credentials silently never apply. Needs re-exporting per shell.
- **Credentials embedded in the URL** (`https://<user>:<token>@<host>/...`) — works, but puts your
  token in shell history and anywhere the URL is echoed. `doctor` masks it, but prefer `~/.netrc`.

| Variable | Purpose |
|---|---|
| `NEMO_IRON_SWARM_INDEX_URL` | Extra index to resolve iron-swarm from, `<url>` or `<name>=<url>` |
| `NEMO_IRON_SWARM_INDEX_STRATEGY` | uv `--index-strategy`; `unsafe-best-match` when the index shadows PyPI packages |

**Check access in seconds, before installing anything.** uv cannot tell you which of these is wrong —
it reports an unauthorized index as an empty one — so ask the index directly:

```bash
curl -sS -n -o /dev/null -w '%{http_code}\n' "<index-url>/iron-swarm/"
```

| Code | Meaning |
|---|---|
| `200` | Ready — go run `setup`. |
| `401` | Credentials wrong or missing. Most often a **truncated token**: registry UIs display tokens elided, so copy with the button, not by selecting text. Check with `echo "${#TOKEN} chars"`. Also confirm the `~/.netrc` machine matches the index host, and that the username is the one the registry issued (often a service account, not your own). |
| `403` | Authenticated, but the token isn't scoped to this repository. |
| `404` | Authenticated, but iron-swarm isn't published in this repository — check the URL. |

**If `setup` still fails:**

- **`iron-swarm was not found in the package registry`** — this is almost always **authentication**, not
  a missing package. Run the `curl` check above; a `401` confirms it. It also appears when
  `NEMO_IRON_SWARM_INDEX_URL` is unset, which is what a default `setup` reports.
- **A dependency that exists on PyPI won't resolve** — the index carries a package shadowing its PyPI
  counterpart. Set `NEMO_IRON_SWARM_INDEX_STRATEGY=unsafe-best-match`.

> **Delete this whole section once iron-swarm is on PyPI.** Nothing else in this README, and no code,
> refers to it — plain `nemo iron-swarm setup` already installs from PyPI with no index
> configuration and no credentials.
</details>

**Docker + OpenShell**, which run the victim sandbox:

```bash
brew install colima docker && colima start          # or Docker Desktop

# Use the native installer — `uv tool install openshell` gives you the CLI
# without the gateway service, and the war-game needs the gateway.
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
openshell status                                     # expect "Status: Connected"
```

<details>
<summary>macOS: point OpenShell at Docker so sandboxes can reach the host</summary>

```bash
DOCKER_SOCK=$(docker context inspect --format '{{.Endpoints.docker.Host}}')
brew services stop openshell
launchctl setenv OPENSHELL_DRIVERS docker
launchctl setenv DOCKER_HOST "$DOCKER_SOCK"
brew services restart openshell
openshell status
```
</details>

---

## One-time setup

```bash
cd /path/to/nemo-platform
make bootstrap                       # Python deps + Studio assets

uv run nemo iron-swarm setup         # creates ~/.iron-swarm/venv and ~/.iron-swarm/garak-venv
uv run nemo iron-swarm doctor        # preflight — everything should be green
```

Start the platform:

```bash
# models  → discovers served models (without it, providers show 0 models)
# jobs    → runs the war-game
# 0.0.0.0 → lets the sandbox reach the Inference Gateway via host.docker.internal
# logs go to a file — backgrounding alone still prints them over your prompt
uv run nemo services run --service-group all --controllers models,jobs \
  --host 0.0.0.0 --port 8080 > /tmp/nemo-platform.log 2>&1 &

until curl -sf http://localhost:8080/health/ready >/dev/null; do sleep 2; done; echo ready
```

Watch it with `tail -f /tmp/nemo-platform.log`; stop it with `uv run nemo services stop`.

Register an inference provider. Both commands fail with `409 already exists` if you've run them
before — that's harmless, skip to the next step. To start from a clean platform instead, stop it
(`nemo services stop`), `rm -rf ~/.local/share/nemo`, and restart; the stop must come first or the
wipe silently doesn't take effect.

```bash
printf '%s' "$INFERENCE_API_KEY" | \
  uv run nemo secrets create nvidia-inference-key --from-file - --workspace default

uv run nemo inference providers create nvidia-inference --workspace default \
  --host-url "https://inference-api.nvidia.com/v1" \
  --api-key-secret-name nvidia-inference-key
```

Register an agent to attack. This example ships with the repo and needs no extra packages:

```bash
# The config references ${NEMO_DEFAULT_MODEL}. It must be a *model entity* name the platform
# discovered — not a provider model id. Entity names are lowercase-and-hyphens only; a slash gets
# rejected by the Inference Gateway with "Invalid model".
uv run nemo models list --workspace default | grep nemotron      # pick one
export NEMO_DEFAULT_MODEL=nvidia-nvidia-nemotron-3-nano-30b-a3b  # example — use what you saw

uv run nemo agents create --name react-agent \
  --agent-config plugins/nemo-agents/examples/react-agent/react-agent.yml
```

> **Egress.** The victim sandbox blocks outbound traffic unless the manifest allow-lists it, and
> iron-swarm can only auto-discover hosts by scanning a project's source — a config-only agent keeps
> its tool hosts in packaged code, so you must declare them. Entries are `host[:port]` and a bare
> host opens **443 only**; a tool using plain HTTP needs `host:80` too. Without this the victim's
> calls are dropped and tool-using attacks silently no-op while the run still reports success.
>
> `react-agent`'s `wiki_search` is a known exception: it fails even with egress open, because the
> `wikipedia` package sends no User-Agent and Wikimedia now rejects that
> ([T400119](https://phabricator.wikimedia.org/T400119)). Upstream, not iron-swarm. Its other tool,
> `current_datetime`, needs no network and exercises the tool path fine.

> `NEMO_DEFAULT_MODEL` must be set **when you run `agents create`** — the config references it as
> `${NEMO_DEFAULT_MODEL}` and the platform resolves it into the stored agent. Register it unset and
> the victim later starts with an unresolved model name. It is not needed afterwards; Iron Swarm
> reads the already-resolved config.

---

## Run it in the UI

```bash
export STUDIO_UI_VITE_FF_IRON_SWARM_ENABLED=true
uv run nemo services run --service-group all --controllers models,jobs \
  --host 0.0.0.0 --port 8080
```

Open **http://localhost:8080/studio/** → **Safety → Iron Swarm**.

1. **Manifests → New Manifest** — pick `react-agent`, accept the detected port and secrets, **Create**.
2. **Run war-game** on the manifest. The run opens on its **Swarm** tab.
3. Watch the graph light up per phase, with the live agent feed beside it. Click any node for its
   prompts and LLM calls.
4. When it finishes, **Harden** lists each recommended defense with the attack that motivated it.
   Toggle the ones you want → **Sanity check** replays the attacks against just that selection and
   reports what it blocks and any ordinary requests it breaks → **Apply to Agent** writes the
   hardened workflow back onto the agent config.

Redeploy the agent for the guardrails to take effect.

---

## Run it from the CLI

```bash
uv run nemo iron-swarm init --agent react-agent                  # manifest + saved entity
uv run nemo iron-swarm synth-benign --manifest-id react-agent --yes   # required, see below
uv run nemo iron-swarm run --manifest-id react-agent             # attack → defend → validate
uv run nemo iron-swarm status --limit 5                          # recent runs
```

`init` only needs the agent **registered**, not deployed. It saves a reusable manifest named after the
agent — that name is the `--manifest-id` every later command takes — and writes `iron-swarm.yaml` as a
*rendering* you can read. The run re-renders it from the agent each time, so editing that file has no
effect; change the manifest instead.

If your agent calls the internet, allow-list the hosts at init time — the sandbox drops everything
else, and a blocked tool usually looks like a working run because the model answers from memory:

```bash
uv run nemo iron-swarm init --agent react-agent --egress en.wikipedia.org
```

A bare host opens **443 only**; write `host:80` for plain HTTP. Hosts can't be auto-discovered for a
config-only agent, since its tool code lives in an installed package rather than in your project.

### War-game a local NAT project

No deployed agent needed — point `init` at the project directory instead:

```bash
uv run nemo iron-swarm init --project-dir ~/my-nat-agent      # asks about workflow, port, secrets
uv run nemo iron-swarm init --project-dir ~/my-nat-agent --yes  # CI: accept detected answers
```

This runs `iron-swarm init` in your terminal so you answer its questions directly, then uploads the
project and saves the result as a manifest. From there it's the same `--manifest-id` flow as above.
`--workflow`, `--port`, `--egress` and `--secrets` pre-answer individual prompts.

Your project supplies its own dependencies, so its `pyproject.toml`/`requirements.txt` must include
`nvidia-nat` (plus whatever your tools import).

**`synth-benign` is not optional.** The war-game validates two things: that attacks are blocked, and
that ordinary requests still work. Those ordinary requests are the *benign suite*, and `run` is a
pure consumer of it — it never generates one. Without a suite it fails immediately with
`smart-benign validation requires an explicit benign suite`. Generate it once and it's cached on the
manifest for every later run:

```bash
uv run nemo iron-swarm synth-benign --manifest-id react-agent          # interview, you answer
uv run nemo iron-swarm synth-benign --manifest-id react-agent --yes    # interview, defaults accepted
uv run nemo iron-swarm synth-benign --manifest-id react-agent --no-interactive   # CI: rules only
```

Prefer `run --manifest-id` over `run --config`: the cached suite is looked up by manifest id, so the
`--config` form needs you to pass `--benign-suite <csv>` yourself.

After a run produces mitigations, freeze a chosen subset and replay the recorded attacks against it:

```bash
uv run nemo iron-swarm sanity-check --manifest-id react-agent \
  --mitigations mitigations.json --replay-hitlog <fileset-ref> --keep custom_guardrail_1
```

---

## Troubleshooting

**Iron Swarm missing from the Studio side nav.** The feature flag isn't set. Export
`STUDIO_UI_VITE_FF_IRON_SWARM_ENABLED=true` *before* starting the platform — it's read at startup.

**`Missing required secrets: <NAME>`.** The agent config references `${<NAME>}` and nothing provides
it. Iron Swarm derives required secrets from the agent's *stored* config, so this means the variable
was unset when the agent was registered. Export it and re-run `nemo agents create`, or supply it via
`--env-file`.

**The victim never becomes healthy, and its log shows a pydantic `union_tag_invalid` for a
`_type`.** The agent references a component the scaffolded victim can't resolve — it installs only
`nvidia-nat[langchain]`, not the platform's NAT plugins. Platform telemetry (`nemo_files`) is
stripped for you; anything else means the agent needs a real project, so pass `--project-dir` to
`init` and let its `pyproject.toml` supply the dependency.

**The victim is healthy but every request 422s with `Invalid model`.** The workflow's `model_name`
isn't a model entity the platform knows. Entity names are lowercase letters, digits and hyphens —
a provider id like `nvidia/nemotron-3-nano-30b-a3b` is rejected for the slash. Check
`nemo models list --workspace default`, then re-register the agent with that exact name (the value
is baked in at `agents create` time).

**`openshell status` says "connection refused" or "no compute driver" (macOS).** The gateway is up but
has no driver — apply the Docker driver block above, then re-run `nemo iron-swarm setup` to
re-register the `auto-defender` gateway.

**OpenShell installed but no gateway.** You installed via `uv tool install openshell`, which is
CLI-only. `uv tool uninstall openshell`, then use the curl installer above.


**Provider shows 0 served models / inference 404s.** Start the platform with `--controllers models`.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NEMO_IRON_SWARM_IRON_SWARM_SPEC` | `iron-swarm` | Package spec `setup` installs. Override to pin a version (`iron-swarm==0.0.2`) or to develop against a local checkout |
| `NEMO_IRON_SWARM_VENV_PATH` | `~/.iron-swarm/venv` | iron-swarm venv |
| `NEMO_IRON_SWARM_GARAK_VENV_PATH` | `~/.iron-swarm/garak-venv` | garak (attacker) venv |
| `NEMO_IRON_SWARM_DEFAULT_WORKSPACE` | `default` | Workspace used by CLI commands |
| `NEMO_IRON_SWARM_REQUIRE_SANDBOX` | `true` | Fail `run` when Docker/OpenShell aren't ready |
| `NEMO_IRON_SWARM_OPERATOR_ENV_FILE` | `~/.iron-swarm/.env` | Dotenv the war-game subprocess reads |
| `STUDIO_UI_VITE_FF_IRON_SWARM_ENABLED` | `false` | Shows Iron Swarm in Studio |

All `NEMO_IRON_SWARM_*` values can also be set via Helm `platformConfig.iron_swarm.*`.

---

## How it works

iron-swarm and garak run in **their own venvs**, invoked by subprocess and never imported — their
pins (`litellm → httpx>=0.28`, `torch`) conflict with the platform's. The plugin talks to them purely
through the filesystem: YAML manifests in, JSON hitlogs and event logs out.

`init` resolves a registered agent into an Iron Swarm manifest by reading the agent registry over
HTTP, injecting the Inference Gateway URL into its LLMs (so the sandboxed victim needs no raw model
key), and scaffolding a minimal installable project for the victim container.
