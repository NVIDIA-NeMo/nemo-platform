# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Post-generation update tool for NeMo Platform SDK.

This script applies customizations to the auto-generated SDK after Stainless generation.
It handles README merging, pyproject.toml updates, and LICENSE file copying.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Tuple

import tomlkit
import typer
from nemo_platform_sdk_tools.sdk.core.common import SdkInfo, get_sdk_info
from nemo_platform_sdk_tools.sdk.post_generation_exist_ok import inject_exist_ok

app = typer.Typer(
    name="post-generation", help="Post-generation update tool for NeMo Platform SDK.", no_args_is_help=True
)


def sdk_version_file_content(package_name: str) -> str:
    return f'''# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from importlib.metadata import PackageNotFoundError, version as _package_version

__title__ = "nemo_platform"
try:
    __version__ = _package_version("{package_name}")
except PackageNotFoundError:
    __version__ = "0.0.0"
# Injected at release time for non-production builds; None for RC and production releases.
__image_tag__: str | None = None
'''


def merge_readme_files(readme_dir: Path) -> str:
    """Merge README markdown files in numerical order."""
    readme_files = sorted([f for f in readme_dir.glob("*.md") if f.name[0].isdigit()])

    if not readme_files:
        typer.echo(f"Error: No numbered README files found in {readme_dir}", err=True)
        raise typer.Exit(code=1)

    merged_content = []

    for readme_file in readme_files:
        typer.echo(f"  - Merging {readme_file.name}")
        content = readme_file.read_text(encoding="utf-8").strip()
        merged_content.append(content)

    return "\n\n".join(merged_content)


def get_string_replacements() -> List[Tuple[str, str]]:
    """Get list of string replacements to apply to source code."""
    stainless_sdk_url = "https://www.github.com/stainless-sdks/nemo-platform-python"
    nemo_docs_url = "https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html"

    return [
        (
            stainless_sdk_url + "#accessing-raw-response-data-eg-headers",
            nemo_docs_url + "#accessing-raw-response-data-e-g-headers",
        ),
        (stainless_sdk_url + "#with_streaming_response", nemo_docs_url + "#with_streaming_response"),
        # Add more replacements here as needed
        # (old_string, new_string),
    ]


def check_for_stainless_references(sdk_dir: Path) -> List[Tuple[Path, int, str]]:
    """Check for any remaining references to Stainless URLs in the SDK code."""
    # Patterns to look for
    stainless_patterns = ["stainless.com", "github.com/stainless-sdks", "stainless-sdks"]

    # File patterns to process
    patterns = ["**/*.py"]

    # Files to exclude from processing
    exclude_patterns = [
        "**/.*",  # Hidden files
        "**/__pycache__/**",  # Python cache
        "**/node_modules/**",  # Node modules
        "**/venv/**",  # Virtual environments
        "**/.venv/**",  # Virtual environments
    ]

    findings = []

    for pattern in patterns:
        for file_path in sdk_dir.glob(pattern):
            # Skip if file matches exclude patterns
            if any(file_path.match(exclude_pattern) for exclude_pattern in exclude_patterns):
                continue

            # Skip if not a file
            if not file_path.is_file():
                continue

            try:
                # Read file content
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()

                # Check each line for stainless references
                for line_num, line in enumerate(lines, 1):
                    for stainless_pattern in stainless_patterns:
                        if stainless_pattern.lower() in line.lower():
                            findings.append((file_path, line_num, line.strip()))
                            break  # Only report once per line

            except (UnicodeDecodeError, PermissionError):
                # Skip files that can't be read
                continue

    return findings


