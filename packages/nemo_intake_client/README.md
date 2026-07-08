# NeMo Intake Client

Typed request, response, and HTTP client contracts for the NeMo Platform Intake plugin.

This package intentionally contains no service entry points, FastAPI routers, ClickHouse code,
or OTLP runtime dependencies. Installing it cannot cause the Intake service to be discovered.
