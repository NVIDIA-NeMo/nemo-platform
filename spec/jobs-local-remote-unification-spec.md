# Jobs Local/Remote Unification Spec

## Summary

This spec proposes an end-state jobs model where NeMo Platform removes the architectural distinction between "local" and "remote" job execution.

The key change is:

- `run` and `submit` remain as interaction modes
- all execution goes through the jobs service contract
- local execution becomes a normal jobs deployment shape, not a separate code path
- `subprocess` becomes the first-class jobs backend for local operation in this spec

The critical product goal is full API parity between local and remote jobs operation.

This keeps the platform close to what it already has today while removing the current "jobs" versus "no jobs" split.

The guiding UX principle for this work is the principle of least surprise.

The platform should become more consistent and more powerful without becoming more complicated for the common case.

At the top level, the user should still experience only two deployment modes:

- local
- remote

Everything else should support those two modes without forcing extra complexity into the default workflow.

This spec is broad because local/remote jobs parity is not a single backend change.

To make local jobs behave like remote jobs, the platform must define all of the following together:

- how jobs are addressed
- how the local control plane is discovered and reused
- how local and remote targets are selected
- how subprocess inherits code, interpreter, and virtual environment identity
- how task and job storage are represented
- how working directory is defined
- how logs are accessed
- how supporting services are activated
- how lifecycle operations such as pause, resume, and retention behave

If these pieces are not specified together, the platform will still have hidden local-only behavior even if subprocess becomes a first-class backend.

So the purpose of this spec is not only to say "use subprocess through jobs."

It is to define the minimum surrounding control-plane, runtime, and UX contract needed for that statement to actually produce full local/remote jobs parity.

There is also an important historical reason for the existing split between `run` and `submit`.

Previously, the platform often treated:

- `run` as the lightweight local path
- `submit` as the jobs-backed path

because starting the full platform control plane was seen as expensive and unnecessary for simple local work.

That concern is valid and remains one of the biggest risks for this project.

If adopting the unified jobs model makes simple local execution feel heavier, slower, or more operationally confusing than the old `run` experience, then the architecture will have failed a key product requirement even if it is internally cleaner.

The two primary product risks are:

1. Progressive platform startup fails to feel lightweight.

   If progressive activation exists architecturally but still feels heavy or slow to the user, then the design has not solved the original problem.

2. The getting-started story becomes more complicated.

   If users have to learn more control-plane concepts, startup choices, or routing mechanics than they do today for the common local and remote workflows, then the design violates the principle of least surprise.

So the spec should be evaluated against a simple bar:

- it must support the needed power and flexibility
- it must not make the common local and remote workflows more complicated than they are today

## Why This Spec Covers Multiple Areas

The changes in this document are coupled for structural reasons.

### Jobs API Parity Requires Control-Plane Parity

If the jobs API is unified but local daemon discovery, target selection, and reuse are left implicit, local mode still behaves differently in practice.

That is why this spec covers:

- local daemon discovery
- foreground/background lifecycle
- target selection
- fail-fast reuse checks

### Backend Parity Requires Runtime Contract Parity

If subprocess becomes a first-class backend but continues to expose different working-directory, storage, logging, or interpreter behavior than remote backends, users still experience a split system.

That is why this spec covers:

- logical task/job/config storage
- working-directory semantics
- code-root and interpreter identity
- logging access through APIs
- backend-owned retention policy

### Lightweight Local Mode Requires Service-Activation Semantics

If local mode is supposed to be lightweight and on-demand, the platform must define how required services are discovered, activated, and observed.

That is why this spec covers:

- daemon control interfaces
- readiness and availability reporting
- progressive service activation
- service-level logs and failure reporting

### Simple UX Requires Explicit Target And Mode Rules

If the user experience is supposed to remain simple, the spec must say what the defaults are and when users need to think about targets, daemon keys, or endpoints.

That is why this spec covers:

- local as the default target
- remote as an explicit named target
- cluster as the main target abstraction
- background versus foreground as lifecycle modes of the same local daemon
- advanced overrides as secondary escape hatches

In short, the document is intentionally larger than a backend-only spec because the architectural problem is larger than a backend-only change.

## Primary UX Risk

The main product risk for this work is unnecessary friction in the local-first workflow.

Historically, local execution avoided jobs because:

- users wanted the fastest path to "just run this now"
- many local jobs did not need the full platform runtime
- startup overhead made jobs feel heavyweight for simple development tasks

This spec must therefore preserve the benefits users expected from the old lightweight local path while still moving everything onto the jobs contract.

The design should be judged against a simple standard:

- a user should be able to run a local job synchronously without needing to understand daemon lifecycle, target routing, or service activation details
- if nothing suitable is running, the CLI should be able to start what it needs automatically and transparently
- the default local experience should feel local-first, lightweight, and obvious
- remote operation should also remain straightforward and explicit

The main failure modes to avoid are:

- forcing users to learn too much control-plane vocabulary for common local workflows
- making users manually reason about whether jobs services are running
- making local startup feel slow or operationally heavy for simple use cases
- exposing too many knobs in the default path
- preserving hidden differences between local and remote while also increasing perceived complexity

This is why the spec emphasizes:

- local as the default target
- transparent daemon acquisition
- progressive service activation
- one jobs API contract
- one target-selection model
- advanced options only when users explicitly need them

The intended default user experience is:

- `nemo jobs run ...` should just work locally
- if needed, the platform starts the local daemon in the background automatically
- the user does not need to decide up front between "jobs" and "no jobs"
- switching to remote should also be simple and explicit when desired

## Acceptance Criteria

- `nemo jobs run ...` should work in the default local-first workflow without requiring the user to pre-start services manually.
- If a suitable local daemon is not already running, the CLI should be able to start it automatically and transparently.
- Local and remote jobs execution should expose the same jobs API contract to clients.
- Subprocess should be a first-class jobs backend rather than a separate local execution path.
- The default local workflow should not require the user to understand daemon keys, service activation, or transport details.
- Remote targeting should remain explicit and straightforward.
- CLI commands that do not require any services should incur no service-startup overhead.
- Jobs unification should not impose daemon acquisition or service startup on CLI flows that can run entirely client-side.

### Parity Checklist

The spec should be considered a failure if local and remote still diverge in any major user-visible way across these areas.

- same jobs API contract
- same top-level target-selection model
- same profile-discovery model
- same logical task/job/config storage contract
- same working-directory contract
- same log-access contract
- same lifecycle-state contract
- explicit and stable local runtime identity
- explicit service-activation and dependency-failure model
- daemon-to-daemon storage and state isolation
- foreground and background local modes differ only by lifecycle attachment, not by jobs semantics

## Current State

Today the repo has two different execution models for jobs.

### Plugin CLI / Scheduler Split

At the plugin layer, `NemoJobScheduler` still exposes two materially different paths:

- `run_local(...)` executes a job in-process
- `submit_remote(...)` POSTs to the jobs API

This means `run` is not just synchronous interaction. It is a different execution architecture.

### Core Jobs Already Has A Subprocess Backend

The core jobs service already supports `provider: subprocess` as a real backend.

That backend schedules a persisted job step, launches a host process, captures logs, manages lifecycle, and reconciles status through the jobs service.

This is already much closer to the desired model than `run_local(...)`.

### Current Subprocess Rewrite

