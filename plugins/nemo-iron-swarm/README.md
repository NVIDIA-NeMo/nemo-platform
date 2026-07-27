# nemo-iron-swarm plugin

Red-team and harden a **deployed NeMo Platform NAT agent** with Iron Swarm. The plugin resolves an
agent already registered in NeMo Platform into an Iron Swarm manifest, then runs the
attack → defend → validate war-game against it.

iron-swarm (and garak) run in their own venvs and are invoked by subprocess — never imported —
because their pins (`litellm → httpx>=0.28`, `torch`) conflict with the platform's deps.

---

## Step 0 — Get iron-swarm

The plugin drives **iron-swarm**, a separate red-teaming tool that ships as its own package and runs
in its own venv (never imported — see the note above). iron-swarm is currently an NVIDIA-internal
package and is not yet published publicly; point the plugin at your iron-swarm checkout or package
via `NEMO_IRON_SWARM_IRON_SWARM_SPEC` (see Step 3). Everything else in this guide runs from this
nemo-platform repo.

---

## Step 1 — System prerequisites

Install these once on your machine.

### Always needed

```bash
# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# just (task runner used by iron-swarm)
brew install just        # macOS
# or: cargo install just

# git, curl, Python 3.11 — assumed present
```

### For the real war-game (Docker + OpenShell)

```bash
# Docker — use Docker Desktop or Colima on macOS
brew install colima docker
colima start
```

**OpenShell — use the native installer, not `uv tool install`.**
`uv tool install openshell` installs the CLI only; it does not install or start the local gateway
service. The native installer installs both.

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
openshell status   # should say "Status: Connected"
```

On macOS, configure the Docker compute driver so sandboxes can reach the host:

```bash
DOCKER_SOCK=$(docker context inspect --format '{{.Endpoints.docker.Host}}')
brew services stop openshell
launchctl setenv OPENSHELL_DRIVERS docker
launchctl setenv DOCKER_HOST "$DOCKER_SOCK"
brew services restart openshell
openshell status   # should say "Status: Connected"
```

The `auto-defender` gateway registration is handled automatically by `nemo iron-swarm setup` (Step 4).

Optional: `jq` for artifact inspection.

### For the Studio UI only

```bash
# Node 22 + pnpm
brew install node@22 pnpm
# or use nvm: nvm install 22 && nvm use 22

# Install the web dependencies (creates web/node_modules).
# open-studio.sh does this automatically on first run; run it manually to build the FastAPI assets too.
make bootstrap-studio
```

---

## Quickstart

Already have Steps 0–1 done and the platform bootstrapped? Three env vars and you're off:

```bash
export NMP_BASE_URL=http://localhost:8080
export NEMO_IRON_SWARM_IRON_SWARM_SPEC=/path/to/iron-swarm   # your local checkout
export INFERENCE_API_KEY=<your-nvapi-key>
export HTTPS=0

# Studio UI — easiest path (handles platform, venvs, provider, agent, browser):
cd nemo-platform
./plugins/nemo-iron-swarm/scripts/open-studio.sh [--agent <name>]

# CLI war-game:
uv run nemo iron-swarm setup && uv run nemo iron-swarm doctor
uv run nemo iron-swarm init --agent <name>
uv run nemo iron-swarm run --config iron-swarm.yaml
```

First time? Continue from Step 2 below.

---

## Step 2 — Bootstrap the platform

```bash
cd /path/to/nemo-platform
make bootstrap-python   # creates .venv and runs uv sync --frozen --all-packages
```

---

## Step 3 — Set up your environment

Set these in your shell (or add to `.zshrc` / `.envrc`):

```bash
export NMP_BASE_URL=http://localhost:8080
export NEMO_IRON_SWARM_IRON_SWARM_SPEC=/path/to/iron-swarm   # until iron-swarm is on PyPI
export INFERENCE_API_KEY=<your-nvapi-key>
```

Create a `.env` file in your iron-swarm checkout with your inference key — the war-game subprocess reads it:

```bash
echo "INFERENCE_API_KEY=sk-..." > /path/to/iron-swarm/.env
```

---

## Step 4 — Provision iron-swarm venvs

```bash
uv run nemo iron-swarm setup    # creates ~/.iron-swarm/venv (iron-swarm) and
                                 # ~/.iron-swarm/garak-venv (garak attacker)
uv run nemo iron-swarm doctor   # read-only preflight — expect all green before a real run
```

Neither command needs the platform running.

---

## Step 5 — Start the platform

```bash
# --controllers models,jobs is required:
#   models → reconciler that discovers served models (without it providers show 0 models and 404)
#   jobs   → job executor that runs the war-game task
# --host 0.0.0.0 so the OpenShell sandbox can reach the Inference Gateway via host.docker.internal
uv run nemo services run --service-group all --controllers models,jobs \
  --host 0.0.0.0 --port 8080 &

until curl -sf http://localhost:8080/health/ready >/dev/null; do sleep 2; done
echo "platform ready"
```

Create the inference provider (idempotent — safe to re-run):

```bash
printf '%s' "$INFERENCE_API_KEY" | \
  uv run nemo secrets create nvidia-inference-key --from-file - --workspace default

uv run nemo inference providers create nvidia-inference --workspace default \
  --host-url "https://inference-api.nvidia.com/v1" \
  --api-key-secret-name nvidia-inference-key
```

Wait a few seconds for the model controller to discover served models:

```bash
uv run nemo inference providers get nvidia-inference --workspace default \
  --output-format json | jq '.served_models | length'   # should be > 0
