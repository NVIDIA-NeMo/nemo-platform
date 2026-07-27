# nemo-iron-swarm — review findings (running log)

Review-only, file-by-file walkthrough. No fixes applied. Severity: Critical / High / Medium / Low / Nit.

## Progress

Order: end-to-end trace of a run (CLI → API → job → subprocess → artifacts → events → Studio), then tests.

- [x] `cli/main.py` — triaged & closed (#6 fixed, #1/#2 rejected, #3 dropped, #4/#5 won't fix)
- [x] `cli/client.py`, `checks.py`, `provisioning.py`, `credentials.py` — triaged & closed (#7/#8/#9/#10/#15 fixed; #11–#14 won't fix)
- [x] `config.py` — triaged & closed (#17 fixed; #18 noted, #19–#21 won't fix)
- [x] `model_config.py`, `model_preflight.py` — triaged & closed (#22 fixed; #23 rejected, #24–#26 won't fix)
- [x] `agent_resolver.py`, `filesets.py` — triaged & closed (#27 retracted; #29/#33 docstrings corrected; #28/#30/#31/#32 won't fix)
- [x] `sdk.py`, `entities.py` — triaged & closed (#34/#35 fixed; #36/#37 won't fix)
- [x] `api/v2/` (`runs.py`, `schemas.py`, `_filters.py`, `manifests.py`, `events.py`, `jobs.py`), `authz.py`, `_perms.py`, `service.py` — triaged (#39 fixed; #40 blocked by platform, documented; #38/#41–#44 open)
- [x] `jobs/` 7a — lifecycle: `run.py`, `records.py`, `spec.py` — triaged (#45 fixed; #46–#49 open)
- [x] `jobs/` 7b — execution: `execution.py`, `_common.py`, `errors.py` — triaged (#50 fixed; #51–#53 open)
- [x] `jobs/` 7c — artifacts & manifest: `manifest.py`, `artifacts.py`, `defenses.py` — triaged (#54/#59 fixed; #55–#58 open)
- [x] `jobs/` 7d — synth & HITL: `synth_benign.py`, `synth_client.py`, `hitl.py`, `benign_suite.py`, `tasks/` — triaged, no fixes (all Low/Nit; #60–#64 open)
- [ ] `tasks/`, `model_config.py`, `model_preflight.py`
- [x] Studio UI (`web/packages/studio/src/components/ironSwarm/**`) — triaged (#71/#74 fixed; #72/#73/#75/#76 open)
- [x] Tests — triaged, no fixes (#65–#70 open; this session's regression tests already cover the bugs found)

---

## `cli/main.py`

Purpose: thin Typer entry point for `nemo iron-swarm ...`. Parses args, validates locally, delegates
everything real to the platform API over the SDK. iron-swarm itself is never imported.

**Triaged with the user — this file is closed.** Line numbers below are pre-fix.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 1 | Medium | `cli/main.py:142-148` | `init` prints a recoverable "the local YAML still works with `run --config`" warning, then exits 1. | **Rejected** — if the manifest didn't save, the command should fail. Intended. |
| 2 | Medium | `cli/main.py:301` | `sanity-check` never sets a failure exit code, unlike `run` (`:208`) and `synth-benign` (`:247`). | **Rejected** — blocked benign requests are a *result* to show the user, who then tries another patch set. Not a command failure. |
| 3 | Low/Med | `cli/main.py:140` | CLI calls the entity's private `_get_data_fields()`. | **Dropped** — platform-wide convention, not a local slip (`nemo_platform_plugin/entities.py:513,614`, `core/jobs/dispatcher.py:183`). A local wrapper would diverge from every other plugin. |
| 4 | Low | `cli/main.py:189-197` | A non-existent `--env-file` is silently ignored, surfacing as "Missing required secrets: ..." instead of "env file not found". | **Won't fix.** |
| 5 | Low | `cli/main.py:116` | `init -o nested/dir/x.yaml` raises a raw `FileNotFoundError` when the parent dir is missing. | **Won't fix.** |
| 6 | Nit | `cli/main.py` (6 commands) | `IronSwarmConfig.get()` / `require_preflight` / `make_sdk(base_url())` / `workspace or config.default_workspace` duplicated verbatim in every command. | **Fixed** — `_CommandContext` + `_command_context(workspace, preflight=...)` (`:31-56`). `status`'s preflight opt-out is now explicit at the call site. |

Verified clean: `status` correctly forwards `--limit` to the SDK (`:313`) — the known pagination bug
is downstream in `sdk.py`.

### Design note: the two `run` paths validate secrets at different times

`run --config` checks victim secrets client-side up front (`main.py:216-224`); `run --manifest-id`
defers to the job (`jobs/execution.py:140`). **Not a defect** — on the saved-manifest path no manifest
exists yet: the server re-resolves it live from the stored agent ref (`jobs/manifest.py:133`), and only
then are the required secrets known. The client also can't see the platform Secrets service that
`build_model_env` resolves from (`jobs/_common.py:77-83`), so an early client check would raise false
"missing secret" errors. Studio only ever uses `manifest_id`, so the server check is the real gate.

| # | Severity | Location | Finding |
|---|---|---|---|
## `config.py`

Purpose: the operator config model (`NEMO_IRON_SWARM_*` / Helm), the two-venv architecture it
encodes (garak kept separate because it drags `litellm`'s `httpx>=0.28` and `torch` into conflict
with iron-swarm's pins — the plugin owns *where*, iron-swarm owns *what version*), and the secret
plumbing (`read_env_file`, `missing_secrets`).

Verified correct: `missing_secrets` resolves `secrets_file` as `manifest_path.parent / secrets_file`,
which handles both the relative form and the absolute path `jobs/manifest.py:173` writes — `Path("/a/b")
/ "/abs/.env"` returns `/abs/.env`. Now commented in place.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 17 | Medium | `config.py:101` vs `cli/checks.py:107` | Secrets were counted as satisfied by *key presence*, so `export KEY=""` or a `KEY=` dotenv line passed the gate and resurfaced minutes later as a provider auth error. `operator_env_ok` used truthiness for the same class of value. | **Fixed** — new `_non_empty_keys()` filters blank/whitespace values across all three sources. |
| 18 | Medium | `config.py:167-169` | `state_dir` is derived as `venv_path.parent`, so overriding `NEMO_IRON_SWARM_VENV_PATH` silently relocates the durable run-events log (`api/v2/events.py:42`) while `operator_env_file` keeps its own default — the state dir splits in two. | **Noted, not fixed** — latent only: nothing overrides that env var today, so the defaults hold. Revisit if the venv path is ever relocated. |
| 19 | Low | `config.py:93-95` | `missing_secrets` returns `[]` on unreadable/malformed YAML, so a corrupt manifest passes the secret gate. Deliberate, but the gate goes inert exactly when something is already wrong. | **Won't fix.** |
| 20 | Low | `config.py:68-75` | `read_env_file` doesn't strip inline comments: `A=value # note` yields `'value # note'` (verified). | **Won't fix.** |
| 21 | Nit | `config.py:131-137` | `iron_swarm_spec` defaults to unpinned `"iron-swarm"`; two hosts running `setup` a week apart get different versions with no record. | **Won't fix.** |

## `model_config.py` + `model_preflight.py`

Purpose: iron-swarm's five model-driven roles collapsed into three user-facing groups (`attack`,
`analysis`, `agent`), each an all-optional `ModelChoice` where `None` means "built-in default" — so an
unset config reproduces prior behavior exactly and the feature is purely additive. `model_config.py`
imports nothing plugin-internal, so entity / job spec / API depend on it without cycles.
`model_preflight.py` probes `GET {base_url}/models` before the (minutes-long) sandbox spin-up and hands
back the reachable model list so the error can offer real options.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 22 | Medium | `model_preflight.py:64-65` → `jobs/run.py:136-137` | Every `status_code >= 400` set `auth_ok=False`, so a provider 500/429/503 was reported as "The attack model credentials were rejected" — sending the operator to rotate a working key. | **Fixed** — `auth_ok` is strictly 401/403; other error statuses clear a new `status_ok` → `reason="provider_error"`, with a message stating the credentials were accepted and it's the provider's side. |
| 23 | Medium | `model_preflight.py:90` | `model not in result.available` is an exact string match and a miss hard-blocks the run, while the no-`/models` case right above it soft-passes. A provider spelling ids differently would reject a working model. | **Rejected** — exact provider-accepted names are the intended contract; a name the provider doesn't list *should* block. |
| 24 | Low | `model_preflight.py:22,51` | `_PROBE_TIMEOUT_S` applies only to the client `probe_models` constructs; a caller-supplied one brings its own. Latent — no caller passes one. | **Won't fix.** |
| 25 | Nit | `jobs/run.py:140` | `verdict.available[:20]` truncates silently with no "…and N more". | **Won't fix.** |
| 26 | Nit | `model_config.py:29,31` | `ATTACK_DEFAULT_BASE_URL` has a trailing slash, `ANALYSIS_DEFAULT_BASE_URL` doesn't. | **Won't fix.** |

Design note (not a defect): the four default literals (`model_config.py:28-31`) are hand-mirrored from
iron-swarm's own constants and nothing detects drift — unavoidable while the plugin deliberately never
imports iron-swarm, but it is a manual sync point.

## `agent_resolver.py` + `filesets.py`

Purpose: turn a deployed-agent reference into a ready iron-swarm manifest (parse ref → fetch config →
resolve victim port from a running deployment → IGW-inject → materialize workflow + scaffold → build
the manifest dict), and download/expand an uploaded NAT project bundle from a fileset.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 27 | ~~Medium (sec)~~ | `filesets.py:79-81` | Claimed the size cap trusts the attacker-controlled `ZipInfo.file_size`, allowing a bomb to under-report and expand past the cap. | **Retracted — false positive.** `zipfile` also *reads* against `file_size`: a member claiming less than its data is truncated at the declared length and fails its CRC. Lying yields `BadZipFile`, not an oversized extraction. Proven by `test_a_zip_under_reporting_its_size_cannot_beat_the_cap`; the reasoning is now in the function docstring so it isn't "fixed" again. |
| 28 | Medium | `agent_resolver.py:102-103` | `model_override` replaces `model` on every openai/nim LLM, including one that kept its own explicit `base_url` (preserved by the `setdefault` at `:100`) and so is not gateway-bound — it may get a model name that provider doesn't have. | **Docstring corrected only**, behavior unchanged. |
| 29 | Medium | `agent_resolver.py:177` | `sorted(found) or ["INFERENCE_API_KEY"]` fires only when nothing else is found, so an agent declaring `GITHUB_TOKEN` loses `INFERENCE_API_KEY` — contradicting the docstring's "always have a usable key name". | **Docstring corrected only**, behavior unchanged. |
| 30 | Low (sec) | `filesets.py:75` | `stat.S_ISLNK(info.external_attr >> 16)` is only meaningful for Unix-created zips (`create_system == 3`); a Windows-flagged archive skips the symlink check. | **Won't fix.** |
| 31 | Low | `agent_resolver.py:164-165` | `"${A}/${B}"` is captured as one secret name `A}/${B`. | **Won't fix.** |
| 32 | Low | `agent_resolver.py:295`, `filesets.py:93,96` | Silent first-match picks (`running[0]`, `zips[0]`) with no warning when several candidates exist. | **Won't fix.** |
| 33 | Low | `agent_resolver.py:18-21, 90` | Docstring justified duplicating `inject_gateway_url` "to avoid a cross-plugin dependency", but that dependency now exists (`pyproject.toml:15`, `api/v2/runs.py:18`), leaving the copy free to drift — and it already has. | **Docstring corrected**; consolidating the copy left for later. |

## `sdk.py` + `entities.py`

Purpose: mounts `client.iron_swarm`, with **two execution paths** — `run`/`synth_benign` via
`run_local` (in-process, blocking, TTY interview) and `submit`/`sanity_check` via `submit_remote`
(dispatched, pollable, `driver="service"` HITL). Same `IronSwarmRunJob` either way; only the scheduler
and interview transport differ. `entities.py` holds the two persisted shapes, with `IronSwarmRun`
defaulting to `status="failed"` / `returncode=-1` so a never-updated record reads as failed.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 34 | **High** | `sdk.py:83-87`, `:100-104` | **Root cause of the known `status --limit` bug.** `entities.list` returns `SyncDefaultPagination`, whose `__iter__` auto-paginates (`_base_client.py:276-279`), so `page_size` bounds the *page*, not the total — iterating returned every run. `--limit 5` over 200 runs meant 40 requests and 200 rows. Same in `_ManifestsResource`. | **Fixed** — shared `_list_newest()` caps iteration with `itertools.islice`, one request. Regression-checked: reverting the one-line fix fails 3 of the 6 new tests in `test_sdk_resources.py`. |
| 35 | Medium | `sdk.py:89-91` | `latest()` called `list(limit=1)`, downloading the whole history one record per request to take `[0]`. | **Fixed** by #34. |
| 36 | Low | `sdk.py:188-189`, `:220-221` | `submit`/`sanity_check` resolve the target via env-derived `base_url()` while `run` uses `self._platform` — a client built against one platform can submit to another. | **Won't fix.** |
| 37 | Low | `sdk.py:225-257` | The async resource exposes only `run`/`synth_benign` — no `runs`, `manifests`, `submit`, `sanity_check`. | **Won't fix.** |

Design note (architecture, not a defect): the local-vs-dispatched fork happens deep inside
`jobs/run.py:324` rather than at the boundary, so ~60 lines of shared setup must be correct for both
callers. Visible consequences: `run.py:305-311` materializes an env file solely because Studio submits
without one, finding #16's secret check lands at different points per path, and `test_run_service.py`
(691 lines, the largest test file here) largely pays for the split. The TTY-interview constraint
justifies two paths; containing them behind one driver interface is a future refactor.

## `api/v2/` + `authz.py` / `_perms.py` / `service.py`

Purpose: five routers under `/apis/iron-swarm` (healthz, runs, manifests, events, jobs). Authz is
consistent — one `AuthzScope("iron-swarm")` in its own module to avoid import cycles, typed
permissions (`iron-swarm.runs.*`, `iron-swarm.manifests.*`), `@scope.read|write` + `@path_rule` on
every handler, no bare permission strings.

Done well: `_filters.py` converts a typo'd `filter[foo]=bar` into a 422 rather than the 500 FastAPI
would produce from the raw `ValidationError`; and `events.py:141-145` documents a real self-deadlock —
the fileset fallback calls back into this same platform, so on the event loop the server cannot answer
its own lookup (~181s of SDK retries with everything, including the inference gateway, frozen). Now
offloaded to a worker thread.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 39 | Medium | `manifests.py:179-185`, `:327` | `iron-swarm inspect` / `init` ran with **no timeout** inside a request. A wedged subprocess pins its threadpool worker for the process's lifetime; enough of them starve the pool. | **Fixed** — shared `_run_iron_swarm()` with a 120s ceiling; timeout returns **504**, distinct from the 400 for a non-zero exit. |
| 40 | Medium | `runs.py:112-159` | `apply-mitigation` overwrites another plugin's `Agent.config` while gated only on `iron-swarm.runs.apply`; `workflow_yaml` is never verified to have come from this run. | **Cannot fix as proposed.** Adding `AgentPerms.CREATE` fails the platform's authz derivation: permission ids outside a service's own namespace are **fail-closed DENY** (`test_service.py:44`). A deliberate platform boundary. Documented at the decorator: `iron-swarm.runs.apply` is effectively an agent-write grant — assign it accordingly. |
| 38 | Low | `runs.py:169-183` | **Known bug (live-test #4).** The route declares `{name}` and never reads it, so compose-defense against a non-existent run returns **200**. Either look the run up (404) or drop `{name}` — the handler is pure. | **Open.** |
| 41 | Low | `events.py:96-102` | `EventHub._streams` is never evicted — one entry per `(workspace, run)` for the process's lifetime. | **Open.** |
| 42 | Low | `events.py:69-73` | `publish` does synchronous `open`/append on the event loop, on the hot ingest path. | **Open.** |
| 43 | Nit | `events.py:61,73` | `_seq` is seeded and incremented but never read (`history()` uses line numbers) — dead state implying a mechanism that doesn't exist. | **Open.** |
| 44 | Nit | `events.py:140,163` | `get_events` / `_fileset_fallback` reach into `stream._path`; make it a property. | **Open.** |

## `jobs/` 7a — lifecycle (`run.py`, `records.py`, `spec.py`)

Purpose: the two-phase job lifecycle. `compile()` (API side, async) builds the `PlatformJobSpec` and
**pre-creates** the run record so Studio can open a live view before the worker starts; `run()` (worker,
sync) wraps everything in one error boundary that classifies any exception into a `RunFailure`, records
it, and returns `{"status": "failed"}` — which `dispatcher._exit_code_for` maps to a non-zero exit.
`records.py` is uniformly best-effort: no recording failure can ever fail the war-game.

Key subtlety: **entity updates replace the whole record** (`records.py:43`). `run.py:384-386` already
guards `source_run` against this; #45 was the same trap in the other caller. `spec.py` is the cleanest
file in the plugin — every field documents why it exists. No findings there.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 45 | Medium | `run.py:247-257` | `_record_failure` built `_run_data("", 0, …)` and `_update_run` overwrote the pre-created row wholesale, so a run failing after pre-creation lost the `agent`/`port` Studio was already showing — the Hardening list rendered a failed run against nothing. | **Fixed** — new `_run_facts()` reads the recorded agent/port back and carries them forward. Regression-checked: reverting the read-back fails `test_failure_preserves_the_precreated_agent_and_port`. |
| 46 | Medium | `run.py:276,292,293` → `records.py` | `_manifest_models`, `_cached_benign_suite`, `_manifest_rounds` each issue a separate `get_entity_by_name` for the *same* manifest — three round-trips where one would do. | **Open.** |
| 47 | Low | `run.py:382` | `_save_events_fileset(run_name=outcome.record_name or "")` runs before the one-shot path creates its record (`:404`), so that path keys the events fileset on `""`. | **Open.** |
| 48 | Nit | `run.py:375-380` | `if config.get("stop_after_synth"): pass` — empty branch standing in for "no hitlog here". | **Open.** |
| 49 | Nit | `run.py:198-201` | `compile()` snapshots `HOME`/`DOCKER_HOST`/`XDG_CONFIG_HOME` from the **API** process into the job spec; correct only while API and worker share a host, which the docstring assumes but doesn't assert. | **Open.** |

## `jobs/` 7b — execution (`execution.py`, `_common.py`, `errors.py`)

Purpose: the two subprocess strategies (one-shot `iron-swarm run`; Studio's service-driven
sandbox-up → synth HITL → reuse-run) and the failure taxonomy behind them.

Invariants worth preserving: every *primary* iron-swarm call goes through `_run_iron_swarm`, which
clears a stale `run-error.json` first (so an earlier command's cause can't be misattributed) and prefers
that structured file over log-scraping — teardown calls deliberately bypass it so they never write the
error file. Once the run record exists, every failure path returns a `RunOutcome` carrying `record_name`,
so a mid-run crash finalizes the record instead of orphaning it as `running`. `_drive_service_run` wraps
post-`up` work in `try/finally` so a SIGTERM during the minutes-long HITL wait still tears the victim
down — and the `except Exception` at `:232` correctly does not swallow `SystemExit`, so that path holds.

`errors.py`'s `_heuristic_category` checks "run reached its final summary" markers *before* the cue scan,
because cues like `docker`/`openshell` appear in every healthy log; a completed run exiting non-zero is
`validation_failed`, a *result* rather than a crash (`test_errors.py:29` records learning this).

Verified clean: `_pin_synth_storage` rewrites a manifest in place, but always the *materialized* copy
under job storage (`synth_benign.py:130`), never the user's `iron-swarm.yaml`.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 50 | Low (sec) | `_common.py:152-154` | Second instance of #10: the victim dotenv — which its own comment notes "holds provider creds" — was `write_text`-ed at default umask (0644) then chmod'd to 0600, leaving a world-readable window. | **Fixed, and de-duplicated:** new `config.write_env_file()` is the single 0600-at-creation writer; both `credentials.py` and `_common.py` use it, and `credentials.py`'s hand-rolled `os.open` block is gone. |
| 51 | Low | `errors.py:214` | `_is_network_error` treats any `TimeoutError` as `network`; `subprocess.TimeoutExpired` subclasses it, so the timeouts added in #9/#39 would classify a wedged *local* subprocess as a connectivity problem. | **Open.** |
| 52 | Low | `run.py:352-355`, `execution.py:261-264`, `:304-307` | The "write cached suite to `benign-suite.csv`, set `suite_path`" block is duplicated three times across two modules. | **Open.** |
| 53 | Nit | `errors.py:143-157` | `classify_subprocess` builds an `IronSwarmRunError` purely as a value carrier — never raised, only `.as_failure()`'d. Returning a `RunFailure` would say what it means. | **Open.** |

## `jobs/` 7c — artifacts & manifest (`manifest.py`, `artifacts.py`, `defenses.py`)

Purpose: rebuild the on-host `iron-swarm.yaml` per run (an agent-source manifest is re-resolved from the
agent ref every run so a redeploy is picked up — which is *why* stored choices like intensity/defenders/
port must be re-injected each time), save Studio-facing artifacts, and compose a selected defense subset.
`defenses.py` rests on one structural fact: a guardrail is a keyed global `middleware` entry plus a name
in a component's `middleware` list, and guardrails are independent — so deselecting one is a clean delete.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 54 | Medium | `defenses.py:92-105` | `_drop_middleware_refs` scanned only `functions`/`function_groups`, **not `workflow`** — which NAT also treats as a middleware-bearing component. Deselecting a guardrail removed it from the global map and from function refs but left the `workflow` entry naming it, so the composed YAML shipped a dangling reference and the victim failed config validation ("middleware type not found") and never served — the exact symptom `agent_resolver.py:248-252` documents. Hit the harden flow's main path: preview a subset → freeze into a sanity check → victim won't start. **Reproduced before and after.** | **Fixed** — `workflow` is now pruned alongside the other components. New `test_compose_leaves_no_dangling_middleware_reference` asserts the general invariant (every surviving ref names an existing middleware) across all selections, so the class of bug can't return via another component. Regression-checked: removing the fix fails both compose tests. |
| 59 | Nit | `artifacts.py:123` | Over-long `logger.warning` from commit `e82f502e2` — the sole reason `ruff format --check` failed all session. | **Fixed** — formatted; the plugin is now format-clean. |
| 55 | Low | `artifacts.py:8` | Module docstring claims "All best-effort — capturing an artifact never fails the run", but `_replay_args` (`:45`) and `_uploaded_benign_suite` (`:58`) deliberately raise. The code is right; the docstring is wrong. | **Open.** |
| 56 | Low | `artifacts.py:43,56` | Both take the first file alphabetically from a fileset that may hold several, with no warning (same class as #32). | **Open.** |
| 57 | Low | `manifest.py:83-85` | `defenders: []` means "use iron-swarm's defaults", not "no defenders" — a caller disabling defenders with an empty list silently gets all of them. | **Open.** |
| 58 | Nit | `artifacts.py:62-95` | `_save_mitigations` and `_save_validation` are the same function modulo a filename and a result key. | **Open.** |

Design note: `DEFENDER_ENTRIES` (`manifest.py:39-59`) hardcodes iron-swarm **implementation import paths**
as strings. Same manual-sync hazard as the `model_config.py` defaults, but with a worse failure mode — a
rename in iron-swarm surfaces as a runtime defender failure rather than a config error.

## `jobs/` 7d — synth & HITL (`synth_benign.py`, `synth_client.py`, `hitl.py`, `benign_suite.py`, `tasks/`)

**No fixes applied — the whole chunk is Low/Nit and in good shape.**

`hitl.py` is the strongest design in the plugin. The interview is a human-in-the-loop conversation
relayed through the job's `status_details`; two details make it correct rather than merely working:
**round stamping** (`:81-82`) — every publish increments a counter Studio must echo, so a multi-round
interview can never read a stale answer — and an **asymmetric failure policy** (`:83-97` vs `:105-108`):
a failed *publish* retries 3× then aborts loudly (a silently-dropped prompt would hang the interview to
the 30-minute deadline with no explanation), while a failed *poll* retries indefinitely because a human
is thinking. Opposite treatments, each right for its side. `drive_synth_hitl` takes `publish`/
`await_response` as parameters purely so the loop is testable without a platform.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 60 | Low | `synth_benign.py:108-123` | `IronSwarmSynthBenignJob.run` returns a failed result but never records it on the run entity, unlike `IronSwarmRunJob.run:229`. A failure before `_run_service_driven` would strand a supplied `run_name` record at `running`. **Latent** — verified no caller populates `run_name`. | **Open, won't fix now.** |
| 61 | Nit | `synth_benign.py:55`, `:180` | `SynthBenignSpec.run_name` is dead: declared and consumed, never produced. | **Open.** |
| 62 | Low | `synth_client.py:73-77` | `_free_port` binds/releases then hands the number to `serve` — a TOCTOU window; losing the race surfaces as a confusing "not healthy within 90s". | **Open.** |
| 63 | Low | `synth_client.py:110-117` | `_terminate` signals only the direct child; `iron-swarm serve` descendants could outlive the job on the provisioned host. Needs a process-group kill (speculative — depends on whether `serve` forks). | **Open.** |
| 64 | Nit | `hitl.py:111` | An operator who deliberately deletes every suite row is indistinguishable from an empty response; the run proceeds silently with no benign suite. | **Open.** |

## Tests (19 files, ~3,500 lines, 234 passing, **83.27% coverage**)

**No fixes applied** — the regression tests added during this review already cover the bugs found.

The finding that matters is the relationship between "83% coverage" and "two real bugs on primary user
paths, found by reading". They failed in three distinct ways, none of which a coverage number can see:

- **#34 (pagination) — no test existed.** `sdk.py` was already at 92% line coverage: the lines *ran*,
  they just ran wrongly. A comprehension over an auto-paginator executes identically whether it yields
  5 rows or 200 — only an assertion on the **count** catches it.
- **#54 (dangling middleware) — a test existed and passed.** `defenses.py` sat at 90%. The fixture had
  `workflow: {"_type": "react_agent"}` with no `middleware` key, so the unhandled branch was
  unreachable *from the fixture*. It verified the behavior the fixture permitted, not what production sees.
- **Live Bug #1 — a bare `Mock` lied.** `get_entity_by_name` returns a generic `Entity`, so
  `run.events_fileset` raised `AttributeError` in production, while `Mock().events_fileset` is a truthy
  Mock. Now properly fixed with the reasoning left in place at `test_events.py:96-97`.

Missing test · unrepresentative fixture · mock lying about a real type. Coverage sees none of them.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 65 | Medium | `tests/` | **No integration tests** — only `tests/unit/`, though the Makefile has a `test-integration` target. The live shakedown *was* the integration suite, run by hand, and found 4 bugs the automated suite could not. Nothing prevents them regressing. | **Open** — the finding that matters; worth scoping as its own piece of work. |
| 66 | Medium | `tests/` (no `conftest.py`) | Zero shared fixtures; `_ctx`, `_config`, `_capturing_sdk`, `_provisioned_config` are re-declared per file. That is *why* fixtures drift from production shapes — exactly how #54 hid. | **Open.** |
| 67 | Medium | `test_artifacts.py:19-32` | Codifies implementation, not behavior: patches `_events_path` *and* `upload_file_to_fileset`, then asserts `assert_called_once_with(sdk, events_file, workspace="default")`. Reordering an argument fails the test with no behavior change; only a return-value passthrough is really verified. | **Open.** |
| 68 | Low | `test_artifacts.py:18,38,54` | Still uses bare `sdk = MagicMock()`. Benign today (passed through only), but it is the pattern that hid live Bug #1. | **Open.** |
| 69 | Low | `test_run_service.py` | 691 lines, 117 mock constructs — highest mock density in the plugin, a direct cost of the local-vs-dispatched fork described in the `sdk.py` design note. | **Open.** |
| 70 | Low | coverage | Weakest branch coverage sits on the error/best-effort paths: `credentials.py` 60%, `records.py` 64.6%, `cli/main.py` 66.3%, `artifacts.py` 68.9% — the "never fail the run" handlers that swallow silently, so a defect there is invisible in production too. | **Open.** |

Assessment: the suite is solid at unit level, and `test_errors.py` / `test_compose_defense.py` encode
real domain reasoning. Its weakness is **level**, not rigor — everything is mocked at exactly the
boundary the bugs live on. #65 is the root; the rest are consequences.

## Studio UI (`web/packages/studio/src/components/ironSwarm/**`)

Reviewed at logic level (data flow, polling, state derivation), not pixel level.

`swarmModel.ts` is the centrepiece: the topology is **authored, not force-simulated** (hand-laid
coordinates ported from the demo SVG), and `deriveSwarmState` is a **pure fold** over the ordered event
stream — documented as deterministic "so late SSE subscribers converge correctly". State is a function of
the event prefix, not of arrival timing. `nodeForAgent` resolves iron-swarm's agent names (which don't
equal node ids) by exact title → role → name substring → `validator_kind`; that layered fallback is what
makes clicking a leaf node show its own transcript.

| # | Severity | Location | Finding | Verdict |
|---|---|---|---|---|
| 71 | Medium | `useSwarmEvents.ts:9,30` | `MAX_EVENTS = 500` with `slice(-500)` dropped the **oldest** events, breaking the very determinism `deriveSwarmState` promises: the fold starts from `pending` and needs every `phase_started`/`round_started`, so truncating the front silently corrupted phase and round on runs over 500 events (the live test saw 53; a multi-round `thorough` run exceeds it). | **Fixed** — the full prefix is retained, with the reasoning in the hook docstring so no cap gets re-added. |
| 74 | Low/Med | `useSwarmEvents.ts:18` | Flat `refetchInterval: 1000` with no terminal gate — polled forever while the tab stayed open, even on a finished run. Every other hook here uses a status-aware interval (`getJobRefetchInterval`); this was the one skipping the local convention. | **Fixed** — new `isTerminal` param stops the poll; the trailing fetch still lands because the last batch advances `afterId` and changes the query key. Both callers updated (run status / job terminal status). |
| 72 | Medium | `useSwarmEvents.ts:28` | `ts: Date.now()` stamps **client receive time**, not event time. After a reload or via the fileset-replay path the whole history arrives in one poll, so every event shares a timestamp — the Message Feed timeline is meaningless exactly when reading back a finished run. | **Open.** |
| 73 | Medium | `useMitigations.ts:224` → `HardenPanel.tsx:162-165` | `defenses: query.data?.defenses ?? []` allocates a new array each render while `query.data` is undefined, and `HardenPanel`'s effect depends on `[defenses]` and calls `setSelected`. That is a setState→render→effect→setState cycle during the artifact download (bounded: the panel only mounts when `hasMitigations`), and any later refetch would silently reset the user's defense toggles. One-line `useMemo` fix. **(verify live)** | **Open.** |
| 75 | Low | `useSwarmEvents.ts:25,31` | `id: … : Date.now()` — a non-numeric id pushes `afterId` to ~1.7e12, and since the server filters `line_no <= after_id`, the stream is **permanently dead** for that run. The defensive fallback is worse than failing. | **Open.** |
| 76 | Low | `useRunWarGame.ts:20-31` | Polls up to 60× with no unmount/abort check, then calls `navigate()` — which can fire after the user has left the page. | **Open.** |

---

| # | Severity | Location | Finding |
|---|---|---|---|
| 16 | Low | `jobs/run.py:282-291` → `jobs/execution.py:140` | On the `manifest_id` path `check_victim_secrets` runs *after* model preflight and the live agent re-resolution, so a missing victim secret costs minutes instead of seconds. Hoisting it to just after `_materialize_manifest` (`:291`) fixes it for the CLI and Studio both. **Open.** |

## `cli/client.py`

Purpose: base-URL resolution (`NEMO_BASE_URL` → `NMP_BASE_URL` → `http://localhost:8080`) and lazy
SDK construction. No findings; the lazy `nemo_platform` import (`:18`) deliberately keeps
`doctor`/`setup` importable before the platform is installed.

## Preflight & setup layer — `checks.py`, `provisioning.py`, `credentials.py`

Purpose: the host-readiness contract for the "iron-swarm runs isolated in its own venv" design.
`checks.py` probes (iron-swarm venv, garak venv, inference credential, Docker, OpenShell gateway);
`provisioning.py` creates the two venvs (garak delegated to `iron-swarm setup`, which owns the pin);
`credentials.py` resolves iron-swarm's own `INFERENCE_API_KEY` (it calls the public NVIDIA endpoint
directly, not the platform gateway) into a 0600 operator dotenv.

| # | Severity | Location | Finding |
|---|---|---|---|
| 7 | Medium | `cli/checks.py:58` | `"Connected" in proc.stdout` also matches `Not Connected` / `Last Connected:`. A down gateway can report ✓, pushing the failure deep into the job. **Fixed** — new `gateway_status()` strips ANSI and matches the whole `Status:` field; `openshell_gateway_ok` compares it to `connected` and reports the actual value on failure. |
| 8 | Medium | `cli/checks.py:33,49` ← `main.py:96` | `require_preflight` runs the full check set on every mutating command, including `docker info` (20s timeout) and `openshell status` (30s). A wedged daemon stalls every command ~50s. **Fixed** — `PROBE_TIMEOUT_SECONDS = 5` for both probes, with an explicit `TimeoutExpired` branch each ("the daemon looks wedged"). Worst case ~10s, down from ~50s. *A TTL cache was tried first and reverted: the 20s/30s were timeout ceilings, not typical cost (a healthy daemon answers in <1s), so caching bought ~1s on the happy path and introduced a stale-pass window — Docker dying after a cached pass would sail through preflight and fail deep in the job.* |
| 9 | Medium | `cli/provisioning.py:23` | `run_subprocess` has `capture_output=True` and no `timeout`. The multi-minute `uv pip install` shows no progress and can hang indefinitely. **Fixed** — output inherits the terminal (also surfaces uv's stdout-reported failures) and `SUBPROCESS_TIMEOUT_SECONDS = 900` bounds every call, with a distinct timeout message. |
| 10 | Low (sec) | `cli/credentials.py:52-53` | The API key is written with default umask (0644) and only chmod'd to 0600 afterwards — world-readable window. **Fixed** — `os.open(..., 0o600)` applies the mode at creation; parent dir now `mode=0o700`. The trailing `chmod` stays because `O_CREAT`'s mode is ignored for an existing file. |
| 11 | Low | `cli/credentials.py:52` | Dotenv values written unquoted/un-escaped (`f"{k}={v}\n"`); a value containing a newline corrupts the file. Rewrite also drops comments/formatting. |
| 12 | Low | `cli/credentials.py:31` | `except Exception: pass` makes "Secrets unreachable", "auth failed", and "secret absent" indistinguishable. Log at debug. |
| 13 | Low | `cli/provisioning.py:39-45` | `--force` never deletes `venv_path`; whether it truly recreates depends on `uv venv`'s overwrite behavior. Add an explicit `rmtree` if a clean slate is the intent. **(verify)** |
| 14 | Nit | `cli/provisioning.py:45` | Python `3.12` hardcoded as a `uv venv` argument; the `<3.13` cap belongs in `config.py` with the other pins. |
| 15 | Nit | `cli/checks.py:20` | `CheckResult` NamedTuple's named fields are never used — all callers unpack positionally (`main.py:44,69`). **Fixed** — `print_checks`, `require_preflight`, `doctor`, and `setup` now use `check.label/.ok/.detail`. |

Covered by `tests/unit/test_preflight.py` (new): gateway-status parsing incl. the `Not Connected` /
`Last Connected:` cases that defeated the old substring match, plus cache hit / expiry / failure-not-cached.

Design note (not a defect): the inference credential has two precedence orders — Secrets → env →
prompt at setup time (`credentials.py:20-43`), but env wins over the dotenv at run time because the
job injects with `setdefault` (`credentials.py:23-24`). Confusing when debugging; confirm at the job layer.