The jobs API currently contains a compatibility rewrite that converts some CPU container steps into subprocess steps when the selected profile is configured as a subprocess profile.

That rewrite:

- happens at jobs API ingress
- rewrites a `CPUExecutionProvider` step into `SubprocessExecutionProvider`
- derives the subprocess command from `container.entrypoint + container.command`
- drops container semantics in the process

This works as a bridge, but it is not an honest execution contract.

## Problem

The current split creates avoidable complexity and weakens local/remote parity.

### Problem 1: `run` And `submit` Mix Interaction Mode With Execution Placement

Users currently have to learn:

- `run` means local and in-process
- `submit` means remote and jobs-backed

That is the wrong abstraction boundary. Whether a user wants synchronous output or an async handle should be independent from where the job runs.

### Problem 2: Local Execution Bypasses Jobs Semantics

When `run_local(...)` is used, the platform bypasses the jobs scheduler, reconciliation, persistence, logs, and status lifecycle that the same workload encounters through the jobs service.

This means local execution does not exercise the same platform semantics as jobs-backed execution.

### Problem 3: Subprocess Exists Twice

The platform currently has:

- subprocess-like local execution via `run_local(...)`
- a real subprocess backend inside core jobs

Those are overlapping concepts with different semantics and different code paths.

### Problem 4: Current Rewrite Is A Compatibility Hack

Rewriting a container-shaped CPU step into a subprocess step based on profile name is useful for migration, but it hides a real contract change:

- container execution means "run this image with container semantics"
- subprocess execution means "run this host command in the local environment"

Those are not equivalent.

### Problem 5: Lightweight Local Development Still Needs Persistence And Discovery

The desired local experience is lightweight, but it still needs:

- persistence
- daemon discovery
- duplicate-service avoidance
- explicit start/stop behavior
- log visibility
- clear reuse of an already-running local endpoint

Direct multi-process SQLite access from arbitrary client processes is not a sufficient control-plane model.

## Goals

- Preserve `run` and `submit` as user-facing verbs.
- Redefine `run` as synchronous jobs interaction, not in-process execution.
- Make all execution flow through the jobs service contract.
- Preserve full API parity between local and remote jobs operation.
- Make `subprocess` a first-class jobs backend rather than a side path.
- Allow the local daemon to host `subprocess` in this spec.
- Preserve profile-driven execution selection in the near term.
- Make local daemon reuse and bootstrap transparent and predictable.
- Ensure CLI commands that do not require services incur no service-startup overhead.

## Terminology

This spec uses the following terms consistently:

- `cluster target`: a named jobs-routing target selected by the CLI
- `local target`: a cluster target whose control plane is a local daemon
- `remote target`: a cluster target whose control plane is a remote jobs API
- `daemon key`: the identity of a specific local daemon target
- `state directory`: the daemon-private state location associated with a daemon key
- `daemon-private root`: the daemon-scoped runtime/storage root under that state directory

## Non-Goals

- Unifying jobs with agent deployments or model deployments.
- Replacing profile resolution in this iteration.
- Writing a migration plan in this spec.
- Defining `daemon-group` behavior in this spec.
- Defining Orchard-specific implementation details as required architecture.
- Requiring direct client access to SQLite.

## End-State Model

### Core Principle

There is one jobs contract.

The CLI always talks to a jobs API. There are only two control-plane targets:

- local daemon
- remote cluster

Those are two ways to host the same jobs contract. They are not different job models.

The local and remote paths should behave as close to identically as possible.

The default target should be as simple as possible:

- local daemon is the default target
- no target selection should be required for the default local workflow
- remote targeting should be explicit

There should be a built-in default cluster target named `local`.

That target should always be present and should not require the user to create or register it.

The built-in `local` target should resolve to the default local daemon key for the current local development context.

In this spec, `cluster` should be understood as the primary named target abstraction for jobs routing.

It should not be treated as merely a convenient alias for a raw URL.

A cluster target should represent the saved routing and identity information needed to talk to a jobs control plane.

The only local-only interface should be the daemon control surface used for discovery and coordination.

The jobs API itself should remain the same between local and remote modes.

### Interaction Modes

The user-facing verbs keep their names but change meaning:

- `submit` means create a job and return a handle
- `run` means create a job and follow it until terminal state

`run` is therefore "submit + follow", not "execute locally in-process".

### Backend Model

Backend choice is part of jobs execution, not part of the CLI verb.

The local-first backends in scope for this spec are:

- `subprocess`

This backend should be scheduled, reconciled, logged, and cancelled through the same jobs lifecycle.

### Profile Resolution

Near-term backend selection continues to use the existing profile model.

That means:

- compilers keep producing profile-driven job specs
- configured execution profiles determine what backend contract is actually available
- local and remote hosting differ mainly in which profiles are present and valid

This keeps the architecture close to the current platform while removing the `run_local(...)` side path.

Profiles should be treated as properties of the selected control plane.

That means:

- remote cluster mode uses the profiles exposed by the remote jobs API
- local daemon mode uses the profiles exposed by the local daemon over its local API

In local daemon mode, the CLI should not read execution profile definitions directly from local config files as its source of truth. It should query the local daemon for the profile set that is actually active for that daemon instance.

### Working Directory And Storage Parity

Full local/remote parity also requires a consistent task/job storage contract.

Docker and Kubernetes already expose a mostly logical storage contract:

- task-scoped ephemeral storage via `NEMO_JOB_EPHEMERAL_TASK_STORAGE_PATH`
- job-scoped persistent storage via `NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH`
- task-scoped config storage via `NEMO_JOB_STEP_CONFIG_STORAGE_PATH`

Those map to stable in-task paths such as:

- `/var/run/scratch/task`
- `/var/run/scratch/job`
- `/var/run/scratch/config`

for containerized backends, while the actual implementation may be Docker volumes, Kubernetes `emptyDir`, PVC subpaths, or other backend-owned storage mechanisms.

Subprocess currently differs in two important ways:

- it sets `cwd` directly to a host-side task working directory
- it exposes backend-owned host paths as the actual runtime locations for task, config, and job storage

That is acceptable as an implementation detail, but it should not remain the client-visible or compiler-visible contract.

The target contract for this spec is:

- jobs should continue to consume the logical task/job/config storage env vars as the primary storage contract
- subprocess should follow the same logical storage conventions already used by Docker and Kubernetes
- backend-specific filesystem layout should remain an internal implementation detail
- the jobs API should expose enough metadata to identify task-level and job-level storage locations logically, without requiring clients to know backend-private host paths
- different local daemons must have fully isolated backend-private storage roots

For subprocess specifically:

- the backend may still materialize task and job storage on the host filesystem
- the backend may still choose an internal host-side working directory layout for process execution
- but the stable contract seen by job code should be the same logical task/job/config storage environment already used by Docker and Kubernetes
- and that host-side storage must be namespaced by daemon identity so multiple local daemons cannot conflict

The current subprocess host layout is a reasonable internal implementation:

- `<root>/<workspace>/<job>/<attempt>/<step>/<task>` for task work
- `<root>/<workspace>/<job>/<attempt>/job-storage` for job-persistent storage

but that layout should be treated as daemon-owned state, not as the public job contract.

The spec should therefore distinguish clearly between:

- logical task storage
- logical job-persistent storage
- backend-private host implementation paths
- daemon-private host implementation roots

