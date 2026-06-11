# NeMo Platform Common MCP Utilities

Shared utilities for building Model Context Protocol (MCP) servers within the NeMo Platform.

## Overview

This module provides common functionality used across all MCP servers in the platform, ensuring consistency in client creation, error handling, and response formatting. These utilities enable the hybrid MCP architecture where service teams can build their own MCP servers while maintaining a cohesive user experience.

## Purpose

When multiple MCP servers exist across the platform:

```
services/core/mcp/              # Core infrastructure tools
services/guardrails/mcp/        # Guardrails-specific tools
services/evaluator/mcp/         # Evaluation-specific tools
plugins/nemo-customizer/        # Customization plugin (router + contributor discovery)
```

These shared utilities ensure:

- ✅ **Consistent client configuration** across all servers
- ✅ **Standardized error responses** for AI agents
- ✅ **Single source of truth** for common patterns
- ✅ **Reduced code duplication** across service teams
- ✅ **Easier maintenance** and evolution

## Modules

### `error_handling.py`

Formats tool responses and errors consistently across all MCP servers.

**Functions**:

#### `format_error_response(error: Exception) -> dict[str, Any]`

Converts exceptions into standardized error responses with automatic logging.

**Returns**:

```python
{
    "success": False,
    "error": "Connection refused to localhost:8080",
    "error_type": "ConnectionError"
}
```

**Example Usage**:

```python
from nmp.common.mcp import format_error_response

@server.tool()
async def deploy_model(model_id: str) -> dict[str, Any]:
    try:
        result = await nemo_client.models.deploy(model_id)
        return {
            "success": True,
            "deployment_id": result.id,
            "status": result.status
        }
    except Exception as e:
        # Logs error with stack trace + returns formatted response
        return format_error_response(e)
```

**Why Use This Pattern**:

- AI agents can reliably check `success` field
- Consistent error structure across all tools
- Automatic error logging with stack traces
- Easy to add error codes, retry hints, or sanitization
- Success responses manually constructed with explicit fields

---

## Usage Pattern

All MCP servers should follow this pattern:

```python
# In any MCP server (e.g., services/core/entities/src/nmp/core/entities/mcp/server.py)
from fastmcp import FastMCP
from nmp.common.mcp import format_error_response
from nmp.common.sdk_factory import get_platform_sdk

def create_server(base_url: str | None = None) -> FastMCP:
    """Create MCP server with tools."""
    server = FastMCP("Service Name")

    # Use shared SDK factory (same as REST services)
    nemo_client = get_platform_sdk(base_url)

    @server.tool(description="Tool description for AI agents")
    async def my_tool(param: str) -> dict[str, Any]:
        """
        Tool documentation.

        Args:
            param: Parameter description

        Returns:
            Dictionary with success and result data
        """
        try:
            result = nemo_client.some_operation(param)
            return {
                "success": True,
                "result": result,
                "additional_field": "value"
            }
        except Exception as e:
            # Use shared error formatter
            return format_error_response(e)

    return server
```

## Benefits for Distributed Development

### For Service Teams

When service teams build their own MCP servers:

```python
# services/guardrails/src/nmp/guardrails/mcp/server.py
from fastmcp import FastMCP
from nmp.common.mcp import format_error_response
from nmp.common.sdk_factory import get_platform_sdk

guardrails = FastMCP("NeMo Guardrails")
client = get_platform_sdk()

@guardrails.tool()
async def create_guardrail_config(rules: dict):
    try:
        result = client.guardrails.configs.create(rules)
        return {"success": True, "config_id": result.id}
    except Exception as e:
        return format_error_response(e)
```

**Benefits**:

- Use same SDK factory as REST services (consistency across platform)
- No need to duplicate client creation logic
- Automatic consistency with other MCP servers
- Focus on domain-specific tool logic
- Inherit improvements to shared utilities

### For Platform Team

When aggregating multiple service MCP servers:

```python
# services/core/mcp/src/nmp/core/mcp/server.py
from nmp.guardrails.mcp.server import guardrails
from nmp.evaluator.mcp.server import evaluator

platform = FastMCP("NeMo Platform")
platform.mount(guardrails)  # All tools use same patterns
platform.mount(evaluator)   # Consistent for agents
```

**Benefits**:

- Unified experience across all mounted servers
- Agents see consistent error formats
- All servers follow same configuration patterns
- Easy to add cross-cutting concerns (auth, rate limiting, metrics)

## Evolution & Maintenance

### Adding New Features

MCP servers use `nmp.common.sdk_factory.get_platform_sdk()` for SDK client creation, which is the same factory used by REST services. This ensures:

- **Consistency**: MCP and REST services use identical SDK configuration
- **Centralized updates**: Changes to SDK factory benefit both MCP and REST
- **Auth support**: Automatic service principal auth via `as_service` parameter
- **Test injection**: HTTP client injection for testing (same as REST services)

See `packages/nmp_common/src/nmp/common/sdk_factory.py` for SDK factory implementation and configuration options.

### Adding Error Enhancements

**Example**: Add error codes for agents

```python
# nmp/common/mcp/error_handling.py
def format_error_response(error: Exception) -> dict[str, Any]:
    logger.error(f"Error in MCP tool: {error}", exc_info=True)

    # Map exception types to codes
    error_codes = {
        "ConnectionError": "PLATFORM_UNAVAILABLE",
        "TimeoutError": "PLATFORM_TIMEOUT",
        "HTTPStatusError": "API_ERROR",
    }

    return {
        "success": False,
        "error": str(error),
        "error_type": type(error).__name__,
        "error_code": error_codes.get(type(error).__name__, "UNKNOWN_ERROR"),
        "retryable": isinstance(error, (ConnectionError, TimeoutError))
    }
```

All tools instantly provide better error information to agents.

## Future Utilities

Potential additions to this module:

- **Rate limiting decorators** - Throttle tool calls per agent
- **Metrics collection** - Track tool usage across servers
- **Caching utilities** - Cache expensive SDK calls
- **Validation helpers** - Common parameter validation patterns
- **Authentication decorators** - Workspace/role-based access control

See also the devjournal [architecture/devjournal/3294-devjournal-MCP-services.md](../../../../../../architecture/devjournal/3294-devjournal-MCP-services.md) for more details on how we arrived at these decisions and future plans.

---

*Last updated: 2026-01-21*
