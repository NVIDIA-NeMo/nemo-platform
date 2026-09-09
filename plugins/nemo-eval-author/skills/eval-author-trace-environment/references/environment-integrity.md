# Environment integrity protocol

Apply this protocol to every candidate before finalization.

## Network isolation

In addition to the separate no-network verifier contract, require the agent
environment to set `[environment].network_mode = "no-network"`. A step-local
agent environment may inherit that setting or repeat `network_mode =
"no-network"`; it must never enable public networking. Resolve and vendor the
complete build and runtime dependency closure before grading.

## Reproducibility manifest

Record the exact task tree before running Harbor:

```bash
python <skill_dir>/scripts/trace_environment.py record-reproducibility \
  --task-dir <task-dir>
```

The manifest hashes every task path, file byte, directory, and executable bit.
It records a declared source revision, Dockerfile base images, network modes,
and one portability state: `local_only`, `recipe_rebuildable`, or
`immutable_image`. A recipe is rebuildable only when the agent Dockerfile exists
and every base image is pinned by digest. A configured agent image is immutable
only when its reference contains a SHA-256 digest.

The scan fails closed on Git metadata in `task/environment`, exact solution or
hidden-test files copied into the agent build context, private keys, bearer
credentials, credential-bearing URLs, and symlinks. It is a static task-tree
gate, not an inspection of opaque image layers. Keep image-construction
transcripts private and inspect pre-existing opaque images separately.

## Repeat and negative-control proof

Run every arm as an independent Harbor invocation so each result records a
distinct job ID and fresh task containers. Require at least two NOP runs, two
Oracle runs, and one negative control. NOP must receive reward `0`, Oracle must
receive reward `1`, and every run must finish without an exception.

The negative control must be a deliberately incomplete or subtly incorrect,
non-crashing solution relevant to the task and must receive reward `0`. Do not
reuse NOP as the negative control. Record the mutation in private construction
notes without exposing verifier logic.

Retain each exact Harbor job directory. Repeat each job option once per result:

```bash
python <skill_dir>/scripts/trace_environment.py record-validation \
  --task-dir <task-dir> \
  --nop-job-dir private/jobs/nop-1 \
  --nop-job-dir private/jobs/nop-2 \
  --oracle-job-dir private/jobs/oracle-1 \
  --oracle-job-dir private/jobs/oracle-2 \
  --negative-job-dir private/jobs/negative-1 \
  --harbor-version "$(harbor --version)"
```

The helper requires unique Harbor job IDs, a shared task checksum, separate
verifier mode in every result, and a task-tree digest matching
`reproducibility.json`. Failed proof remains technical evidence: retain it and
report the candidate as failed.