### Daemon Storage Isolation

Multiple local daemons must be fully isolated from one another.

That isolation must cover at least:

- task working directories
- task scratch directories
- task config directories
- job-persistent storage
- backend-private logs
- daemon-private state

This means one local daemon must not be able to accidentally read, reuse, or delete another daemon's task or job runtime state simply because the workspace, job name, or attempt id happen to match.

For subprocess, the backend-private host layout should therefore be scoped under a daemon-private root before any workspace/job/attempt/task nesting is applied.

Conceptually:

- `<daemon-root>/<workspace>/<job>/<attempt>/<step>/<task>` for task work
- `<daemon-root>/<workspace>/<job>/<attempt>/job-storage` for job-persistent storage

where `<daemon-root>` is unique to the local daemon target rather than globally shared across all local daemons.

The daemon root should be derived from the daemon key and the daemon's own state directory, not only from the workspace or job identifiers.

The spec should make this explicit:

- every local daemon key has its own daemon-private state directory
- every local daemon key has its own daemon-private storage root
- daemon-private task, scratch, config, log, and job-storage paths must all live under that daemon-private root

So if the daemon key is `local`, one daemon-private root might conceptually look like:

- `<state-root>/daemons/local/runtime/...`

and if the daemon key is `exp-b`, a separate daemon-private root might conceptually look like:

- `<state-root>/daemons/exp-b/runtime/...`

The exact directory naming may vary, but the required property is:

- the daemon key must be part of the daemon-private root layout

This is what guarantees that two daemons using the same checkout or virtual environment still do not collide with each other.

This is required for:

- side-by-side local daemons for testing
- foreground and background instances of different daemon keys
- version-isolated local development
- fail-fast discovery and safe cleanup

Cleanup and retention must also respect daemon isolation.

That means:

- one daemon must only clean up its own backend-private storage
- retention logic must never assume a single global subprocess storage root shared by all local daemons

### Current Working Directory Gap

#### Current Behavior

Today, backends do not all handle the task working directory the same way.

- `subprocess` explicitly launches the process with `cwd` set to a backend-owned task work directory
- Docker and Kubernetes standardize task/job/config storage mounts and env vars
- Docker and Kubernetes do not currently standardize the task working directory
- the jobs launcher does not currently set `cwd`
- so in Docker and Kubernetes, the working directory is whatever the container runtime or image default happens to be

#### Problem

This means local and remote do not have the same working-directory contract.

Today:

- local subprocess jobs start in an explicit task directory
- Docker and Kubernetes jobs do not necessarily start in that same logical task directory

That is a parity gap.

Job code should not have to guess whether:

- the current working directory is the task directory
- the current working directory is the image default
- it should use the task storage env vars instead of `cwd`

#### Change In This Spec

This spec should define one explicit jobs working-directory contract for all backends.

The contract is:

- every task has a logical task working directory
- by default, that working directory is the task-ephemeral storage root
- job specs may override working directory at job scope
- job steps may override working directory at step scope

The spec should add explicit working-directory fields to the jobs schema:

- `PlatformJobSpec.working_directory`
- `PlatformJobStepSpec.working_directory`

These fields represent the logical working directory seen by job code, not a backend-private host path.

These values should be absolute runtime paths.

Relative working-directory values should be rejected.

For the backends in scope here, those values should be runtime paths consistent with the existing Docker/Kubernetes storage conventions, for example:

- `/var/run/scratch/task`
- `/var/run/scratch/job`
- subdirectories under those roots

Backends may reject values they cannot safely materialize.

The precedence should be:

- task-level working directory override
- job-level working directory override
- backend default

The backend default should be the logical task storage root.

That means:

- subprocess should default `cwd` to the task-ephemeral storage root
- Docker and Kubernetes should also default the container working directory to the task-ephemeral storage root

So the intended end state is simple:

- if no override is set, every task starts in its logical task directory
- if a job-level override is set, tasks use that unless a step overrides it
- if a step-level override is set, that step uses its own value

Backend-specific storage layout remains private.

For subprocess:

- the backend maps the logical working directory onto its daemon-private host layout
- the process is launched with `cwd` set to that resolved logical directory

For Docker and Kubernetes:

- the backend sets the container working directory to the resolved logical path
- task/config/job storage mounts continue to work as they do today

#### Potential Impact And Risk

This part of the spec changes behavior for Docker and Kubernetes, because today they do not consistently force the task working directory.

There is one real compatibility risk here:

- some existing workloads may implicitly rely on the current container-image `WORKDIR`

Examples of concrete breakage would be:

- code that reads or writes relative paths assuming the image's existing `WORKDIR`
- wrapper scripts that expect to start from a repository root or image-specific home directory
- commands that rely on relative paths without using the provided task/job storage paths

If a workload already uses the task/job/config storage paths explicitly, the practical impact should be low.

So this should be treated as a genuine but narrow compatibility risk:

- narrow, because it only affects workloads that rely on implicit image-default `WORKDIR`
- genuine, because this spec intentionally replaces that accidental behavior with an explicit jobs contract

### Retention Parity

#### Current Behavior

Today, jobs backends already share some controller-level retention settings such as:

- `cleanup_completed_jobs_immediately`
- `ttl_seconds_after_finished`

but each backend applies retention differently.

Today:

- subprocess removes backend-owned task working directories according to subprocess cleanup policy
- Docker removes containers and task volumes, and may separately clean job-persistent storage
- Kubernetes relies on Kubernetes job TTL plus explicit cleanup behavior

So there is already no single identical retention mechanism across backends.

#### Change In This Spec

This spec should preserve that general architecture.

Retention should remain backend-owned policy rather than becoming a special local-only concern.

That means the retention model should distinguish at least:

- task-ephemeral storage retention
- job-persistent storage retention
- job metadata retention in the jobs API
- log retention

The intended parity is not identical deletion behavior across backends.

The intended parity is:

- retention is a normal backend concern
- retention is configured and enforced through the backend/profile model
- local subprocess follows that same architectural convention instead of behaving like a special non-jobs path

For this spec:

- subprocess should have its own backend retention policy, just like Docker and Kubernetes do
- task-ephemeral storage may be cleaned up according to subprocess backend/profile retention policy
- job-persistent storage retention should be defined by the subprocess backend/profile, not by accidental host-directory lifetime
- jobs API records and status lifecycle should still be exposed uniformly even if backend cleanup behavior differs
- log access should remain API-based even if underlying local task directories are removed

So the change here is mostly architectural clarity:

- subprocess cleanup policy becomes an explicit backend concern
- local jobs retention is brought under the same conceptual model as Docker and Kubernetes

#### Potential Impact And Risk

There is no significant known compatibility risk here.

This part of the spec is mostly clarifying architecture:

- subprocess retention is treated as an explicit backend policy
- local subprocess is brought under the same conceptual model as Docker and Kubernetes

Because local subprocess retention is not understood to be something existing deployed environments materially depend on, this should not be treated as a major product risk.

## Local Control Plane

### Principle

Local execution is not special because it is local.

It is special only in how the jobs control plane is hosted.

### Local Daemon

The local option should be a real daemon-backed jobs endpoint with:

- persistent local state
- a well-defined daemon control socket
- a discoverable TCP/IP jobs API listener
- daemon discovery
- reuse of an already-running usable daemon
- clear visibility into status and logs

