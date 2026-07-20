# Authentik Docker Compose Runtime

This directory contains the Docker Compose runtime files for the Authentik
reference example.

Use the single shared tutorial for the end-to-end walkthrough:

- [Authentik Reference Tutorial](../tutorial.md)

For Compose-specific architecture and wiring, see:

- [Implementation Details](implementation-details.md)

The Compose runtime starts with:

```bash
cd contrib/auth/authentik/compose
docker compose up
```

The Compose project name defaults to `nemo-platform-authentik`, so container,
network, and volume names do not inherit the generic `compose` directory name.
Set `COMPOSE_PROJECT_NAME` before running `docker compose` if you need a
different local namespace.