def apply_string_replacements(sdk_dir: Path, replacements: List[Tuple[str, str]]) -> None:
    """Apply string replacements to all Python."""
    # File patterns to process
    patterns = ["**/*.py"]

    # Files to exclude from processing
    exclude_patterns = [
        "**/.*",  # Hidden files
        "**/__pycache__/**",  # Python cache
        "**/node_modules/**",  # Node modules
        "**/venv/**",  # Virtual environments
        "**/.venv/**",  # Virtual environments
    ]

    processed_files = 0
    total_replacements = 0

    for pattern in patterns:
        for file_path in sdk_dir.glob(pattern):
            # Skip if file matches exclude patterns
            if any(file_path.match(exclude_pattern) for exclude_pattern in exclude_patterns):
                continue

            # Skip if not a file
            if not file_path.is_file():
                continue

            try:
                # Read file content
                content = file_path.read_text(encoding="utf-8")
                original_content = content

                # Apply replacements
                file_replacements = 0
                for old_string, new_string in replacements:
                    if old_string in content:
                        content = content.replace(old_string, new_string)
                        file_replacements += content.count(new_string) - original_content.count(new_string)

                # Write back if changes were made
                if content != original_content:
                    file_path.write_text(content, encoding="utf-8")
                    processed_files += 1
                    total_replacements += file_replacements
                    typer.echo(f"  - Updated {file_path.relative_to(sdk_dir)} ({file_replacements} replacements)")

            except (UnicodeDecodeError, PermissionError) as e:
                # Skip files that can't be read or written
                typer.echo(f"  - Skipped {file_path.relative_to(sdk_dir)} ({e})", err=True)
                continue

    typer.echo(f"  - Processed {processed_files} files with {total_replacements} total replacements")


def update_pyproject_toml(sdk_info: SdkInfo) -> bool:
    """Update pyproject.toml using regex replacements while preserving formatting."""
    pyproject_path = sdk_info.sdk_dir / "pyproject.toml"

    if not pyproject_path.exists():
        typer.echo(f"pyproject.toml not found at {pyproject_path}. Skipping update.")
        return False

    pyproject_str = pyproject_path.read_text(encoding="utf-8")

    pyproject = tomlkit.loads(pyproject_str)
    project = pyproject.get("project", {})

    authors = project["authors"]
    authors.clear()
    authors.append({"name": "NVIDIA Corporation"})

    project["urls"] = {"Homepage": "https://docs.nvidia.com/nemo/microservices/latest/about/index.html"}

    # Drop support for Python versions older than 3.11.
    version_to_remove = ["3.8", "3.9", "3.10"]
    for ver in version_to_remove:
        try:
            project["classifiers"].remove(f"Programming Language :: Python :: {ver}")
        except ValueError:
            pass

    project["requires-python"] = ">= 3.11"
    dependencies = project.get("dependencies")
    if dependencies is not None:
        for dep in list(dependencies):
            if dep.startswith("exceptiongroup"):
                dependencies.remove(dep)
    pyproject["tool"]["ruff"]["target-version"] = "py311"
    pyproject["tool"]["pyright"]["pythonVersion"] = "3.11"

    # Handle versioning
    project.pop("version", None)
    dynamic = project.setdefault("dynamic", [])
    if "version" not in dynamic:
        dynamic.append("version")

    tool = pyproject.setdefault("tool", {})
    hatch_version = tool.setdefault("hatch", {}).setdefault("version", {})
    hatch_version.clear()
    hatch_version["source"] = "nmp-dynamic-versioning"

    tool.pop("uv-dynamic-versioning", None)

    build_requires = pyproject.setdefault("build-system", {}).setdefault("requires", [])
    try:
        build_requires.remove("uv-dynamic-versioning")
    except ValueError:
        pass
    if "nmp-build-tools" not in build_requires:
        build_requires.append("nmp-build-tools")

    # Tweak pytest options
    pytest = pyproject["tool"]["pytest"]["ini_options"]
    pytest_addopts = "-k 'not aiohttp' -Wdefault"
    opts = pytest.get("addopts", "")
    if pytest_addopts not in opts:
        opts += f" {pytest_addopts}"
        pytest["addopts"] = opts.strip()

    # Tweak uv config
    uv_config = pyproject["tool"]["uv"]
    uv_config.pop("conflicts", None)
    uv_config["cache-keys"] = [
        {"file": "pyproject.toml"},
        {"git": {"commit": True, "tags": True}},
    ]
    nmp_build_tools_source = tomlkit.inline_table()
    nmp_build_tools_source["workspace"] = True
    uv_config.setdefault("sources", {})["nmp-build-tools"] = nmp_build_tools_source

    pyproject["dependency-groups"].pop("pydantic-v1", None)

    # Configure wheel build to include only the SDK package (client extensions
    # are vendored into src/nemo_platform/ by `make vendor`).  Runtime/server
    # packages are no longer vendored into the SDK — the wrapper handles bundling.
    hatch_build = pyproject.setdefault("tool", {}).setdefault("hatch", {}).setdefault("build", {})
    wheel_target = hatch_build.setdefault("targets", {}).setdefault("wheel", {})
    wheel_target["packages"] = ["src/nemo_platform"]
    wheel_target["force-include"] = {
        "../../../docs": "nemo_platform/cli/docs",
    }

    # Remove legacy build hook config if present
    wheel_target.pop("hooks", None)

    updated_pyproject_str = tomlkit.dumps(pyproject)

    # Only write if changes were made
    if updated_pyproject_str != pyproject_str:
        pyproject_path.write_text(updated_pyproject_str, encoding="utf-8")
        typer.echo(f"  - Updated {pyproject_path}")
    else:
        typer.echo(f"  - No changes needed for {pyproject_path}")

    return True