If the local endpoint is already running, the CLI should connect to it instead of starting a duplicate service.

If it is not running, the CLI may bootstrap it and then submit through the same jobs API contract.

The local daemon should not assume a fixed all-or-nothing service bundle. It should be able to activate additional local services and plugins on demand as requirements become known.

The jobs API exposed by the local daemon should use TCP/IP, not UDS, so local and remote request paths remain as similar as possible.

### Foreground And Background Local Modes

The local daemon should support two operational modes:

- foreground mode
- background mode

These should not be treated as different architectures.

They are two lifecycle modes for the same local control plane and should be functionally equivalent.

In this framing:

- `nemo services run` is the foreground mode
- daemon mode is the background mode

Both should expose the same jobs API behavior, the same daemon identity model, and the same progressive activation behavior.

The difference is only lifecycle ownership and terminal attachment:

- foreground mode stays attached to the invoking terminal
- background mode detaches and continues running after the invoking command exits

The spec should make it explicit that either mode may be used for the same local target.

That means:

- a user should be able to start the local daemon explicitly in foreground mode
- a user should be able to start the same local daemon explicitly in background mode
- the CLI may also start the local daemon implicitly through progressive activation when no suitable daemon is already running

Those should all converge on the same effective runtime shape.

One reasonable command model is:

- `nemo services run` for foreground local mode
- `nemo services run --daemon` for background local mode

or an equivalent spelling under the existing services command family.

The important requirement is not the exact flag name. The important requirement is:

- there is one command family for starting local services
- foreground and background are explicit lifecycle modes of that same command family
- progressive activation and explicit startup are functionally equivalent ways to obtain the same local daemon target

This avoids creating a second conceptual split such as:

- explicit `services run`
- separate unrelated `daemon start`

The platform should instead present a single local control-plane model with multiple lifecycle entry paths.

The preferred CLI spelling for background mode in this spec is:

- `--daemon`
- `-d`

The same local daemon key selection mechanism should be available in both foreground and background mode.

That is required because local daemon discovery must be able to identify a specific local target regardless of whether that target is attached to a terminal.

Example:

- `nemo services run --instance exp-b`
- `nemo services run --daemon --instance exp-b`
- `nemo services run --daemon --instance exp-b --state-dir /tmp/nmp-exp-b`

Both commands refer to the same logical local daemon target `exp-b`.

The difference is only whether the process remains in the foreground or detaches into background operation.

### Local Daemon Code Root And Interpreter Contract

The local daemon must also have a well-defined relationship to the source tree and Python environment it is running from.

This matters especially for subprocess because local execution should be unambiguous about:

- which checkout of the code is being used
- which Python interpreter is being used
- which virtual environment is being used
- whether an existing daemon can be safely reused for the caller's intended local development context

Current subprocess behavior already points in this direction:

- subprocess inherits a narrow allowlist from the daemon process environment, including `PATH` and `VIRTUAL_ENV`
- if a subprocess command begins with `python` or `python3`, the backend rewrites it to use the daemon's interpreter resolution
- if `VIRTUAL_ENV` is set and contains an executable `bin/python`, that interpreter is used
- otherwise, the backend falls back to the daemon process `sys.executable`

This means local subprocess execution already effectively runs in the daemon's Python environment rather than in a separate task-specific environment.

That behavior should be made explicit and contractual.

For local daemon mode, each daemon instance should therefore have explicit identity fields for:

- daemon key
- code root
- Python executable
- virtual environment path, if any
- daemon version
- jobs API version

The daemon key should be the selector used to distinguish multiple local daemons for testing or versioned development.

The code root should identify which checkout the daemon is associated with for local development purposes.

The Python executable and virtual environment should identify exactly which runtime environment local subprocess jobs will inherit when they use `python` or `python3`.

The daemon control interface should expose these values directly.

### Non-Default Daemon Key Example

The default local workflow should not require users to think about daemon keys.

By default:

- the CLI targets the default local daemon for the current local development context
- if no such daemon exists, the CLI starts one

The built-in cluster target for that workflow should be `local`.

Non-default daemon keys are mainly for testing, side-by-side development, or explicit version isolation.

Users should not need to pass a daemon key on every jobs command.

The local daemon selection model should mirror cluster selection as closely as possible:

- there should be a current selected local daemon target
- jobs commands in local mode should use that selected daemon by default
- a per-command daemon-key override may still exist for testing or debugging, but it should not be the primary workflow

A concrete example:

1. A developer is working on the current checkout and uses the default local daemon:
  `nemo jobs run ...`
2. The same developer wants to compare behavior against a second local daemon started from a different checkout or virtual environment.
3. They start or target that daemon with a non-default key such as `exp-b`:
  `nemo services run --instance exp-b ...`
4. They then select that daemon through the same target-selection model used for remote clusters:
  `nemo cluster use exp-b`
5. Subsequent local jobs commands use that selected daemon automatically:
  `nemo jobs run ...`
6. The CLI performs daemon discovery against `exp-b`, checks the daemon metadata, and either:
  - connects if the daemon key, version, code root, interpreter, and capability requirements match
  - fails explicitly if they do not match
  - or starts a new local daemon for `exp-b` if none is running and startup is allowed

In this example, the user can keep two local daemons distinct:

- default daemon for the main checkout
- `exp-b` daemon for an alternate checkout or alternate virtual environment

This makes the behavior explicit and testable:

- daemon selection is intentional
- daemon identity is inspectable
- reuse is fail-fast rather than best-effort

The spec does not require a per-command `--daemon-key` to be a broadly advertised end-user workflow.

It is acceptable for per-command daemon-key override to exist primarily as an advanced local-development and test capability, as long as the behavior is explicit and stable.

### Local Daemon Selection

The platform should support explicit selection of the current local daemon target through the existing cluster-selection model.

That means:

- local daemon targets should be named by daemon key
- the CLI should persist the currently selected target
- local jobs commands should use the selected local daemon target by default when operating in local mode
- users should be able to switch between local daemons without repeating the daemon key on every command
- the built-in `local` target should always exist and should map to the default local daemon key

A conceptual workflow is:

- `nemo cluster ls`
- `nemo cluster use exp-b`
- `nemo jobs run ...`

The current repo does not yet have a complete generic cluster-selection command surface for this exact purpose, so the examples below should be read as proposed CLI behavior for this spec.

This keeps the local and remote selection stories aligned:

- remote mode selects a remote cluster target
- local mode selects a local daemon target
- both should use the same top-level target-selection workflow

The selection rules should be:

- if `--cluster` or `--base-url` is provided, use that explicit target
- otherwise, default to the local daemon target for the current local development context

The daemon control interface should expose enough metadata for the CLI to render and select available local daemons clearly.

The spec should not introduce a new top-level `daemon` command family for this purpose.

Instead, the existing cluster/target selection system should be extended so that it can represent both:

- remote cluster targets
- local daemon targets

This preserves a single selection model and avoids creating a parallel command surface.

### Local Daemon Discovery

The spec should make local daemon discovery explicit.

Discovery should not be based on guesswork such as:

- probing arbitrary ports
- looking only for a PID
- assuming one global singleton daemon

Instead, discovery should be keyed by the local daemon target identity.

At minimum, discovery should use:

- daemon key
- instance descriptor/state directory entry
- explicit daemon control socket location

