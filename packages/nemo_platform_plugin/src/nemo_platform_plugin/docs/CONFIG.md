<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Plugin Configuration (NemoConfig)

## NemoConfig

`NemoConfig` is a `pydantic-settings` base class that wires your plugin's typed configuration to environment variables and the platform YAML config file.

Class signature:
```python
class NemoConfig(EnvironmentFirstSettings, metaclass=_NemoConfigMeta):
    plugin_name: ClassVar[str]           # REQUIRED — kebab-case (matches CLI entry-point key)
    plugin_description: ClassVar[str]    # REQUIRED — non-empty string

    @classmethod
    def get(cls) -> Self: ...            # returns cached singleton
```

Both `plugin_name` and `plugin_description` must be declared in the concrete subclass body. Omitting either raises `TypeError` at class-definition time.

## Defining a config class

```python
from typing import ClassVar, Literal
from pydantic import Field
from nemo_platform_plugin.config import NemoConfig

class ExampleConfig(NemoConfig):
    plugin_name: ClassVar[str] = "example"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Platform example plugin."

    greeting_style: Literal["formal", "casual"] = Field(
        default="formal",
        description="Controls the tone of /hello/{name} responses.",
    )
    log_requests: bool = Field(
        default=False,
        description="When True, emits structured INFO log for list endpoint calls.",
    )
```

## Environment variables

Env var formula: `NMP_<SAFE_NAME>_<FIELD>` where `SAFE_NAME = plugin_name.upper()` with non-word characters replaced by `_`.

| `plugin_name` | Env prefix | Example field | Env var |
|---|---|---|---|
| `"my-plugin"` | `NMP_MY_PLUGIN_` | `debug` | `NMP_MY_PLUGIN_DEBUG` |
| `"agents"` | `NMP_AGENTS_` | `runner_backend` | `NMP_AGENTS_RUNNER_BACKEND` |
| `"example"` | `NMP_EXAMPLE_` | `greeting_style` | `NMP_EXAMPLE_GREETING_STYLE` |

Nested fields use `_` as the delimiter:

```bash
NMP_AGENTS_CONTROLLER_INTERVAL_SECONDS=10
NMP_AGENTS_CONTROLLER_PORT_RANGE_START=49152
```

## Config file

The config key in `/etc/nmp/config.yaml` matches `plugin_name`:

```yaml
my_plugin:
  debug: true
  max_workers: 8
```

Override the config file path: `NMP_CONFIG_FILE_PATH=/my/custom/config.yaml`

The platform logs a warning (not an error) when `/etc/nmp/config.yaml` does not exist. Defaults apply — expected for local development.

## Priority order

1. **Environment variables** (`NMP_<NAME>_<FIELD>`) — highest priority
2. **Config file** (`/etc/nmp/config.yaml`)
3. **Field defaults** — lowest priority

## Accessing config

```python
# Option 1: classmethod (returns cached singleton — same instance every call)
from nemo_my_plugin.config import MyPluginConfig
config = MyPluginConfig.get()

# Option 2: standalone function
from nemo_platform_plugin.config import get_nemo_config
config = get_nemo_config(MyPluginConfig)
```

## Nested config models

Use a plain `BaseModel` (NOT `NemoConfig`) for nested config sections. `NemoConfig` is only for the top-level class.

```python
from typing import ClassVar
from pydantic import BaseModel, Field
from nemo_platform_plugin.config import NemoConfig

class ControllerConfig(BaseModel):  # plain BaseModel — NOT NemoConfig
    interval_seconds: int = Field(default=5)
    health_check_timeout_seconds: int = Field(default=120)

class AgentsConfig(NemoConfig):
    plugin_name: ClassVar[str] = "agents"
    plugin_description: ClassVar[str] = "Configuration for the NeMo Platform agents plugin."

    controller: ControllerConfig = Field(default_factory=ControllerConfig)
    runner_backend: str = Field(default="in_memory")

# Access nested field:
config = AgentsConfig.get()
interval = config.controller.interval_seconds  # NMP_AGENTS_CONTROLLER_INTERVAL_SECONDS
```

## Testing

```python
import pytest
from nemo_platform_plugin.config import (
    set_nemo_config_override,
    clear_nemo_config_override,
    clear_nemo_config_overrides,
)
from nemo_my_plugin.config import MyPluginConfig

# Per-test override with manual cleanup:
def test_debug_mode():
    set_nemo_config_override(MyPluginConfig(debug=True))
    try:
        config = MyPluginConfig.get()
        assert config.debug is True
    finally:
        clear_nemo_config_override(MyPluginConfig)

# Recommended: autouse fixture that clears all overrides after every test:
@pytest.fixture(autouse=True)
def reset_config():
    yield
    clear_nemo_config_overrides()
```

Three cleanup functions:
- `clear_nemo_config_override(cls)` — removes override for one config class
- `clear_nemo_config_overrides()` — removes ALL overrides (all config classes)

## Common mistakes

1. **`plugin_name` in snake_case** — use kebab-case to match your CLI entry-point key (e.g., `plugin_name = "my-plugin"`). The env prefix is derived by uppercasing and replacing `-` with `_`: `NMP_MY_PLUGIN_*`. Your YAML config key should also use `my-plugin:`.

2. **Calling `MyPluginConfig()` directly in production code** — bypasses env/file loading entirely. Always use `MyPluginConfig.get()` or `get_nemo_config(MyPluginConfig)`.

3. **Forgetting cleanup in tests** — config is cached; a test override bleeds into subsequent tests unless cleaned up. Use the autouse fixture pattern above.
