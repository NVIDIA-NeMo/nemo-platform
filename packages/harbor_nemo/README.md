# harbor-nemo

A [Harbor](https://github.com/harbor-framework/harbor) registry backend that publishes to and
runs from **NeMo Platform** instead of the public Harbor Hub, with no changes to Harbor.

```bash
pip install -e packages/harbor_nemo

export HARBOR_REGISTRY_BACKEND=nemo
export NMP_BASE_URL=http://localhost:8080

harbor publish ./my-task
harbor download nvidia/my-task -o ./out
harbor run -t nvidia/my-task --agent nop
```

Installing the package registers `nemo` under the `harbor.registry_backends` entry point.
That is the whole integration: the stock CLI resolves the backend by name at call time.

## How Harbor concepts map onto NeMo

| Harbor | NeMo |
|---|---|
| task package `org/name` | task entity `org.name` (`kind="harbor"`), one workspace |
| task version | a published *revision* of that entity |
| task archive (`dist.tar.gz`) | a file in the `harbor-packages` fileset |
| content hash | `spec.archive_digest` |
| dataset `org/name` | taskset entity `org.name` |
| dataset-level files | a JSON blob in taskset `metadata` (see *Known gaps*) |
| tags (`latest`, …) | revision tags |

**The org is folded into the entity name.** A NeMo workspace is a tenancy boundary with its
own lifecycle and authorization; a Harbor org is a cheap, self-serve namespace that
`harbor publish` creates on demand. Mapping org to workspace would make publishing a tenancy
operation. The cost is that the org prefix is a convention, not an enforced boundary.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NMP_BASE_URL` | `http://localhost:8080` | platform to publish to / read from |
| `HARBOR_NEMO_WORKSPACE` / `NMP_WORKSPACE` | `default` | workspace holding tasks and tasksets |
| `HARBOR_NEMO_FILESET` | `harbor-packages` | fileset holding package archives |
| `NMP_TOKEN` / `NMP_API_KEY` | — | bearer token, when the platform has auth enabled |
| `HARBOR_NEMO_TIMEOUT_SEC` | `120` | HTTP timeout |

Set `HARBOR_REGISTRY_WEBSITE_URL` too: `harbor publish` prints a hub URL from a Harbor-side
constant, so without it the CLI advertises `hub.harborframework.com` for NeMo packages.

## Two digests, and why it matters

NeMo addresses a revision by a digest of the revision's *content* (canonical JSON of the
stored spec). Harbor addresses a version by a digest of the task *directory's files*. They are
different hashes of different things, and both are live:

- `ResolvedTaskVersion.content_hash` carries **Harbor's**, because Harbor's download cache is
  keyed on it.
- A `sha256:` reference reaching `resolve_version` is always **Harbor's**, and is *not* a
  valid NeMo revision selector — the platform returns 404 for it. Resolving one is a scan
  over revisions comparing `spec.archive_digest`, not a direct fetch.
- A **revision ordinal** is not a valid selector either: the platform reads any non-digest
  fragment as a *tag name*, so `/revisions/2` looks for a tag called `"2"`. Ordinals are
  translated to that revision's content hash first.
- NeMo digests are **bare hex**, deliberately, so a `#` fragment stays free of `:` — which the
  entity-ref charset does not admit and the route's path pattern rejects with a 422. Harbor's
  `sha256:` prefix is stripped before any digest is used as a selector.

Publishing a dataset translates between the two spaces: a Harbor manifest pins members by
archive digest, a taskset pins by revision digest, so each member costs one lookup. This is
not optional — the taskset service re-resolves bare member refs at write time, so an
unpinned member would silently pin whatever was `latest` at publish, not what the manifest
named.

## Known gaps

- **Dataset-level files ride in taskset `metadata`** as a JSON string, because a taskset has
  no file-reference field. A taskset-level file reference would replace this.
- **No yank support.** `ResolvedTaskVersion.yanked_at` is always `None`; NeMo has no
  equivalent.
- **`record_download` is a deliberate no-op.** NeMo has no counter primitive, so implementing
  it would mean a read-modify-write on the hottest entity per package for best-effort
  telemetry.
- **`harbor version list|show|tag` is Supabase-pinned** in Harbor itself and will show Hub
  data regardless of `HARBOR_REGISTRY_BACKEND`.

## Requirements

Needs a NeMo Platform with the `entities`, `files`, and `evaluator` services, and the
`kind="harbor"` task definition from nemo-platform PR #1071.

```bash
uv run nemo services run --services entities,files,evaluator --port 8080
```