The daemon control socket should be the authoritative discovery rendezvous point for a local daemon target.

The local services CLI should also be able to accept an explicit daemon state directory.

That is useful for:

- testing
- isolated local sandboxes
- side-by-side daemon instances with different roots

However, this must be validated strictly.

The platform should reject configurations where two distinct daemon identities would share the same effective state directory.

At minimum:

- the daemon key must map to one daemon-private state directory
- the daemon-private root must include the daemon key
- starting a daemon with a state directory that would collide with another daemon's effective root should fail explicitly
- the CLI should not silently alias two daemon keys onto one shared state directory

One reasonable model is:

- each daemon key maps to a deterministic instance state directory
- that directory contains the daemon descriptor
- that directory also contains the well-known daemon control socket for that key
- the CLI uses that descriptor and socket to determine whether the daemon exists, is alive, and is usable

This is close to the current `nemo services` instance model and should remain the basis for local discovery.

The discovery flow should be:

1. Determine the target daemon key.
  This may come from:
  - the selected local cluster target
  - an explicit command-line override
  - the default local development-context target
2. Resolve the instance state directory for that daemon key.
3. Read the daemon descriptor if present.
4. Check daemon liveness through the authoritative discovery mechanism for that key.
  A lock or equivalent liveness primitive should remain the source of truth, not the descriptor alone.
5. If alive, connect to the daemon control socket for that key.
6. Query status and metadata from the daemon control interface.
7. Verify safe reuse checks such as:
  - daemon key
  - code root
  - Python executable
  - virtual environment
  - daemon version
  - jobs API version
  - required capabilities
8. If the daemon is not present, not alive, or not reusable:
  - fail explicitly
  - or start a new daemon for that same key if the current workflow allows startup

This should be clear in both foreground and background mode.

That means the daemon key is not only a background concern.

It is part of the fundamental local identity and discovery contract for:

- foreground `nemo services run --instance <key>`
- background `nemo services run --daemon --instance <key>`
- implicit CLI-driven local daemon acquisition for jobs commands

### Per-Command Override

The selected target should remain the default, not an exclusive routing mechanism.

Per-command override should continue to be supported.

That means:

- the user may override the currently selected target for a single jobs command
- `--cluster` remains a valid per-command override for remote routing
- `--base-url` remains a valid per-command override when the user wants to target a specific endpoint directly

This keeps the current operational flexibility while still allowing the CLI to maintain a stable default target.

However, `--base-url` should be treated as an advanced escape hatch rather than the primary user workflow.

The normal workflow should be:

- create or discover a named target
- select that target
- run jobs against the selected target

This keeps users thinking in terms of stable named control-plane targets rather than transport details.

### Concrete Target Examples

The spec should make local and remote targets look structurally similar.

One reasonable target model is:

- remote cluster targets have a name, kind, and endpoint metadata
- local daemon targets have a name, kind, and local discovery metadata

Example remote target:

- name: `dev-usw2`
- kind: `remote`
- base URL: `https://dev-usw2.example.nvidia.com`
- optional additional target metadata for auth or routing as needed

Example local daemon target:

- name: `exp-b`
- kind: `local-daemon`
- daemon key: `exp-b`
- discovered jobs API endpoint: `http://127.0.0.1:43123`
- optional additional target metadata for compatibility checks as needed

Example workflows:

1. Default local workflow
  `nemo jobs run ...`
   Result:
  - the CLI uses the default local daemon target
  - if needed, it discovers or starts the default local daemon
  - jobs then run against the local jobs API
2. Create a named remote target
  Proposed CLI shape:
   `nemo cluster add dev-usw2 --base-url https://dev-usw2.example.nvidia.com`
   Result:
  - a named remote target `dev-usw2` is created
  - it can later be selected or used as a per-command override
3. Switch to a remote target
  Proposed CLI shape:
   `nemo cluster use dev-usw2`
   Result:
  - jobs commands go to `https://dev-usw2.example.nvidia.com`
4. Switch back to the default local target
  Proposed CLI shape:
   `nemo cluster use local`
   Then:
   `nemo jobs run ...`
   Result:
  - jobs commands resolve `local` as the default local-daemon target
  - the CLI uses the daemon control interface to discover the daemon
  - the CLI discovers the local jobs API endpoint, for example `http://127.0.0.1:43123`
  - jobs commands then talk to that TCP/IP jobs API endpoint
5. Create and use a non-default local target for testing
  Proposed CLI shape:
   `nemo cluster add exp-b --local-daemon-key exp-b`
   Then:
   `nemo cluster use exp-b`
   Then:
   `nemo jobs run ...`
   Result:
  - the CLI resolves `exp-b` as a named local-daemon target
  - it discovers or starts the `exp-b` daemon instance
  - jobs run against that daemon's TCP/IP jobs API
6. Override the selected target for a single command
  `nemo jobs run --cluster dev-usw2 ...`
   Result:
  - this command goes to remote cluster `dev-usw2`
  - the current selected target remains unchanged
7. Override with an explicit endpoint
  `nemo jobs run --base-url http://127.0.0.1:43123 ...`
   Result:
  - this command talks directly to that endpoint
  - the current selected target remains unchanged

The important behavior is not the exact command spelling. The important behavior is:

- local is the simple default
- `local` is a built-in target that is always available
- remote is explicit
- both local and remote targets can be named and selected
- local targets resolve indirectly through daemon discovery
- remote targets resolve directly through configured base URLs
- per-command override remains available without mutating the selected default target

The key UX point is:

- `cluster` is the primary abstraction
- URL is just one field inside some cluster targets
- users should usually select a named target rather than supplying raw endpoints

### Fail-Fast Reuse Policy

Local daemon reuse should be fail-fast.

There should be no silent fallback from one local development context to another.

That means:

- if the CLI is targeting a specific daemon key, it should connect only to that daemon key
- if the CLI expects a particular code root, Python executable, virtual environment, version, or capability set, and the daemon does not match, the operation should fail explicitly
- the CLI may then choose to start another daemon, but it should not silently reuse the wrong one

This should be treated as part of safe reuse checks, not as best-effort convenience behavior.

In particular, local daemon mode should not silently:

- connect to a daemon associated with a different checkout
- connect to a daemon associated with a different virtual environment
- connect to a daemon associated with a different Python executable
- downgrade to a different local runtime than the caller requested

### Current Development Behavior

Today, changes made in the source tree are picked up by newly launched local subprocess jobs only to the extent that the daemon's Python environment resolves them at runtime.

In practice that means:

- subprocess jobs launched with `python -m ...` or `python3 -m ...` use the daemon's interpreter selection
- imports come from whatever that interpreter and environment resolve at execution time
- if the local development environment uses an editable install, new subprocess jobs will generally observe source-tree changes immediately
- if the local development environment uses a non-editable installed package, they may instead continue to use installed code

This is another reason the daemon must expose code-root and interpreter identity explicitly rather than leaving behavior implicit.

The spec should not rely on accidental editable-install behavior as the architectural contract.

### Why A Daemon Is Required For Local Mode

The local mode still needs cross-process coordination, persistence, and discovery.

That rules out a design where each CLI invocation directly opens and manages SQLite state on its own. For local mode, a daemon-backed control plane is the correct primitive.

### Remote Cluster

