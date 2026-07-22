# Models Integration Tests

## Running Tests with Docker-in-Docker (DinD)

To simulate the CI environment locally, you can run integration tests against a Docker-in-Docker container. This is useful for debugging flaky tests that only fail in CI.

### Setup

1. Start a DinD container with the required port range exposed:

```bash
docker run --privileged -d --name dind \
  -p 2376:2376 \
  -p 50000-51599:50000-51599 \
  -e DOCKER_TLS_CERTDIR=/certs \
  -v dind-certs:/certs \
  docker:28.3.1-dind
```

The port range `50000-51599` supports up to 16 parallel pytest workers with 100 ports each.

2. Wait for DinD to initialize and copy TLS certificates:

```bash
sleep 5
docker cp dind:/certs/client /tmp/docker-certs
```

3. Set environment variables for Docker client and test configuration:

```bash
export DOCKER_HOST=tcp://localhost:2376
export DOCKER_TLS_VERIFY=1
export DOCKER_CERT_PATH=/tmp/docker-certs
export MODELS_DOCKER_PORT_RANGE_START=50000
```

### Running Tests

Run the integration tests with parallel workers:

```bash
uv run pytest services/core/models/tests/integration/ -v -n 4 --dist loadscope
```

To run specific tests:

```bash
uv run pytest services/core/models/tests/integration/test_deployments_plugin_lifecycle.py::test_deployments_plugin_docker_lifecycle -v
```

### Cleanup

Stop and remove the DinD container:

```bash
docker rm -f dind
docker volume rm dind-certs
rm -rf /tmp/docker-certs
```

### Troubleshooting

**Port allocation failures**: If tests fail with "No ports available in range", ensure:
- The DinD container was started with the correct port range exposed
- `MODELS_DOCKER_PORT_RANGE_START` matches the exposed range start

**Health check failures**: The backend automatically detects remote Docker hosts via `DOCKER_HOST` and skips local port binding checks. If health checks fail, verify:
- The port range is correctly forwarded from DinD to the host
- No firewall rules are blocking the port range

**Certificate errors**: If you see TLS certificate errors:
- Ensure `/tmp/docker-certs` contains `ca.pem`, `cert.pem`, and `key.pem`
- Verify `DOCKER_CERT_PATH` points to the correct directory
