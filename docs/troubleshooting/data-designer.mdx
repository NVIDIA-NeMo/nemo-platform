<a id="trbl-ndd-dc"></a>
# Troubleshoot Data Designer

Learn how to troubleshoot common issues with {{ndd_short_name}} in a local {{platform_name}} setup.

## Prerequisites

Before troubleshooting, make sure:

- The `nemo` CLI is installed and available: `nemo --help`.
- Local platform services are running from `nemo setup` or `nemo services run`.
- Your CLI context points at the workspace where the Data Designer job or fileset was created. Use `nemo workspaces list` to confirm available workspaces.

## Check Platform Health

Verify that the local platform API is ready:

```bash
curl -s http://localhost:8080/health/ready
```

If the health check fails, re-run setup:

```bash
nemo setup
```

## Check Service Logs

Local setup writes service output to `.nemo-services.log` in the directory where services were started.

```bash
tail -n 200 .nemo-services.log
tail -f .nemo-services.log
```

Look for startup errors, provider authentication failures, port conflicts, or Data Designer request failures.

## Common Issues

- **Port conflicts**: Ensure port `8080` is not in use by another local application.
- **Authentication**: Confirm that the model provider configured by `nemo setup` has a valid API key.
- **Network connectivity**: Ensure your machine can reach package indexes and configured model-provider endpoints.
- **No healthy upstream (503)**: A `503` response can mean services are still starting. Wait for readiness, then retry the request.
- **Dataset access**: Confirm that referenced filesets exist in the selected workspace and that remote dataset credentials are configured when required.

## Next steps

- Tutorial: [Data Designer Tutorials](../data-designer/tutorials/index.md) covers common generation workflows.
- How-to: [Set Up {{platform_name}}](../get-started/setup.md) covers local setup and service startup.
- Explanation: [Data Designer Overview](../data-designer/index.md) explains configuration, execution, and service behavior.
- Reference: [API Reference](../api/index.md#tag-data-designer) lists Data Designer endpoints.
- Troubleshooting: [Troubleshooting Overview](index.md) links to other service troubleshooting pages.