The remote option means an externally hosted NeMo jobs API, such as a configured cluster endpoint.

In remote mode:

- the environment is assumed to be provisioned already
- required services are checked, not progressively bootstrapped by the CLI
- dependency unavailability should surface as a normal error

### Local Daemon Interface

Local mode should expose a local-only daemon interface for reporting status, requirements, readiness, and errors.

This interface is not responsible for starting or stopping the local daemon itself.

Daemon lifecycle remains CLI-owned code:

- find an existing local daemon
- decide whether one must be started
- start it if needed
- stop it if the CLI owns that lifecycle

The local daemon interface is responsible only for answering questions such as:

- which local daemon instance is being addressed
- which TCP/IP port its jobs API is listening on
- what services and backends are currently running
- what services are required for a given request
- whether the required services are ready
- whether the request cannot be satisfied and why
- what daemon and service version is currently running
- how to stream logs relevant to startup, convergence, and failures

The interface should be:

- asynchronous
- readiness-aware
- cross-process safe
- able to support polling or long-poll readiness waits
- able to support log streaming for connected local clients

Availability should be an explicit part of the contract. In particular, local mode needs a clear and reliable way to determine whether a daemon or service is:

- not running
- starting but not yet ready
- running and reusable
- running but unhealthy
- running but not usable for this request

The daemon interface should not guess based only on process existence. It should expose an explicit availability check that can answer whether the target runtime is present, healthy, and usable for the request.

The interface should expose explicit state such as:

- started or not started
- ready or not ready
- healthy or unhealthy
- failed, with error details

That state is required so "ensure service" style logic can actually determine whether to wait, proceed, or fail.

### Local Daemon API

The local daemon interface should be specified as a small local-only control API separate from the normal jobs API.

The recommended transport is HTTP/REST over a Unix domain socket.

This keeps the daemon control interface local-only while allowing the actual jobs API to remain TCP/IP-based.

Using HTTP over UDS is a good fit because it:

- reuses the existing REST and FastAPI-style platform patterns
- keeps daemon discovery and coordination local-only
- avoids forcing the main jobs API onto a different transport than remote mode
- preserves room for streaming, long-poll, and structured status responses

The contract should expose four concrete capabilities:

- daemon status
- requirement planning
- wait for readiness
- log streaming

#### 1. Status

The daemon should expose a status call that returns the current daemon view without mutating state.

The status response should include at minimum:

- daemon key
- daemon identity
- daemon version
- protocol or API version
- jobs API host and port
- started state
- readiness state
- health state
- state-root or storage identity
- effective config identity or fingerprint
- supported services
- supported backends
- supported profiles
- per-service status
- active errors

Per-service status should distinguish at least:

- not started
- starting
- ready
- unhealthy
- failed

This status call is the basis for availability and safe-reuse checks.

#### 1a. Profiles

The local daemon should expose the effective execution profiles that belong to that daemon instance.

The daemon control interface may report profile metadata, but the actual profile query for jobs behavior should go through the local daemon's TCP/IP jobs API so that local and remote paths remain aligned.

The CLI should use the daemon-resolved profile set in local mode rather than reading profile configuration directly from local files.

#### 2. Requirement Planning

The daemon should expose a call that accepts request context and returns what local supporting services are required for that request.

The input should allow the daemon to consider:

- platform configuration
- job family or compiler-declared requirements
- backend or profile requirements
- current daemon state

The response should include:

- the required service set
- which required services are already ready
- which required services are still converging
- which required services failed
- whether the request is satisfiable in local mode
- why it is unsatisfiable when it fails

This makes the progressive activation contract explicit instead of implicit.

#### 3. Wait For Readiness

The daemon should expose a wait call for local mode that lets a client wait until the daemon is ready for a specific request.

This call should support polling or long-poll semantics.

The client should be able to provide:

- the request context or requirement key
- a timeout
- an optional cursor or last-seen status version for efficient waiting

The daemon should respond with one of these outcomes:

- ready: all required services are ready for the request
- pending: requirements are still converging
- failed: the request cannot become ready under current conditions
- timeout: readiness was not reached before the requested deadline

The response should also include current service state and active errors so the caller can decide whether to keep waiting or surface a failure.

#### 4. Log Streaming

The daemon should expose a log stream for local clients so startup and convergence remain visible.

The stream should be able to include:

- daemon bootstrap logs
- service activation logs
- readiness or failure transition messages
- logs for specific required services

The client should be able to scope the stream by:

- daemon-wide startup
- a specific request or requirement resolution flow
- one or more services

The log stream is diagnostic and observational. It should not be required for correctness, but it should be available so local startup and failure modes remain transparent.

### Progressive Service Activation

Progressive activation should be built on top of the local daemon interface rather than on fixed startup presets.

Required services may come from multiple sources:

- platform configuration requirements
- job or compiler-declared requirements
- profile or backend requirements

Examples:

- if auth is enabled in platform configuration, local auth-related services may also need to run
- a particular job family may require files, secrets, models, or a plugin-owned service
- a chosen backend or profile may require more local runtime support than another

The local control plane should therefore:

- start with the smallest useful local jobs runtime
- compute the union of currently required services from all known requirement sources
- activate missing services incrementally inside the daemon
- reuse already-running compatible services instead of restarting them

This implies that plugin-owned or service-owned local capabilities should be startable on demand based on usage and configuration, not only through fixed CLI startup flags.

The daemon interface should support a wait pattern where a caller can poll or long-poll until the required services become ready or until an error or timeout occurs.

### Responsibility Split

The CLI should be responsible only for daemon lifecycle and for ensuring access to a usable local jobs control plane.

That means the CLI should:

- find or start the local daemon using CLI-owned lifecycle code
- connect to the daemon through the local-only daemon interface
- submit or follow jobs through the normal jobs API

The local daemon should be responsible for resolving and activating supporting services needed to handle those requests.

That means the daemon should:

- inspect configuration and request context
- determine which supporting services are required
- activate supporting services internally as needed
- reuse running compatible services where possible

This keeps duplicate prevention and lazy activation inside explicit runtime contracts instead of scattering that logic across CLI startup paths.

### Auto-Start Failure UX

Transparent local daemon acquisition should have an explicit user-facing error contract.

If the CLI attempts to acquire a local daemon automatically and fails, the error should report at minimum:

- the local target name
- the daemon key
- the failure phase
- a short human-readable cause
- how to inspect relevant logs
- how to run explicitly in foreground mode
- how to run explicitly in `--daemon` mode

The failure phase should be one of:

- `discovery`
- `reuse`
- `startup`
- `readiness`

The CLI should use those phases consistently so users can tell whether:

- no daemon was found
- an existing daemon was found but could not be reused
- startup failed
- startup succeeded but readiness was not reached

Additional expected details:

- readiness failures should include timeout information when relevant
- reuse failures should include the mismatched property or requirement when relevant
- startup failures should include enough information to locate daemon-control logs quickly

The purpose of this contract is to keep transparent startup from feeling opaque when it fails.

### Availability And Safe Reuse

For local mode, the contract should define a clear method for determining whether a daemon or service is available.

That check should be strong enough to distinguish:

- process exists but runtime is not ready
- runtime is healthy and reusable
- runtime is unhealthy
- runtime is alive but attached to the wrong state, configuration, or capability set for the request

