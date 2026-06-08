# Safe Synthesizer Results

## Prerequisites

- Resolve the CLI with the command in `workflows/run.md`.
- For host-local runs, know the `--output-dir` passed to `nemo safe-synthesizer run-local`.
- For platform jobs, know the job name and workspace.

## Host-Local Runs

`nemo safe-synthesizer run-local --output-dir ./nss-output` writes artifacts under the output directory.

Start answers with the exact output directory when it is known:

```bash
ls ./nss-output
```

## Platform Jobs

Platform jobs publish named results through the Jobs service:

- `summary`
- `synthetic-data`
- `evaluation-report`
- `adapter`

Use the Jobs API or SDK to list and fetch result records for platform jobs. The plugin CLI does not expose `nemo safe-synthesizer jobs ...` result commands.

## Next Steps

- Interpret artifact names and missing output cases with `workflows/artifacts.md`.
- Check platform job status with the Jobs API or SDK.
- Diagnose failures with `workflows/diagnose.md`.
