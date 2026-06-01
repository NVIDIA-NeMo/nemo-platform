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

Use the generated Safe Synthesizer jobs result commands when available:

```bash
nemo safe-synthesizer jobs results list <job-name> --workspace default
nemo safe-synthesizer jobs results get <result-name> --job <job-name> --workspace default
```

If those generated commands differ in the installed CLI, run `nemo safe-synthesizer jobs results --help` and follow the current help text.

## Next Steps

- Interpret artifact names and missing output cases with `workflows/artifacts.md`.
- Check job status with `nemo safe-synthesizer jobs get <job-name> --workspace <workspace>`.
- Diagnose failures with `workflows/diagnose.md`.