This is especially important for daemon reuse. "Available" should therefore mean more than "a process is running" or "a socket exists." It should mean the runtime has passed an explicit availability check and is safe for the CLI to treat as the active local control plane for the request.

At minimum, the availability and reuse contract should surface:

- daemon key
- daemon identity
- daemon version
- protocol or API version
- jobs API host and port
- health state
- readiness state
- state-root or storage identity
- effective config identity or fingerprint
- supported services, backends, and profiles
- per-service status
- active error details when unavailable

### Log Streaming

The local daemon interface should also support streaming logs to the connecting local client.

This is especially useful when:

- the CLI has started or attached to a local daemon
- the daemon is progressively activating required services
- a required service is slow to become ready
- activation fails and the user needs immediate diagnostic context

The local runtime does not have to rely on log streaming for its own internal correctness, but the interface should make log streaming available so local startup and convergence remain transparent to the user.

### Remote Behavior

The local-only daemon interface is specific to local mode.

It should not be treated as part of the remote jobs contract.

For remote, Kubernetes, or externally hosted platform endpoints:

- the environment is assumed to be provisioned already
- required services are checked, not progressively bootstrapped by the CLI
- dependency unavailability should surface as a normal error

For example, if a job requires `files` and the remote `files` service is unavailable, jobs should fail with a dependency error rather than attempting local-style activation behavior.

### API Parity Requirement

Full API parity between local and remote is a core requirement of this design.

That means:

- the same jobs REST API should be used in both local and remote modes
- local mode should not invent a separate jobs API shape
- differences between local and remote should be limited to control-plane discovery and environment capability, not the jobs API contract itself
- the daemon control API exists only to discover, identify, and coordinate the local daemon; it is not a replacement for the jobs API

In practice, this means a client that knows how to talk to the remote jobs API should also be able to talk to the local daemon's jobs API once the CLI has discovered its TCP/IP endpoint.

### Required Platform Changes

To support this design, NeMo Platform should make the following concrete changes.

#### 1. Add A Local-Only Daemon Control API

Add a local daemon API, separate from the normal jobs API, that exposes:

- status
- requirement planning
- wait for readiness
- log streaming

This API is local-only and exists for local daemon operation. It is not part of the remote platform jobs contract.

#### 2. Keep CLI-Owned Daemon Lifecycle Separate

Keep daemon lifecycle out of the daemon control API.

The CLI should own:

- daemon discovery
- daemon startup
- daemon shutdown when appropriate

The daemon control API should only answer:

- what is running
- what is required
- whether the request is ready
- why the request failed

#### 3. Support Request-Scoped Requirement Resolution

Add a request-scoped requirement resolution path inside the local daemon.

That resolver should combine requirements from:

- platform configuration
- service or plugin declarations
- job or compiler declarations
- backend or profile declarations

The result should be one resolved requirement set for the current request.

#### 4. Support Nested Dependency Activation From One Request

A single requirement request should be able to activate the full nested dependency graph needed for a service.

That means if a plugin-owned service is required, and that service depends on `entities`, `auth`, or another service, one daemon-side activation flow should be able to resolve and activate the entire dependency chain.

This should follow declared dependencies recursively rather than requiring the CLI or caller to activate each service manually.

#### 5. Extend Plugin And Service Declarations For Local Activation

Each core service and plugin-owned service should be able to declare the information needed for local activation.

At minimum this should include:

- service identity
- declared service dependencies
- whether the service is eligible for local activation
- any additional local activation requirements that differ from simple startup order

Existing `dependencies` declarations are a strong starting point and should remain part of this model.

#### 6. Add Job Or Compiler Requirement Declarations

Jobs or compilers should be able to declare which supporting services are required for local execution.

This is distinct from service startup dependencies.

Examples:

- a job may require `files` even if the jobs daemon itself does not
- a specific job family may require a plugin-owned service
- a specific backend or profile may require additional services

This declaration should feed into daemon-side requirement planning.

#### 7. Preserve Boolean Readiness In The Short Term

Short term, a boolean readiness signal from individual services is acceptable.

That means existing `Service.is_ready() -> bool` behavior can remain the base readiness primitive for now.

The local daemon should synthesize richer daemon-interface states such as:

- not started
- starting
- ready
- unhealthy
- failed

from:

- lifecycle state the daemon already knows
- boolean service readiness
- startup and activation errors

This avoids blocking the design on an immediate repo-wide readiness refactor while still giving the daemon interface the richer states it needs.

#### 8. Add Request-Aware Readiness Waiting

Add daemon-side wait-for-readiness behavior that is specific to the current request, not just platform-wide readiness.

The daemon should be able to answer:

- are all services required for this request ready yet
- which required service is still pending
- which required service failed
- whether the request can never become ready under current conditions

This wait path should support polling or long-poll behavior with timeout.

#### 9. Add Versioned Safe-Reuse Metadata

The daemon status contract should explicitly include version and reuse metadata so the CLI can safely decide whether an already-running daemon is reusable for the current request.

At minimum this should include:

- daemon key
- daemon version
- protocol or API version
- jobs API host and port
- state-root or storage identity
- effective config identity or fingerprint
- supported services, backends, and profiles

The CLI should also be able to send explicit version requirements when talking to the local daemon interface.

That means a local CLI request should be able to express requirements such as:

- minimum daemon version
- exact protocol or API version
- required capabilities or backend support

If those requirements are not met, the daemon interface should fail the request explicitly rather than allowing the CLI to proceed against an incompatible runtime.

#### 10. Add Standard Startup And Convergence Log Streaming

Add a standard daemon log streaming path for local clients.

This should support streaming:

- daemon startup logs
- service activation logs
- readiness transition events
- failure diagnostics

This log access should go through the local daemon interface rather than through direct local file reads from the CLI.

That is the correct boundary because it:

- keeps the CLI talking to one interface instead of inspecting daemon-owned files directly
- allows the daemon to choose how logs are stored internally
- supports future multi-daemon operation without changing the CLI log access model
- keeps local log access aligned with the same control-plane contract used for readiness and status

This keeps local startup observable without requiring the user to inspect daemon state out of band.

#### 11. Reuse Existing `--cluster` As The Remote Selector

Reuse the existing `--cluster` option as the explicit selector for remote control planes.

Control-plane selection should work like this:

- if `--cluster` is provided, use remote cluster mode
- if `--base-url` is provided, use remote cluster mode
- otherwise, use local daemon mode

This means the current implicit fallback chain for jobs submission should change.

Today the submit path can resolve remote host selection through active CLI context even when `--cluster` is not provided. That behavior is not compatible with a clean two-option model, because absence of `--cluster` would no longer reliably mean local mode.

For jobs under this design, remote selection should therefore be explicit. The CLI should not silently choose a remote control plane from active context when neither `--cluster` nor `--base-url` was supplied.

#### 12. Query Profiles Through The Selected Control Plane

Execution profiles should be queried through the selected control plane rather than inferred directly by the CLI from local config files.

That means:

- in remote cluster mode, query the remote jobs API for execution profiles
- in local daemon mode, use the daemon control API over UDS to discover the selected daemon and its jobs API port, then query the local jobs API over TCP/IP for execution profiles

This keeps profile discovery aligned with the actual runtime that will execute the job and avoids a split where the CLI believes one profile set is active while the daemon is using another.

#### 13. Support Multiple Local Daemons By Key

