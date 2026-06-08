# Contributing

For the release process (version bumps, triggering stable releases, verification), see [RELEASING.md](RELEASING.md).

## Getting Started

### Local Setup

#### Clone the repository

Clone the repository before bootstrapping the local environment.

```bash
git clone <repo-url> nemo-platform
cd nemo-platform
```

#### Repository bootstrapping

Install the local prerequisites first, then run the bootstrap targets from the repository root.

#### Python Environment Setup

This project uses [uv](https://github.com/astral-sh/uv) for dependency management of the Python environment.

Additionally, it leverages [ruff](https://github.com/astral-sh/ruff) for linting and [ty](https://github.com/astral-sh/ty) for static typechecking, both of which are enforced by CI. For details on configuration, see the [`pyproject.toml`](./pyproject.toml).

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/0.9.14/install.sh | sh
```

> **NeMo Platform uses uv version `>=0.9.14`.**
>
> When updating this version, make sure to update the version in
> `pyproject.toml` and CI jobs.

#### Studio Environment Setup

If you plan to work on Studio or modify files in `web/`, you'll need Node.js and pnpm installed.

For complete Studio setup instructions, see the [Getting Started section in the Studio README](web/README.md#getting-started).

##### Prerequisites

1. **Node.js matching the Studio workspace engine**: Install a Node version that satisfies the `engines.node` range in `web/package.json`.
2. **pnpm**: Install via corepack (included with Node.js 16.13+)

```bash
corepack enable pnpm
```

#### Initialize the Repository

After installing the prerequisites above, initialize the local repository environment:

```bash
make bootstrap
```

If you only need Python dependencies, use `make bootstrap-python`.

##### Building the Studio UI for Local Development

`make bootstrap` already installs the web dependencies and builds the
Studio assets needed by the FastAPI service. To rebuild just the Studio bundle:

```bash
make bootstrap-studio
```

The Studio service automatically detects these source-built assets when packaged static assets are not present.

##### Development Workflow

For active UI development, you can run the Vite dev server instead of rebuilding:

```bash
cd web/packages/studio
pnpm dev
```

This provides hot module replacement (HMR) at the local URL printed by Vite.

When you're ready to test with the FastAPI service, rebuild with `pnpm build:fastapi`.

##### Running the Platform with Studio

Ensure you have bootstrapped Python dependencies and Studio UI assets:

```bash
make bootstrap
```

Run the interactive setup flow to configure and start local services:

```bash
uv run nemo setup
```

Then start the platform from the repository root:

```bash
# From an activated virtual environment
source .venv/bin/activate
nemo services run

# Or run everything with quickstart config (builds OPA policy first)
make run

# Or run specific services
uv run nemo services run --services studio,entities

# Or run with a config file for additional settings
NMP_CONFIG_FILE_PATH=packages/nmp_platform/config/local.yaml \
  uv run nemo services run --services studio,entities
```

Visit `http://localhost:8080/studio/` to access the Studio UI.

#### Using direnv for Automatic Virtual Environment Activation (Optional)

[direnv](https://direnv.net/) can automatically activate your virtual environment
when you enter the project directory, eliminating the need to manually source
the venv or use `uv run` for every command.

```bash
eval "$(direnv hook bash)"  # for bash
eval "$(direnv hook zsh)"   # for zsh
```

Create an `.envrc` file in the repository root (note: the `install_direnv.sh`
script creates this file automatically if it doesn't exist):

```bash
# See https://github.com/direnv/direnv/wiki/Python
# This has to be before our PATH_adds as well
export VIRTUAL_ENV=.venv
layout python3
# this should make it so you don't have to source the venv directly
PATH_add $VIRTUAL_ENV/bin
# ensure local bin is ahead of the venv, mostly for UV. we want to use the
PATH_add ./script
```

Allow direnv to load the configuration:

```bash
direnv allow
```

Now when you `cd` into the repository, the virtual environment will
automatically activate. You can run commands like `pytest` or `ruff` directly
without needing to prefix them with `uv run`.

Initialize pre-commit:

```bash
pre-commit install
```

## Development

### Running the Development Server

To start a server in development mode:

```bash
# Recommended: builds OPA policy and runs with quickstart config
make run

# Or run directly with the nemo CLI (from an activated venv)
nemo services run

# Or run with a custom config file
nemo services run --config packages/nmp_platform/config/local.yaml
```

For more options and details, see [Local Development](#local-development) below.

### Running Tests

Test running is generally done with `uv run pytest <path>`, at a basic level. Service-specific README files and CI workflow files show the broader test combinations.

### Pre-commit

Run pre-commit with `uv run pre-commit -a` to target all files in the repository

If you run `pre-commit install` in the repo it will setup git hooks as needed

### IDE Setup

#### Cursor Rules

This project uses Cursor rules to provide AI assistants with project-specific context and guidelines. Rules are stored in `.cursor/rules/` as Markdown files with the `.mdc` extension.

##### Project-Level Rules

Project-level rules apply to all developers working on the codebase and should be committed to version control. These rules help ensure consistency across the team by providing the AI with shared conventions, patterns, and best practices.

To add or maintain project-level rules:

1. Create a new `.mdc` file in `.cursor/rules/` (e.g., `python-testing.mdc`, `api-conventions.mdc`)
2. Write your rule using the standard Cursor rule format with frontmatter:

   ```markdown
   ---
   description: Brief description of what this rule covers
   alwaysApply: false
   ---
   # Rule Title
   
   Rule content...
   ```

3. Commit the file to version control so it's shared with the team

Current project rules:

- `uv.mdc` - Python package management with uv

##### Personal Rules

Personal rules allow individual developers to add their own preferences without affecting other team members. These rules are **not committed to version control**.

To add personal preference rules:

1. Create a new file in `.cursor/rules/personal/` (e.g., `personal/code-style.mdc`, `personal/workflow.mdc`)
2. Write your personal preferences using the same rule format as project rules
3. The entire `personal/` directory is automatically ignored by git (see `.gitignore`)

Personal rules are ideal for:

- Individual coding style preferences
- Personal workflow optimizations
- Tool preferences that differ from team standards
- Experimental rules you're testing before proposing as project-wide

### License Information

`third_party/licenses.jsonl` is protected by code owners responsible for verifying any new dependencies are approved by the open source review board (OSRB) and appropriate tracking bugs are filed.

A snapshot of Python dependencies, versions, and their detected licenses is maintained in `third_party/licenses.jsonl`. The CI linting stage validates that the checked-in license file matches with the detected dependencies. This file can be automatically regenerated by:

```bash
make update-licenses
```

This command uses [osv-scanner](https://github.com/google/osv-scanner) to scan dependencies and generate the license report. The Makefile will automatically download osv-scanner if it's not already installed.

Alternatively, you can use the SDK/license maintenance CLI directly:

```bash
# Generate license reports for main and garak
nemo-platform-sdk-tools license generate

# Find packages with missing licenses
nemo-platform-sdk-tools license find-missing
```

The license generation process creates intermediate JSON files (`third_party/osv-licenses.json`, `third_party/osv-licenses-garak.json`) which are marked as generated files in `.gitattributes`.

License overrides for packages where osv-scanner cannot determine the correct license are maintained in `tools/nemo-platform-sdk-tools/src/nemo_platform_sdk_tools/license/overrides.yaml`. This YAML file supports comments to document the source of license information.

This may be added as a pre-commit job in the future.

### OpenAPI Specification

A snapshot of the OpenAPI specification is checked in at `openapi/openapi.yaml`. This file is always up to date with the current version of code, and a CI job in the linting phase verifies this. To regenerate the OpenAPI specification:

```bash
make refresh-openapi
```

For more details regarding the OpenAPI specification, see the [OpenAPI README](openapi/README.md).

Automatic generation of this file may be added as a pre-commit job in the future.

### Local Development

For source development, prefer running Python processes directly in your local environment.

#### In-Process Development

`nemo services run` runs NeMo Platform services directly in your local Python environment, which is ideal for active development with fast iteration.

##### Prerequisites

- Python environment set up with `uv sync`
- Any dependent services required by the area you are changing

##### Usage

The simplest way to run locally is with `make run`, which builds the OPA policy and starts all services with the quickstart config:

```bash
make run
```

For more control, invoke the CLI directly. The examples below assume an activated virtual environment; prefix with `uv run` if you don't have one:

```bash
# Run with a custom config file
nemo services run --config path/to/config.yaml

# Run specific services only
nemo services run --services hello-world
nemo services run --services jobs --controllers jobs

# Run a predefined service group
nemo services run --service-group core  # Infrastructure only
nemo services run --service-group api   # Application services
nemo services run --service-group all   # Everything
```

The platform binds to `127.0.0.1:8080` by default. You can customize the host and port:

```bash
nemo services run --host 127.0.0.1 --port 8080
```

To run the platform in the background instead of the foreground, use `nemo services start` (and `nemo services stop` / `nemo services status` to manage it). See `nemo services --help` for the full set of subcommands.

## Contribution License

This project is licensed under the [Apache License, Version 2.0](LICENSE). By
contributing to this project, you agree that your contributions will be licensed
under the same license. All new inbound code contributions must be made under
the Apache License, Version 2.0, without any additional terms or conditions.

All source files must include an SPDX copyright header. For new files, use the
appropriate format for the file type:

**Python / Shell / YAML:**

```python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
```

**TypeScript / JavaScript:**

```typescript
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
```

**CSS:**

```css
/* SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. */
/* SPDX-License-Identifier: Apache-2.0 */
```

A pre-commit hook validates copyright headers automatically. You can also run
the checker manually:

```bash
make check-copyright-headers
```

## Signing Your Work

* We require that all contributors "sign-off" on their commits. This certifies that the contribution is your original work, or you have rights to submit it under the same license, or a compatible license.

  * Any contribution which contains commits that are not Signed-Off will not be accepted.

* To sign off on a commit you simply use the `--signoff` (or `-s`) option when committing your changes:
  ```bash
  $ git commit -s -m "Add cool feature."
  ```
  This will append the following to your commit message:
  ```
  Signed-off-by: Your Name <your@email.com>
  ```

* Full text of the DCO (https://developercertificate.org/):

  ```
    Developer Certificate of Origin
    Version 1.1

    Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

    Everyone is permitted to copy and distribute verbatim copies of this
    license document, but changing it is not allowed.


    Developer's Certificate of Origin 1.1

    By making a contribution to this project, I certify that:

    (a) The contribution was created in whole or in part by me and I
        have the right to submit it under the open source license
        indicated in the file; or

    (b) The contribution is based upon previous work that, to the best
        of my knowledge, is covered under an appropriate open source
        license and I have the right under that license to submit that
        work with modifications, whether created in whole or in part
        by me, under the same open source license (unless I am
        permitted to submit under a different license), as indicated
        in the file; or

    (c) The contribution was provided directly to me by some other
        person who certified (a), (b) or (c) and I have not modified
        it.

    (d) I understand and agree that this project and the contribution
        are public and that a record of the contribution (including all
        personal information I submit with it, including my sign-off) is
        maintained indefinitely and may be redistributed consistent with
        this project or the open source license(s) involved.
  ```