def get_license_header(file_type: Literal["python"] = "python") -> str:
    """
    Get the standard SPDX license header for NVIDIA files.
    """
    current_year = datetime.now().year
    license_header = f"""\
SPDX-FileCopyrightText: Copyright (c) {current_year} NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

    # Use a comment style based on the file type
    if file_type == "python":
        header = "\n".join("# " + line for line in license_header.splitlines()) + "\n\n"
    else:
        raise RuntimeError(f"Unsupported license style: {file_type}")

    # Remove trailing whitespace from all lines
    header = "\n".join(line.rstrip(" \t") for line in header.split("\n"))

    return header


def has_license_header(file_content: str) -> bool:
    """Check if file already has a license header."""
    lines = file_content.splitlines()
    if not lines:
        return False

    # Check first few lines for license header patterns
    first_lines = lines[:10]  # Check first 10 lines
    license_patterns = [
        r"SPDX-FileCopyrightText.*NVIDIA",
        r"Copyright.*NVIDIA",
        r"SPDX-License-Identifier",
    ]

    for line in first_lines:
        for pattern in license_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True

    return False


def should_add_license_header(file_path: Path) -> bool:
    """Determine if a file should have a license header added."""
    # Skip certain files
    skip_patterns = [
        "__pycache__",
        ".pyc",
        ".pyo",
        ".pyd",
        ".so",
        ".egg-info",
        ".git",
        ".pytest_cache",
        "node_modules",
        ".venv",
        "venv",
    ]

    # Skip if file path contains any skip patterns
    file_str = str(file_path)
    for pattern in skip_patterns:
        if pattern in file_str:
            return False

    # Only process Python files
    if file_path.suffix != ".py":
        return False

    # Skip certain specific files
    skip_files = []

    # Allow __init__.py files that are not in the root of the SDK
    if file_path.name in skip_files:
        return False

    return True


def add_license_header_to_file(file_path: Path, license_header: str) -> bool:
    """Add license header to a single file. Returns True if header was added."""
    try:
        # Read file content
        content = file_path.read_text(encoding="utf-8")

        # Check if license header already exists
        if has_license_header(content):
            return False

        # Handle shebang lines
        lines = content.splitlines(keepends=True)
        insert_pos = 0

        # If file starts with shebang, insert after it
        if lines and lines[0].startswith("#!"):
            insert_pos = 1
            # Add empty line after shebang if there isn't one
            if len(lines) > 1 and not lines[1].strip() == "":
                license_header += "\n"

        # Insert license header
        if insert_pos < len(lines):
            lines.insert(insert_pos, license_header)
        else:
            lines.append(license_header)

        # Write back to file
        file_path.write_text("".join(lines), encoding="utf-8")
        return True

    except (UnicodeDecodeError, PermissionError) as e:
        typer.echo(f"  - Skipped {file_path} ({e})", err=True)
        return False


def process_license_headers(sdk_dir: Path) -> None:
    """Update license headers in all Python files in the SDK."""
    license_header = get_license_header()

    # File patterns to process
    patterns = ["**/*.py"]

    processed_files = 0
    updated_files = 0
    skipped_files = 0

    for pattern in patterns:
        for file_path in sdk_dir.glob(pattern):
            # Skip if not a file
            if not file_path.is_file():
                continue

            # Skip if file shouldn't have license header
            if not should_add_license_header(file_path):
                continue

            processed_files += 1

            # Add license header
            if add_license_header_to_file(file_path, license_header):
                updated_files += 1
            else:
                skipped_files += 1

    typer.echo(f"  - Processed {processed_files} files")
    typer.echo(f"  - Updated {updated_files} files with license headers")
    typer.echo(f"  - Skipped {skipped_files} files (already had headers)")


@app.command()
def update_readme() -> None:
    """Merge README override files and replace the generated README."""
    sdk_info = get_sdk_info()

    typer.echo("Updating README...")

    # Check if override directory exists
    if not sdk_info.readme_dir.exists():
        typer.echo(f"README override directory not found: {sdk_info.readme_dir}. Skipping override.")
        return

    # Merge README files
    merged_content = merge_readme_files(sdk_info.readme_dir)

    # Write to SDK README
    readme_path = sdk_info.sdk_dir / "README.md"
    readme_path.write_text(merged_content, encoding="utf-8")

    typer.echo(f"  - Updated {readme_path}")
    typer.echo("README update completed!")


@app.command()
def update_pyproject() -> None:
    """Update pyproject.toml with regex replacements."""
    sdk_info = get_sdk_info()

    typer.echo("Updating pyproject.toml...")

    if update_pyproject_toml(sdk_info):
        typer.echo("pyproject.toml update completed!")


@app.command()
def replace_strings() -> None:
    """Apply string replacements to source code files."""
    sdk_info = get_sdk_info()

    typer.echo("Applying string replacements...")

    # Get replacements
    replacements = get_string_replacements()

    if not replacements:
        typer.echo("  - No replacements configured")
        return

    typer.echo(f"  - Applying {len(replacements)} replacement rules")
    for old_string, new_string in replacements:
        typer.echo(f"    '{old_string[:50]}...' -> '{new_string[:50]}...'")

    # Apply replacements
    apply_string_replacements(sdk_info.sdk_dir, replacements)

    typer.echo("String replacements completed!")


@app.command()
def copy_license() -> None:
    """Copy LICENSE file from overrides to SDK directory."""
    sdk_info = get_sdk_info()

    typer.echo("Copying LICENSE file...")

    # Check for override LICENSE first
    override_license = sdk_info.overrides_dir / "LICENSE"

    source_license = None
    if override_license.exists():
        source_license = override_license
        typer.echo(f"  - Using override LICENSE from {override_license}")
    else:
        typer.echo("No LICENSE file found in overrides. Skipping override.")
        return

    # Copy to SDK directory
    dest_license = sdk_info.sdk_dir / "LICENSE"
    shutil.copy2(source_license, dest_license)

    typer.echo(f"  - Copied to {dest_license}")
    typer.echo("LICENSE copy completed!")


@app.command()
def check_stainless_references() -> None:
    """Check for any remaining references to Stainless URLs in the SDK code."""
    sdk_info = get_sdk_info()

    typer.echo("Checking for Stainless references...")

    findings = check_for_stainless_references(sdk_info.sdk_dir)

    if not findings:
        typer.echo("  ✓ No Stainless references found!")
        return

    typer.echo(f"  ✗ Found {len(findings)} Stainless references:")

    # Group findings by file
    files_with_findings = {}
    for file_path, line_num, line_content in findings:
        rel_path = file_path.relative_to(sdk_info.sdk_dir)
        if rel_path not in files_with_findings:
            files_with_findings[rel_path] = []
        files_with_findings[rel_path].append((line_num, line_content))

    # Display findings
    for file_path, file_findings in files_with_findings.items():
        typer.echo(f"\n  {file_path}:")
        for line_num, line_content in file_findings:
            typer.echo(f"    Line {line_num}: {line_content}")

    typer.echo(f"Error: Found {len(findings)} Stainless references that need to be addressed", err=True)
    raise typer.Exit(code=1)


@app.command()
def remove_stats_file() -> None:
    """
    Remove the stats file if it exists.
    Note: This is important, so the changes to the SDK can be merged without conflicts.
    """
    sdk_info = get_sdk_info()

    typer.echo("Removing stats file...")

    stats_file = sdk_info.sdk_dir / ".stats.yml"
    if stats_file.exists():
        stats_file.unlink()
        typer.echo(f"  - Removed {stats_file}")
    else:
        typer.echo(f"  - No stats file found at {stats_file}. Skipping removal.")

    typer.echo("Stats file removal completed!")


@app.command()
def save_nmp_context() -> None:
    """
    Save the inputs used to generate the current version of the SDK.
    This context is used for checking if the SDK is up to date with the main OpenAPI spec and Stainless config.
    """
    sdk_info = get_sdk_info()

    typer.echo("Saving generation context...")

    nmpcontext_dir = sdk_info.sdk_dir / ".nmpcontext"
    nmpcontext_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy(sdk_info.openapi_spec_file, nmpcontext_dir / "openapi.yaml")
    shutil.copy(sdk_info.stainless_config_file, nmpcontext_dir / "stainless.yaml")

    typer.echo(f"  - Copied to {nmpcontext_dir}")


@app.command()
def update_license_headers() -> None:
    """Update license headers in all Python files in the SDK."""
    sdk_info = get_sdk_info()

    typer.echo("Updating license headers in all Python files...")

    process_license_headers(sdk_info.sdk_dir)

    typer.echo("License headers update completed!")


@app.command()
def ensure_api_image_field() -> None:
    """Ensure dynamic version metadata and ``__image_tag__`` are present in ``_version.py``.

    Stainless rewrites ``_version.py`` with a literal version. This command
    restores the dynamic package-metadata lookup and the development default
    image tag field.
    """
    sdk_info = get_sdk_info()

    typer.echo("Ensuring dynamic version metadata in _version.py...")

    version_file = sdk_info.sdk_dir / "src" / sdk_info.module_name / "_version.py"
    content = version_file.read_text(encoding="utf-8")
    expected = sdk_version_file_content(sdk_info.package_name)
    if content == expected:
        typer.echo("  - Dynamic version metadata already present, skipping.")
        return

    version_file.write_text(expected, encoding="utf-8")
    typer.echo(f"  - Updated {version_file}")


@app.command()
def update_all() -> None:
    """Run all updates: README, pyproject.toml, LICENSE, string replacements, and license headers."""
    typer.echo("Running all post-generation updates...")

    # Run all update commands
    update_readme()
    typer.echo()
    update_pyproject()
    typer.echo()
    copy_license()
    typer.echo()
    replace_strings()
    typer.echo()
    update_license_headers()
    typer.echo()
    remove_stats_file()
    typer.echo()
    ensure_api_image_field()
    typer.echo()
    save_nmp_context()
    typer.echo()
    inject_exist_ok()
    typer.echo()

    typer.echo("\nAll post-generation updates completed successfully!")