The local daemon control model should support multiple daemon instances, each identified by a daemon key.

This is primarily useful for testing, development, and version-isolated local runs rather than as a standard end-user workflow.

The daemon key should allow the CLI to:

- select which local daemon to discover or start
- resolve which daemon control socket to talk to
- discover which TCP/IP jobs API port that daemon is using
- run multiple daemon versions or configurations side-by-side when needed

The daemon key and discovered port should come from the daemon control interface rather than from fixed local assumptions.

## Backend Semantics

### Subprocess

`subprocess` is the explicit contract for running a host command in the local environment.

It should remain suitable for the lightest-weight local developer loop.

### Pause And Resume

Pause and resume must be supported in local daemon mode to preserve jobs API parity with remote backends.

For this spec, parity is required at the API and lifecycle-contract level, not at the low-level process-control level.

That means local subprocess mode must support:

- the same pause API
- the same resume API
- the same lifecycle states and transitions expected by the jobs contract

For the local subprocess backend, the expected implementation is restart-based rather than true in-memory process suspension.

That means:

- `pause` may terminate the running subprocess and transition the job to `PAUSED`
- `resume` may schedule a fresh subprocess execution from the persisted job step definition

This is acceptable for this spec because it preserves API parity and lifecycle parity without requiring the local subprocess backend to implement a more complex suspend-and-continue runtime model.

The spec should not imply that local subprocess pause/resume preserves in-memory process state. If true suspend/resume semantics are required later, that should be designed as separate follow-on work.

The client-visible pause/resume contract should also be explicit.

From a user and API perspective:

- `pause` should be accepted only for jobs in a pausable non-terminal state
- `pause` should transition the job through `PAUSING` and then to `PAUSED`
- `resume` should be accepted only for jobs in `PAUSED`
- `resume` should transition the job through `RESUMING` and then back into normal scheduling states such as `PENDING` or `ACTIVE`
- `pause` and `resume` should be idempotent at the API level

For local subprocess, the backend behavior should be:

- when a running step is paused, the backend may terminate the process group for the current task attempt
- the step definition, job state, and any job-persistent storage must remain available for later resume
- task-ephemeral storage may or may not survive pause depending on backend policy, but that policy must be explicit and not accidental
- resuming should create a new subprocess task execution from persisted job state rather than pretending the original process was frozen in place

The user-visible limitation should be explicit:

- pause/resume for local subprocess is stop-and-restart from persisted job state
- it should only be relied on by workloads that can tolerate restart-based semantics
- workloads that require in-memory suspension are out of scope for this backend

Failure handling should also be defined:

- if `pause` is requested for a terminal job, the API should return a clear no-op or validation error according to the normal jobs contract
- if the backend cannot successfully stop the subprocess during pause, the job should transition to `ERROR` with a clear reason
- if `resume` is requested but the persisted job state is no longer runnable, the job should transition to `ERROR` with a clear reason
- restart-based resume must respect the same daemon reuse, interpreter, profile, and service-availability checks as an initial run

### Logging

Logging must preserve client-visible API parity between local and remote modes.

For this spec:

- local subprocess logging may use local capture and OTLP export internally
- those mechanisms are implementation details of the local backend
- clients should not depend on direct access to local log files

From the client or user point of view, log access should be API-based in the same way it is for remote jobs.

That means:

- job logs should be retrieved through the jobs/logs API surface
- daemon startup and convergence logs should be retrieved through the local daemon control interface
- the CLI should not special-case local subprocess logs by reading daemon-owned files directly

This keeps local and remote logging behavior aligned at the product surface even if their internal log collection paths differ.

The client-visible logging contract should be more explicit.

For job logs:

- the same jobs/logs API surface should be used in local and remote modes
- log retrieval should be keyed by the normal jobs identifiers such as job, step, and task
- the API should support the same kinds of reads the CLI expects remotely, including tailing recent logs and following active logs when available
- clients should not need to know whether logs originated from local file capture, OTLP export, container logs, or pod logs

For local daemon logs:

- daemon startup logs should be available through the local daemon control interface
- service activation and readiness logs should be available through the local daemon control interface
- failure logs for daemon bootstrap or service activation should be available through the local daemon control interface
- log streaming should work in both foreground and background local modes

The relationship between backend-private logs and client-visible logs should also be explicit.

For subprocess:

- local file capture remains an internal implementation detail
- OTLP export remains an internal implementation detail
- neither internal mechanism defines the public client contract
- the daemon is responsible for making sure job logs are queryable through the jobs API regardless of how they are stored locally

The expected behavior for an active local job should be:

- a user runs `nemo jobs run ...`
- the CLI submits the job through the jobs API
- the CLI follows logs through the same jobs/logs API contract it would use remotely
- if the local daemon had to start or progressively activate services first, the CLI may also surface daemon-control logs during that phase
- once the job is running, task logs come from the jobs API rather than from daemon bootstrap channels

The transition between these two log sources should be clear:

- daemon control logs explain local control-plane bootstrap and readiness
- jobs API logs explain job execution

Retention and cleanup should also be clarified:

- backend-private log files may be rotated or deleted according to backend retention policy
- client-visible log retention should be defined at the jobs/logs API level rather than by direct access to those files
- local cleanup must not break the API contract for logs more aggressively than the configured backend retention policy allows

Failure behavior should be explicit:

- if job execution starts but log ingestion or export fails, the runtime should report that failure clearly rather than silently dropping logs
- if daemon bootstrap fails before the jobs API is available, the daemon control interface should expose enough logs to diagnose that failure
- if a user attaches to a foreground local daemon, that terminal output may be convenient, but it should not be the only supported way to observe daemon behavior

### Future Local Backends

This spec intentionally standardizes only the local subprocess path.

Additional local backends such as Docker or daemon-managed long-lived process groups may be added later, but they are not required to achieve the jobs local/remote unification described here.

## What Must Change Conceptually

### `run_local(...)` Stops Being Real

`run_local(...)` should not survive as a real execution architecture.

If retained temporarily, it should be a thin compatibility shim that:

- creates a jobs request
- submits it through a jobs API
- follows the result

It should not continue to instantiate and run jobs in-process.

### The CPU-Container-To-Subprocess Rewrite Stops Being A Target Behavior

The current rewrite may remain as compatibility logic for a transition period, but it should not define the target model.

Long term:

- jobs that mean `subprocess` should compile to `subprocess`

The platform should stop silently changing execution contract based on profile name.

## Operational Requirements

The local control-plane story must be explicit and user-visible.

At minimum the platform should make it clear:

- whether the CLI connected to an existing local jobs endpoint or started one
- how the local endpoint is identified
- how to inspect its logs
- how to stop it
- how duplicate daemons are prevented
- how reuse eligibility is determined when reusing an existing daemon

This is required for trust in local daemon mode.

## Recommendation

Adopt a single jobs-backed execution model with these properties:

- `run` and `submit` stay as interaction modes
- all execution flows through the jobs service contract
- local is a jobs hosting shape, not a separate execution path
- `subprocess` is the first-class local jobs backend in this spec
- profile-driven backend selection stays in place for now
- the current subprocess rewrite is treated as migration-only compatibility logic, not target architecture

This is a materially better model than the current split because it removes the fake distinction between "jobs" and "no jobs" without forcing a large redesign of the current jobs service.