```

---

## Run the CLI war-game

```bash
# Register a NAT agent in the platform (skip if you already have one).
# Run from the nemo_platform repo root — agents/clockbot.yml is a relative path.
uv run nemo agents create --name clockbot --agent-config agents/clockbot.yml

# Resolve it into iron-swarm.yaml + scaffold:
uv run nemo iron-swarm init --agent clockbot

# Run the attack → defend → validate war-game:
uv run nemo iron-swarm run --config iron-swarm.yaml

# Optionally pass a benign suite to check false positives:
uv run nemo iron-swarm run --config iron-swarm.yaml --benign-suite requests.csv

# Show recent runs:
uv run nemo iron-swarm status
```

`init` only needs the agent **registered** (never invokes the model), so a config-only agent is
enough — no deploy, no active inference key. Add `--project-dir` only for agents with custom
components.

---

## Open the Studio UI

`scripts/open-studio.sh` handles everything from Step 4 onward automatically and opens the browser.

```bash
export IRON_SWARM_REPO=/path/to/iron-swarm   # where your local iron-swarm checkout lives
export INFERENCE_API_KEY=<your-nvapi-key>    # read from $IRON_SWARM_REPO/.env if not set

./plugins/nemo-iron-swarm/scripts/open-studio.sh [--agent <name>]
```

The `--agent` flag sets which agent to register and open in Studio (default: `clockbot`). It expects
`<name>.yml` to exist next to the script (`plugins/nemo-iron-swarm/scripts/`); a `clockbot.yml` ships
there. Point elsewhere with `AGENT_CONFIG=/path/to/agent.yml`. Also settable via `AGENT=<name>` env var.

What the script does, in order:

1. Reinstalls iron-swarm (editable) from `IRON_SWARM_REPO` into `~/.iron-swarm/venv` so local
   code changes are picked up without a manual reinstall.
2. Starts the platform on `:8080` if it isn't already running.
3. Runs `nemo iron-swarm setup` (venvs + inference credential).
4. Creates the `nvidia-inference` provider (idempotent).
5. Re-creates the clockbot agent (`RESET_AGENT=1` by default, giving a clean slate each run).
6. Clears any leftover OpenShell sandboxes from a previous crashed run.
7. Installs `web/node_modules` if missing (first run only).
8. Starts the Studio dev server on `:5173` with `VITE_FF_IRON_SWARM_ENABLED=true`.
9. Opens your browser at `https://localhost:5173/workspaces/default/iron-swarm`.

Key options (set as env vars before running):

| Variable | Default | Effect |
|---|---|---|
| `HTTPS` | `1` | Set to `0` to skip mkcert / the sudo password prompt (plain http) |
| `RESET_AGENT` | `1` | Set to `0` to keep the existing agent registration |
| `REINSTALL_IRON_SWARM` | `1` | Set to `0` to skip the editable reinstall (faster) |
| `STUDIO_PORT` | `5173` | Vite dev server port |

`Ctrl-C` stops Studio. The platform keeps running — stop it with `uv run nemo services stop`.

---

## Environment variables reference

| Variable | Default | Purpose |
|---|---|---|
| `NEMO_IRON_SWARM_IRON_SWARM_SPEC` | — | PyPI spec or local path used by `setup` to install iron-swarm |
| `NEMO_IRON_SWARM_VENV_PATH` | `~/.iron-swarm/venv` | iron-swarm venv location |
| `NEMO_IRON_SWARM_GARAK_VENV_PATH` | `~/.iron-swarm/garak-venv` | garak venv location |
| `NEMO_IRON_SWARM_DEFAULT_WORKSPACE` | `default` | Platform workspace used by CLI commands |
| `NEMO_IRON_SWARM_REQUIRE_SANDBOX` | `true` | Fail `run` if Docker/OpenShell are not ready |
| `NEMO_IRON_SWARM_OPERATOR_ENV_FILE` | `$IRON_SWARM_REPO/.env` | `.env` file the war-game subprocess reads |

All can also be set via Helm `platformConfig.iron_swarm.*`.

---

## Troubleshooting

**OpenShell installed via `uv tool install` — gateway missing.**
`uv tool install openshell` only installs the CLI binary. Uninstall it (`uv tool uninstall openshell`)
and re-install with the native curl installer above.

**`openshell status` says "connection refused" or "no compute driver" on macOS.**
The gateway is running but no compute driver is configured. Follow the Docker driver setup in
Step 1 above (`launchctl setenv OPENSHELL_DRIVERS docker …`). Once fixed, re-run
`nemo iron-swarm setup` — it re-registers the `auto-defender` gateway automatically.

**Provider shows 0 served models / inference calls 404.**
The model controller isn't running. Make sure you started the platform with `--controllers models`
(and `--controllers jobs` for the job executor).

**`INFERENCE_API_KEY` missing in the war-game subprocess.**
The subprocess reads `NEMO_IRON_SWARM_OPERATOR_ENV_FILE` (default: `$IRON_SWARM_REPO/.env`).
Confirm the file exists and contains `INFERENCE_API_KEY=...`.

---

## Appendix: venvs and internals

- `~/.iron-swarm/venv` — iron-swarm + deps, installed from `NEMO_IRON_SWARM_IRON_SWARM_SPEC`;
  invoked as `bin/iron-swarm` by subprocess.
- `~/.iron-swarm/garak-venv` — garak's `agent_breaker` attacker, isolated because of
  `litellm → httpx>=0.28` + `torch` conflicts. `setup` delegates to `iron-swarm setup`.
- The plugin itself never imports iron-swarm or garak — all communication is via subprocess +
  filesystem artifacts (YAML manifests, JSON hitlogs, event logs).
