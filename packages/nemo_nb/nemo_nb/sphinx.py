# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sphinx extension integration.

Hooks into builder-inited event to convert all .ipynb files to .md
before Sphinx parsing begins.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from sphinx.application import Sphinx

from .converter import NotebookConverter
from .md_to_notebook import MarkdownToNotebookConverter

logger = logging.getLogger(__name__)

# Languages treated as CLI/shell for notebook variant splitting
_CLI_LANGUAGES: frozenset[str] = frozenset({"bash", "sh", "shell"})


def setup(app: Sphinx) -> Dict[str, Any]:
    """Sphinx extension entry point.

    Args:
        app: Sphinx application instance

    Returns:
        Extension metadata dict
    """
    logger.warning("=" * 80)
    logger.warning("NEMO-NB v0.5.0 Extension Loading...")
    logger.warning("Two-stage processing: .md -> .ipynb -> .md")
    logger.warning("=" * 80)

    # Configuration
    app.add_config_value("nemo_nb_config", {}, "html")

    # Hook into config-inited to exclude files BEFORE document discovery
    app.connect("config-inited", exclude_conflicting_files, priority=50)

    # Hook into builder-inited event - TWO-STAGE PROCESSING
    # Stage 0: Exclude unmarked notebooks from Sphinx processing
    app.connect("builder-inited", exclude_unmarked_notebooks, priority=50)
    # Stage 1: Convert marked .md files to .ipynb (intermediate artifacts)
    app.connect("builder-inited", convert_markdown_files, priority=100)
    # Stage 2: Convert .ipynb files to .md (final output for Sphinx)
    app.connect("builder-inited", convert_notebooks, priority=200)

    # Hook into source-read so logical docnames can serve generated content.
    # This allows authors to reference paths like
    # get-started/tutorials/deploy-nims while the heavy generated
    # .sphinx.md files stay under _generated/.
    app.connect("source-read", override_nemo_nb_source)

    # Hook into build-finished to copy .ipynb files to output for downloads
    app.connect("build-finished", copy_notebooks_to_output)

    # Register .ipynb.md as markdown source (optional - for debugging)
    app.add_source_suffix(".ipynb.md", "markdown")
    # Register .ipynb as markdown source so we can intercept it with source-read hook
    app.add_source_suffix(".ipynb", "markdown")

    return {
        "version": "0.5.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }


def should_process_markdown(md_path: Path) -> bool:
    """Check if markdown file should be processed by looking for opt-in marker.

    A markdown file is processed if it contains:
    1. The marker <!-- @nemo-nb: process --> ANYWHERE in the document
    2. Frontmatter field nemo_nb.process: true

    Args:
        md_path: Path to the markdown file

    Returns:
        True if markdown should be processed, False otherwise
    """
    try:
        content = md_path.read_text(encoding="utf-8")

        # Check 1: Look for @nemo-nb: process marker anywhere in document
        if "@nemo-nb: process" in content:
            return True

        # Check 2: Parse frontmatter for nemo_nb.process field
        if content.startswith("---"):
            try:
                # Extract frontmatter (everything between first two --- lines)
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    if isinstance(frontmatter, dict):
                        nemo_nb_config = frontmatter.get("nemo_nb", {})
                        if isinstance(nemo_nb_config, dict):
                            if nemo_nb_config.get("process") is True:
                                return True
            except Exception as e:
                # If frontmatter parsing fails, continue to other checks
                logger.debug(f"Frontmatter parsing failed for {md_path}: {e}")

        return False

    except Exception as e:
        logger.warning(f"Failed to check markdown file {md_path}: {e}")
        return False


def should_process_notebook(notebook_path: Path) -> bool:
    """Check if notebook should be processed by looking for opt-in marker.

    A notebook is processed ONLY if it contains the marker:
    # @nemo-nb: process

    The marker can be in any cell (markdown or code) in the notebook.

    Args:
        notebook_path: Path to the notebook file

    Returns:
        True if notebook should be processed, False otherwise
    """
    try:
        with open(notebook_path, "r", encoding="utf-8") as f:
            notebook = json.load(f)

        # Search all cells for the process marker
        for cell in notebook.get("cells", []):
            source = cell.get("source", [])

            # Handle both list and string source formats
            if isinstance(source, list):
                source_text = "".join(source)
            else:
                source_text = source

            # Check for opt-in marker
            if "@nemo-nb: process" in source_text:
                return True

        return False

    except Exception as e:
        logger.warning(f"Failed to check notebook {notebook_path}: {e}")
        return False


def exclude_conflicting_files(app: Sphinx, config) -> None:
    """Exclude .md files when corresponding .ipynb exists to avoid 'multiple files found' warnings.

    Called during config-inited event (before document discovery).
    Scans for .md/.ipynb pairs and excludes the .md file if both have markers,
    prioritizing the .ipynb file.

    Args:
        app: Sphinx application instance
        config: Sphinx config object
    """
    srcdir = Path(app.srcdir)
    excluded_count = 0

    # Find all .ipynb files in source directory
    for notebook_path in srcdir.rglob("*.ipynb"):
        # Skip checkpoint directories and generated files
        if ".ipynb_checkpoints" in str(notebook_path) or "_generated" in str(notebook_path):
            continue

        # Check if notebook has the process marker
        if should_process_notebook(notebook_path):
            # Check if there's a corresponding .md file
            md_path = notebook_path.with_suffix(".md")
            if md_path.exists():
                # Exclude the .md file to avoid "multiple files found" warning
                rel_md_path = md_path.relative_to(srcdir).as_posix()
                if rel_md_path not in config.exclude_patterns:
                    config.exclude_patterns.append(rel_md_path)
                    excluded_count += 1
                    logger.info(f"Excluding {rel_md_path} (corresponding .ipynb has process marker)")

    if excluded_count > 0:
        logger.info(f"NeMo-NB: Excluded {excluded_count} .md file(s) to avoid 'multiple files found' warnings")


def exclude_unmarked_notebooks(app: Sphinx) -> None:
    """Exclude notebooks without the @nemo-nb: process marker from Sphinx.

    Called during builder-inited event (Stage 0, before conversion).
    Scans all .ipynb files in the source directory and adds those without
    the opt-in marker to Sphinx's exclude_patterns. This prevents Sphinx
    from treating unmarked notebooks as documents.

    Args:
        app: Sphinx application instance
    """
    logger.warning("=" * 80)
    logger.warning("NEMO-NB: Stage 0 - exclude_unmarked_notebooks() called")
    logger.warning("=" * 80)
    srcdir = Path(app.env.srcdir)

    # Track exclusion count for logging
    excluded_count = 0

    # Find all .ipynb files in source directory
    for notebook_path in srcdir.rglob("*.ipynb"):
        # Skip checkpoint directories
        if ".ipynb_checkpoints" in str(notebook_path):
            continue

        # Skip notebooks in _generated directory (they will be handled separately)
        if "_generated" in str(notebook_path):
            continue

        # Check if notebook has opt-in marker
        if not should_process_notebook(notebook_path):
            # Add to exclude_patterns to prevent Sphinx from processing it
            rel_path = notebook_path.relative_to(srcdir).as_posix()
            if rel_path not in app.config.exclude_patterns:
                app.config.exclude_patterns.append(rel_path)
                excluded_count += 1
                logger.debug(f"Excluding unmarked notebook: {rel_path}")

    if excluded_count > 0:
        logger.info(f"NeMo-NB Stage 0: Excluded {excluded_count} unmarked notebook(s)")


def convert_markdown_files(app: Sphinx) -> None:
    """Convert opted-in .md files to .ipynb during initialization.

    Called during builder-inited event (Stage 1 of two-stage processing).
    Finds all markdown files in the source directory that contain the
    opt-in marker and converts them to notebooks.

    Markdown files MUST contain this marker to be processed:
        <!-- @nemo-nb: process -->

    The generated .ipynb files are written to _generated/nemo-nb/ only.

    Args:
        app: Sphinx application instance
    """
    logger.warning("=" * 80)
    logger.warning("NEMO-NB: Stage 1 - convert_markdown_files() called")
    logger.warning("=" * 80)
    srcdir = Path(app.env.srcdir)
    converter = MarkdownToNotebookConverter()

    # Create build directory for generated files
    # Use _generated directory to avoid Sphinx's exclude_patterns for _build
    build_base = srcdir / "_generated"
    build_dir = build_base / "nemo-nb"
    build_dir.mkdir(parents=True, exist_ok=True)

    # Track conversion count and generated notebooks
    converted_count = 0
    skipped_count = 0
    generated_notebooks = set()

    # Find all markdown files
    for md_path in srcdir.rglob("*.md"):
        # Check if markdown has opt-in marker
        if not should_process_markdown(md_path):
            skipped_count += 1
            logger.debug(f"Skipping markdown (no opt-in marker): {md_path.relative_to(srcdir)}")
            continue

        # Check for conflict: both .md and .ipynb with same name
        ipynb_path = md_path.with_suffix(".ipynb")
        if ipynb_path.exists() and should_process_notebook(ipynb_path):
            raise RuntimeError(
                f"Conflict detected: Both {md_path.relative_to(srcdir)} and {ipynb_path.relative_to(srcdir)} "
                "exist and are marked for processing by nemo-nb. "
                "This creates a collision for the generated output. "
                "Please rename one of them or remove the process marker from one."
            )

        try:
            # Generate output path in build directory
            rel_path = md_path.relative_to(srcdir)
            build_ipynb_path = build_dir / rel_path.with_suffix(".ipynb")

            # Skip if notebook exists and is newer than source markdown
            if build_ipynb_path.exists():
                source_mtime = md_path.stat().st_mtime
                cached_mtime = build_ipynb_path.stat().st_mtime
                if cached_mtime >= source_mtime:
                    logger.debug(
                        f"Skipping markdown conversion (cached notebook is up-to-date): "
                        f"{md_path.relative_to(srcdir)} -> {build_ipynb_path.name}"
                    )
                    skipped_count += 1
                    # Still track this as a generated notebook for Stage 2
                    generated_notebooks.add(build_ipynb_path)
                    continue
                else:
                    logger.info(f"Source is newer, regenerating: {md_path.relative_to(srcdir)}")

            # Convert markdown to notebook
            notebook_dict = converter.convert(md_path)

            # Write .ipynb file only to build directory
            rel_path = md_path.relative_to(srcdir)
            build_ipynb_path = build_dir / rel_path.with_suffix(".ipynb")
            build_ipynb_path.parent.mkdir(parents=True, exist_ok=True)
            with open(build_ipynb_path, "w", encoding="utf-8") as f:
                json.dump(notebook_dict, f, indent=1)

            generated_notebooks.add(build_ipynb_path)
            converted_count += 1
            logger.info(f"Converted markdown -> notebook: {md_path.relative_to(srcdir)}")
            logger.debug(f"  Generated notebook: {build_ipynb_path.relative_to(build_base)}")

        except Exception as e:
            logger.warning(f"Failed to convert markdown {md_path}: {e}")

    if converted_count > 0:
        logger.info(f"NeMo-NB Stage 1: Converted {converted_count} markdown file(s) to notebooks")
        logger.info(f"NeMo-NB Stage 1: Build copies available in {build_dir.relative_to(build_base.parent)}")
    if skipped_count > 0:
        logger.info(f"NeMo-NB Stage 1: Skipped {skipped_count} markdown file(s)")

    # Store generated notebooks in app config for Stage 2
    if not hasattr(app, "nemo_nb_generated_notebooks"):
        setattr(app, "nemo_nb_generated_notebooks", set())
    app.nemo_nb_generated_notebooks.update(generated_notebooks)  # type: ignore[attr-defined]


def convert_notebooks(app: Sphinx) -> None:
    """Convert opted-in .ipynb files to .sphinx.md during initialization.

    Called during builder-inited event. Finds all notebooks in:
    1. Source directory (srcdir) - notebooks authored directly as .ipynb
    2. _generated/nemo-nb/ directory - notebooks generated by Stage 1 from .md files

    Notebooks MUST contain this marker to be processed:
        # @nemo-nb: process
        or
        <!-- @nemo-nb: process -->

    All generated .sphinx.md files are written to _generated/nemo-nb/ maintaining
    the relative path structure from the source directory.

    Args:
        app: Sphinx application instance
    """
    logger = logging.getLogger(__name__)
    logger.warning("=" * 80)
    logger.warning("NEMO-NB: Stage 2 - convert_notebooks() called")
    logger.warning("=" * 80)
    srcdir = Path(app.env.srcdir)
    config = app.config.nemo_nb_config
    converter = NotebookConverter(config)

    # Create build directory for converted files
    # Use _generated directory to avoid Sphinx's exclude_patterns for _build
    build_base = srcdir / "_generated"
    build_dir = build_base / "nemo-nb"
    build_dir.mkdir(parents=True, exist_ok=True)

    # Track conversion count for logging
    converted_count = 0
    skipped_count = 0

    # Ensure we have a place to store docname -> generated file mappings
    if not hasattr(app, "_nemo_nb_doc_aliases"):
        setattr(app, "_nemo_nb_doc_aliases", {})

    # Track processed source notebooks to check for conflicts with generated ones
    processed_source_notebooks = set()

    # Process notebooks from two sources:
    # 1. Source directory (direct .ipynb files)
    # 2. Build directory (generated from .md files in Stage 1)

    # FIRST: Process notebooks in source directory
    logger.info("Processing .ipynb files from source directory...")
    for notebook_path in srcdir.rglob("*.ipynb"):
        # Skip checkpoint directories
        if ".ipynb_checkpoints" in str(notebook_path):
            continue

        # Skip notebooks that live under the build directory; they are handled
        # in the second pass below. This prevents nested paths like
        # _generated/nemo-nb/_generated/nemo-nb/...
        try:
            _ = notebook_path.relative_to(build_dir)
        except ValueError:
            pass
        else:
            logger.debug(
                "Skipping srcdir notebook in build_dir (will be handled in second pass): "
                f"{notebook_path.relative_to(srcdir)}"
            )
            continue

        # Check if notebook has opt-in marker
        if not should_process_notebook(notebook_path):
            skipped_count += 1
            logger.debug(f"Skipping srcdir notebook (no opt-in marker): {notebook_path.relative_to(srcdir)}")
            continue

        try:
            # Check output path for staleness
            rel_path = notebook_path.relative_to(srcdir)
            build_md_path = build_dir / rel_path.with_suffix(".sphinx.md")

            # Skip if generated .sphinx.md exists and is newer than source notebook
            if build_md_path.exists():
                source_mtime = notebook_path.stat().st_mtime
                cached_mtime = build_md_path.stat().st_mtime
                if cached_mtime >= source_mtime:
                    logger.debug(
                        f"Skipping srcdir notebook conversion (cached .sphinx.md is up-to-date): "
                        f"{notebook_path.relative_to(srcdir)}"
                    )
                    skipped_count += 1
                    # Still register the alias
                    logical_docname = rel_path.with_suffix("").as_posix()
                    rel_generated_md = build_md_path.relative_to(srcdir).as_posix()
                    getattr(app, "_nemo_nb_doc_aliases")[logical_docname] = rel_generated_md
                    processed_source_notebooks.add(rel_path)
                    continue
                else:
                    logger.info(f"Source notebook is newer, regenerating: {notebook_path.relative_to(srcdir)}")

            # Expand {include} directives before converting so that generated
            # .sphinx.md paths resolve correctly — the generated file lives
            # under _generated/nemo-nb/ where relative include paths (e.g.
            # ../../_snippets/...) would not resolve.
            nb = json.loads(notebook_path.read_text())
            nb = expand_include_directives(nb, notebook_path)
            md_content = converter.convert_from_dict(nb, notebook_path)

            # Write .md file to build directory with relative path structure
            build_md_path.parent.mkdir(parents=True, exist_ok=True)
            build_md_path.write_text(md_content, encoding="utf-8")

            # Register alias so source-read hook can serve the generated content
            # This allows Sphinx to "read" the .ipynb file but actually process
            # the converted markdown content.
            logical_docname = rel_path.with_suffix("").as_posix()
            rel_generated_md = build_md_path.relative_to(srcdir).as_posix()
            getattr(app, "_nemo_nb_doc_aliases")[logical_docname] = rel_generated_md

            processed_source_notebooks.add(rel_path)

            converted_count += 1
            logger.info(f"Converted srcdir notebook -> markdown: {notebook_path.relative_to(srcdir)}")
            logger.info(f"  Generated: {build_md_path.relative_to(build_base)}")

        except Exception as e:
            logger.warning(f"Failed to convert srcdir notebook {notebook_path}: {e}")

    # SECOND: Process notebooks in build directory (generated by Stage 1)
    logger.info("Processing .ipynb files from build directory...")
    for notebook_path in build_dir.rglob("*.ipynb"):
        # Skip checkpoint directories
        if ".ipynb_checkpoints" in str(notebook_path):
            continue

        # Check for conflict with processed source notebook
        try:
            rel_ipynb = notebook_path.relative_to(build_dir)
            if rel_ipynb in processed_source_notebooks:
                raise RuntimeError(
                    f"Conflict detected: Both {rel_ipynb.with_suffix('.md')} and {rel_ipynb} "
                    "exist in the source directory and are marked for processing by nemo-nb. "
                    "This creates a collision for the generated output. "
                    "Please rename one of them or remove the process marker."
                )
        except ValueError:
            # Should not happen as we are iterating over build_dir
            pass

        # Check if notebook has opt-in marker
        if not should_process_notebook(notebook_path):
            skipped_count += 1
            logger.debug(f"Skipping build notebook (no opt-in marker): {notebook_path.relative_to(build_dir)}")
            continue

        try:
            # Check output path for staleness
            build_md_path = notebook_path.with_suffix(".sphinx.md")

            # Get relative path for aliasing
            try:
                rel_ipynb = notebook_path.relative_to(build_dir)
            except ValueError:
                rel_ipynb = None

            # Skip if generated .sphinx.md exists and is newer than source notebook
            if build_md_path.exists():
                source_mtime = notebook_path.stat().st_mtime
                cached_mtime = build_md_path.stat().st_mtime
                if cached_mtime >= source_mtime:
                    logger.debug(
                        f"Skipping build notebook conversion (cached .sphinx.md is up-to-date): "
                        f"{notebook_path.relative_to(build_dir)}"
                    )
                    skipped_count += 1
                    # Still register the alias
                    if rel_ipynb is not None:
                        logical_docname = rel_ipynb.with_suffix("").as_posix()
                        rel_generated_md = build_md_path.relative_to(srcdir).as_posix()
                        getattr(app, "_nemo_nb_doc_aliases")[logical_docname] = rel_generated_md
                    continue
                else:
                    logger.info(f"Source notebook is newer, regenerating: {notebook_path.relative_to(build_dir)}")

            # Expand {include} directives before converting. Include paths
            # in the source are written relative to the original source file
            # location, not the generated notebook under _generated/nemo-nb/.
            source_equiv_path = srcdir / notebook_path.relative_to(build_dir)
            nb = json.loads(notebook_path.read_text())
            nb = expand_include_directives(nb, source_equiv_path)
            md_content = converter.convert_from_dict(nb, notebook_path)

            # Write .md file to build directory with .sphinx.md suffix
            build_md_path.write_text(md_content, encoding="utf-8")

            # If this notebook was generated from a markdown source, record
            # an alias so the original logical docname can serve this
            # generated content.
            if rel_ipynb is not None:
                logical_docname = rel_ipynb.with_suffix("").as_posix()
                rel_generated_md = build_md_path.relative_to(srcdir).as_posix()
                getattr(app, "_nemo_nb_doc_aliases")[logical_docname] = rel_generated_md

            converted_count += 1
            logger.info(f"Converted build notebook -> markdown: {notebook_path.relative_to(build_dir)}")
            logger.debug(f"  Generated: {build_md_path.relative_to(build_base)}")

        except Exception as e:
            logger.warning(f"Failed to convert build notebook {notebook_path}: {e}")

    if converted_count > 0:
        logger.info(f"NeMo-NB Stage 2: Converted {converted_count} notebook(s) to markdown")
    if skipped_count > 0:
        logger.info(f"NeMo-NB Stage 2: Skipped {skipped_count} notebook(s) (no opt-in marker)")


def override_nemo_nb_source(app: Sphinx, docname: str, source: list[str]) -> None:
    """Override Sphinx source for docs with nemo-nb generated aliases.

    For any docname that corresponds to a markdown file processed by
    nemo-nb (for example, ``get-started/tutorials/deploy-nims``), this
    handler replaces the document source with the contents of the
    generated ``.sphinx.md`` file under ``_generated/nemo-nb``.

    This lets authors reference logical paths in toctrees and links while
    keeping large generated artifacts under ``_generated/`` only.
    """

    aliases = getattr(app, "_nemo_nb_doc_aliases", {})
    generated_rel = aliases.get(docname)
    if not generated_rel:
        return

    srcdir = Path(app.env.srcdir)
    generated_path = srcdir / generated_rel

    try:
        new_source = generated_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(
            "nemo-nb alias target missing for %s -> %s",
            docname,
            generated_path,
        )
        return

    # Sphinx expects source to be a single-item list of the document text
    if source:
        source[0] = new_source
    else:
        source.append(new_source)


def strip_hidden_cells_from_notebook(notebook_dict: dict) -> dict:
    """Remove cells marked with hide from a notebook dictionary.

    Removes cells that have:
    - @nemo-nb: hide marker in the cell content
    - metadata.nemo_nb.hide = true
    - "hide-cell" in metadata.tags

    Args:
        notebook_dict: Notebook dictionary to process

    Returns:
        Modified notebook dictionary with hidden cells removed
    """
    from .markers import CommandInterpreter, MarkerParser
    from .structures import CellMetadata

    parser = MarkerParser()
    interpreter = CommandInterpreter()

    filtered_cells = []

    for cell in notebook_dict.get("cells", []):
        # Get cell content and type
        cell_content = "".join(cell.get("source", []))
        cell_type = cell.get("cell_type", "")

        # Parse markers from cell content
        _, commands = parser.parse_cell(cell_content, cell_type)

        # Check metadata
        meta = CellMetadata(cell)

        # Skip cells that should be hidden
        if meta.should_hide() or interpreter.should_hide(commands):
            continue

        # Keep this cell
        filtered_cells.append(cell)

    # Return notebook with filtered cells
    result = notebook_dict.copy()
    result["cells"] = filtered_cells
    return result


def add_bash_magic_to_shell_cells(notebook_dict: dict) -> dict:
    """Add %%bash magic to shell cells that don't already have it.

    This ensures shell cells are executable in Jupyter without requiring
    the user to manually add the magic command.

    Args:
        notebook_dict: Notebook dictionary to process

    Returns:
        Modified notebook dictionary with %%bash magic added to shell cells
    """
    for cell in notebook_dict.get("cells", []):
        if cell.get("cell_type") != "code":
            continue

        # Check if this is a shell cell by looking at metadata
        metadata = cell.get("metadata", {})
        language = metadata.get("language", "")

        if language not in _CLI_LANGUAGES:
            continue

        # Get source as list
        source = cell.get("source", [])
        if not source:
            continue

        # Check if %%bash magic is already present
        first_line = source[0] if isinstance(source, list) else (source.splitlines()[0] if source else "")
        if first_line.strip().startswith("%%bash"):
            continue

        # Add %%bash magic at the beginning
        if isinstance(source, list):
            cell["source"] = ["%%bash\n", *source]
        else:
            cell["source"] = "%%bash\n" + source

    return notebook_dict


def get_cell_language(cell: dict) -> str:
    """Get normalized language from a notebook cell.

    Args:
        cell: Notebook cell dictionary

    Returns:
        Language identifier ("python", "sh", "bash", "shell", "markdown")
    """
    from .structures import CellMetadata

    # Non-code cells are treated as markdown
    if cell.get("cell_type") != "code":
        return "markdown"

    # Use CellMetadata to get standardized language
    meta = CellMetadata(cell)
    return meta.get_language()


def normalize_language_for_variant(language: str) -> str:
    """Map languages to variant categories: "python" or "cli".

    Args:
        language: Language identifier from get_cell_language()

    Returns:
        Variant category ("python" or "cli")
    """
    if language in _CLI_LANGUAGES:
        return "cli"
    return "python"


def count_code_cells_by_language(notebook_dict: dict) -> dict[str, int]:
    """Count code cells by language for validation.

    Args:
        notebook_dict: Notebook dictionary

    Returns:
        Dictionary mapping language to count (e.g., {"python": 5, "bash": 3})
    """
    counts: dict[str, int] = {}

    for cell in notebook_dict.get("cells", []):
        language = get_cell_language(cell)
        # Only count code cells (not markdown)
        if language != "markdown":
            counts[language] = counts.get(language, 0) + 1

    return counts


def filter_notebook_by_languages(notebook_dict: dict, keep_languages: set[str]) -> dict:
    """Filter notebook cells to keep only specified languages plus all markdown.

    Args:
        notebook_dict: Notebook dictionary to filter
        keep_languages: Set of languages to keep (e.g., {"python"})

    Returns:
        New notebook dictionary with filtered cells (immutable pattern)
    """
    filtered_cells = []

    for cell in notebook_dict.get("cells", []):
        language = get_cell_language(cell)

        # Always keep markdown cells
        if language == "markdown":
            filtered_cells.append(cell)
            continue

        # Keep code cells matching the language filter
        if language in keep_languages:
            filtered_cells.append(cell)

    # Return new dictionary with filtered cells
    result = notebook_dict.copy()
    result["cells"] = filtered_cells
    return result


def expand_include_directives(notebook_dict: dict, notebook_path: Path) -> dict:
    """Expand {include} directives by inserting the actual file content.

    Args:
        notebook_dict: Notebook dictionary to process
        notebook_path: Path to the notebook file (used to resolve relative includes)

    Returns:
        Modified notebook dictionary with {include} directives expanded
    """
    # Pattern to match {include} directives
    include_pattern = re.compile(r"^```\{include\}\s+(.+?)\s*$", re.MULTILINE)

    processed_cells = []

    for cell in notebook_dict.get("cells", []):
        # Only process markdown cells
        if cell.get("cell_type") != "markdown":
            processed_cells.append(cell)
            continue

        # Get source
        source = cell.get("source", [])
        if not source:
            processed_cells.append(cell)
            continue

        # Convert to string for processing
        if isinstance(source, list):
            content = "".join(source)
        else:
            content = source

        # Find all {include} directives
        matches = list(include_pattern.finditer(content))
        if not matches:
            processed_cells.append(cell)
            continue

        # Process includes in reverse order to maintain string positions
        for match in reversed(matches):
            include_path_str = match.group(1).strip()

            # Resolve the include path relative to the notebook
            notebook_dir = notebook_path.parent
            include_path = notebook_dir / include_path_str

            # Read the included file (only I/O errors are caught here)
            if not include_path.exists():
                logger.warning(f"Include file not found: {include_path} (from {notebook_path.name})")
                continue
            try:
                with open(include_path, "r", encoding="utf-8") as f:
                    included_content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to read include file {include_path}: {e}")
                continue

            # Replace the directive (including the surrounding code fence) with the content
            # Find the full directive block: ```{include} path\n```
            directive_start = match.start()
            directive_end = match.end()

            # Look for the closing ``` after the directive
            close_fence_match = re.search(r"\n```\s*\n?", content[directive_end:])
            if close_fence_match:
                directive_end += close_fence_match.end()

            # Replace directive with included content
            content = content[:directive_start] + included_content + content[directive_end:]

        # Track if source was originally a multi-item list
        is_multi_item_list = isinstance(source, list) and len(source) > 1

        # Convert back to appropriate format
        if is_multi_item_list:
            processed_source = content.splitlines(keepends=True)
        else:
            processed_source = [content] if content else []

        # Update cell
        processed_cell = cell.copy()
        processed_cell["source"] = processed_source
        processed_cells.append(processed_cell)

    # Return notebook with processed cells
    result = notebook_dict.copy()
    result["cells"] = processed_cells
    return result


def split_code_fences_in_markdown_cells(notebook_dict: dict) -> dict:
    """Promote backtick-fenced code blocks inside markdown cells to real code cells.

    After {include} expansion the included code blocks may be embedded as text
    inside an existing markdown cell.  This function extracts them so the
    download variant logic can filter by language and the cells are executable.

    Only fences of the form ```lang (no curly braces) are promoted.
    Directive fences (```{directive}) are left as-is.

    Args:
        notebook_dict: Notebook dictionary to process

    Returns:
        New notebook dictionary with code blocks extracted into code cells
    """
    # Match opening code fence: ```lang or ````lang (no directive {)
    code_fence_open_re = re.compile(r"^(`{3,})([a-zA-Z]\w*)\s*$", re.MULTILINE)

    new_cells: list[dict] = []

    for cell in notebook_dict.get("cells", []):
        if cell.get("cell_type") != "markdown":
            new_cells.append(cell)
            continue

        source = cell.get("source", [])
        content = "".join(source) if isinstance(source, list) else source

        # Quick check: does this cell contain any promotable code fences?
        if not code_fence_open_re.search(content):
            new_cells.append(cell)
            continue

        # Parse into (cell_type, language, raw_lines) segments
        lines = content.splitlines(keepends=True)
        segments: list[tuple[str, str, list[str]]] = []
        current: list[str] = []
        in_code = False
        fence_marker = ""
        code_lang = ""

        for line in lines:
            stripped = line.rstrip()
            if not in_code:
                m = code_fence_open_re.match(stripped)
                if m:
                    if current:
                        segments.append(("markdown", "", current))
                        current = []
                    fence_marker = m.group(1)
                    code_lang = m.group(2)
                    in_code = True
                else:
                    current.append(line)
            else:
                if stripped == fence_marker:
                    segments.append(("code", code_lang, current))
                    current = []
                    in_code = False
                    fence_marker = ""
                    code_lang = ""
                else:
                    current.append(line)

        if current:
            segments.append(("code" if in_code else "markdown", code_lang, current))

        for seg_type, seg_lang, seg_lines in segments:
            seg_text = "".join(seg_lines).strip()
            if not seg_text:
                continue
            seg_source = seg_text.splitlines(keepends=True)
            if seg_source and not seg_source[-1].endswith("\n"):
                seg_source[-1] += "\n"

            if seg_type == "markdown":
                new_cells.append(
                    {
                        "cell_type": "markdown",
                        "metadata": cell.get("metadata", {}),
                        "source": seg_source,
                    }
                )
            else:
                new_cells.append(
                    {
                        "cell_type": "code",
                        "metadata": {"language": seg_lang},
                        "source": seg_source,
                        "outputs": [],
                        "execution_count": None,
                    }
                )

    result = notebook_dict.copy()
    result["cells"] = new_cells
    return result


def strip_myst_directives_from_notebook(notebook_dict: dict) -> dict:
    """Remove MyST directive syntax from markdown cells in notebooks.

    Removes MyST syntax like tab-sets, sync tags, and empty directive markers
    to clean up downloaded notebooks for better Jupyter experience.

    Args:
        notebook_dict: Notebook dictionary to process

    Returns:
        Modified notebook dictionary with MyST directives removed
    """
    # Patterns to remove from markdown cells
    # NOTE: Only remove tab-set related directives and sync tags.
    # Do NOT remove content directives like {include}, {tip}, {note} - these should
    # be expanded during Sphinx build, not stripped here.
    patterns = [
        r"^:::+\s*$",  # Directive closings (:::, ::::, etc.)
        r"^:::+\{[^}]+\}.*$",  # Directive openings (:::{tab-set}, :::{tab-item}, etc.)
        r"^:sync:\s*\w+\s*$",  # Sync tags (:sync: cli, :sync: python-sdk)
        r"^:[\w-]+:\s*.*$",  # Other option tags (:class:, :name:, etc.)
    ]

    compiled_patterns = [re.compile(pattern, re.MULTILINE) for pattern in patterns]

    filtered_cells = []

    for cell in notebook_dict.get("cells", []):
        # Only process markdown cells
        if cell.get("cell_type") != "markdown":
            filtered_cells.append(cell)
            continue

        # Get source as list of lines
        source = cell.get("source", [])
        if not source:
            continue

        # Track if source was originally a multi-item list
        is_multi_item_list = isinstance(source, list) and len(source) > 1

        # Convert to string for processing
        if isinstance(source, list):
            content = "".join(source)
        else:
            content = source

        # Apply all patterns to remove MyST syntax
        for pattern in compiled_patterns:
            content = pattern.sub("", content)

        # Remove leading/trailing blank lines
        cleaned = content.strip()

        # Only keep cell if it has content after cleaning
        if cleaned:
            # Convert back to appropriate format based on original structure
            if is_multi_item_list:
                # Preserve original line boundaries for multi-item lists
                cleaned_source = cleaned.splitlines(keepends=True)
            else:
                # Keep simple single-item behavior for single-item lists or strings
                cleaned_source = [cleaned]

            # Update cell with cleaned source
            cleaned_cell = cell.copy()
            cleaned_cell["source"] = cleaned_source
            filtered_cells.append(cleaned_cell)

    # Return notebook with filtered cells
    result = notebook_dict.copy()
    result["cells"] = filtered_cells
    return result


def _should_split_notebook(notebook_dict: dict) -> bool:
    """Check if notebook should be split into language variants.

    Scans all cells for download marker with split option.

    Args:
        notebook_dict: Notebook dictionary to check

    Returns:
        True if any cell has <!-- @nemo-nb: download split -->
    """
    from .markers import CommandInterpreter, MarkerParser

    parser = MarkerParser()
    interpreter = CommandInterpreter()

    for cell in notebook_dict.get("cells", []):
        # Get cell content and type
        cell_content = "".join(cell.get("source", []))
        cell_type = cell.get("cell_type", "")

        # Parse markers from cell content
        _, commands = parser.parse_cell(cell_content, cell_type)

        # Check if split option is present
        if interpreter.has_download_split(commands):
            return True

    return False


def _process_notebook_variant(
    notebook_dict: dict,
    base_output_path: Path,
    variant_suffix: str,
    keep_languages: set[str],
    is_cli_variant: bool = False,
) -> tuple[Path, int, int]:
    """Process and write a notebook variant filtered by language.

    Args:
        notebook_dict: Source notebook dictionary (already has hidden cells stripped and includes expanded)
        base_output_path: Base output path (e.g., /output/tutorial.ipynb)
        variant_suffix: Suffix to add to filename (e.g., "-python" or "-cli")
        keep_languages: Set of languages to keep in this variant
        is_cli_variant: Whether this is the CLI variant (adds %%bash magic)

    Returns:
        Tuple of (written_path, original_cell_count, filtered_cell_count)
    """
    import json

    # Filter cells by language
    filtered_dict = filter_notebook_by_languages(notebook_dict, keep_languages)

    # Strip MyST directive syntax from markdown cells
    filtered_dict = strip_myst_directives_from_notebook(filtered_dict)

    # Add bash magic to shell cells for CLI variant
    if is_cli_variant:
        filtered_dict = add_bash_magic_to_shell_cells(filtered_dict)

    # Calculate output path with suffix
    # For index.ipynb, the base_output_path already has the parent dir name
    stem = base_output_path.stem
    output_path = base_output_path.parent / f"{stem}{variant_suffix}.ipynb"

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the variant
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(filtered_dict, f, indent=1)

    # Return stats
    original_count = len(notebook_dict.get("cells", []))
    filtered_count = len(filtered_dict.get("cells", []))

    return output_path, original_count, filtered_count


def copy_notebooks_to_output(app: Sphinx, exception: Exception | None) -> None:
    """Copy .ipynb files to HTML output for download links.

    Called after Sphinx build is finished. Copies .ipynb files from:
    1. Source directory (directly authored .ipynb files)
    2. _generated/nemo-nb/ (notebooks generated from .md files)

    Files are copied to the corresponding location in the HTML output
    directory so they can be downloaded via the links generated by the
    download marker.

    IMPORTANT: Strips cells marked with 'hide' before copying to prevent
    leaking secrets/internal endpoints in downloadable notebooks.

    Args:
        app: Sphinx application instance
        exception: Exception if build failed, None otherwise
    """
    # Only copy if build succeeded and we're building HTML
    if exception is not None:
        return
    if app.builder.name not in ("html", "dirhtml"):
        return

    srcdir = Path(app.env.srcdir)
    outdir = Path(app.builder.outdir)
    build_dir = srcdir / "_generated" / "nemo-nb"

    # Track copy count for logging
    copied_count = 0
    stripped_cells_count = 0
    processed_paths = set()  # Track processed paths to avoid duplicates

    # FIRST: Copy notebooks from source directory (directly authored .ipynb files)
    logger.info("Copying source .ipynb files to output for downloads...")
    for notebook_path in srcdir.rglob("*.ipynb"):
        # Skip checkpoint directories
        if ".ipynb_checkpoints" in str(notebook_path):
            continue

        # Skip notebooks in build directory (handled in second pass)
        try:
            _ = notebook_path.relative_to(build_dir)
        except ValueError:
            pass
        else:
            continue

        # Skip notebooks that were previously copied to the output directory.
        # outdir (_build/html/) lives inside srcdir, so rglob would otherwise
        # find already-copied notebooks on subsequent builds, causing the output
        # path to nest (_build/html/_build/html/...) and the variant suffix to
        # accumulate (tutorial-python-python-python...).
        try:
            _ = notebook_path.relative_to(outdir)
        except ValueError:
            pass
        else:
            continue

        # Only process notebooks that have the process marker
        if not should_process_notebook(notebook_path):
            continue

        try:
            # Read the notebook
            with open(notebook_path, "r", encoding="utf-8") as f:
                notebook_dict = json.load(f)

            # Count cells before stripping
            original_cell_count = len(notebook_dict.get("cells", []))

            # Strip hidden cells to prevent leaking secrets
            notebook_dict = strip_hidden_cells_from_notebook(notebook_dict)

            # Count cells after stripping
            filtered_cell_count = len(notebook_dict.get("cells", []))
            cells_removed = original_cell_count - filtered_cell_count

            if cells_removed > 0:
                stripped_cells_count += cells_removed
                logger.info(f"Stripped {cells_removed} hidden cell(s) from {notebook_path.name}")

            # Expand {include} directives to show actual content
            notebook_dict = expand_include_directives(notebook_dict, notebook_path)

            # Promote code fences that landed inside markdown cells (e.g. from
            # {include} expansion) into proper code cells so they are filterable
            # by language and executable in Jupyter.
            notebook_dict = split_code_fences_in_markdown_cells(notebook_dict)

            # Get relative path from srcdir
            rel_path = notebook_path.relative_to(srcdir)

            # Determine base output path maintaining directory structure
            base_output_path = outdir / rel_path

            # Check if notebook should be split into language variants
            if _should_split_notebook(notebook_dict):
                # Count code cells by language
                lang_counts = count_code_cells_by_language(notebook_dict)

                # Create Python variant if has Python cells
                if lang_counts.get("python", 0) > 0:
                    variant_path, orig_count, filt_count = _process_notebook_variant(
                        notebook_dict,
                        base_output_path,
                        "-python",
                        {"python"},
                        is_cli_variant=False,
                    )
                    processed_paths.add(variant_path.relative_to(outdir))
                    copied_count += 1
                    logger.debug(
                        f"Created Python variant for {notebook_path.name}: {filt_count} cells (from {orig_count} total)"
                    )

                # Create CLI variant if has bash/sh/shell cells
                cli_count = sum(lang_counts.get(lang, 0) for lang in ["bash", "sh", "shell"])
                if cli_count > 0:
                    variant_path, orig_count, filt_count = _process_notebook_variant(
                        notebook_dict,
                        base_output_path,
                        "-cli",
                        {"bash", "sh", "shell"},
                        is_cli_variant=True,
                    )
                    processed_paths.add(variant_path.relative_to(outdir))
                    copied_count += 1
                    logger.debug(
                        f"Created CLI variant for {notebook_path.name}: {filt_count} cells (from {orig_count} total)"
                    )

                # Skip writing main notebook (variants were created instead)
                if lang_counts.get("python", 0) == 0 and cli_count == 0:
                    logger.warning(
                        f"Notebook {notebook_path.name} has split marker but no code cells - no variants created"
                    )

            else:
                # Standard processing: single notebook (backward compatible)
                # Strip MyST directive syntax from markdown cells
                notebook_dict = strip_myst_directives_from_notebook(notebook_dict)

                # Add %%bash magic to shell cells for Jupyter execution
                notebook_dict = add_bash_magic_to_shell_cells(notebook_dict)

                base_output_path.parent.mkdir(parents=True, exist_ok=True)

                # Write the filtered notebook
                with open(base_output_path, "w", encoding="utf-8") as f:
                    json.dump(notebook_dict, f, indent=1)

                processed_paths.add(rel_path)
                copied_count += 1
                logger.debug(f"Copied source notebook for download: {rel_path}")

        except Exception as e:
            logger.warning(f"Failed to copy source notebook {notebook_path}: {e}")

    # SECOND: Copy notebooks from _generated/nemo-nb/ (generated from .md files)
    if build_dir.exists():
        logger.info("Copying generated .ipynb files to output for downloads...")
        for notebook_path in build_dir.rglob("*.ipynb"):
            # Skip checkpoint directories
            if ".ipynb_checkpoints" in str(notebook_path):
                continue

            try:
                # Read the notebook
                with open(notebook_path, "r", encoding="utf-8") as f:
                    notebook_dict = json.load(f)

                # Count cells before stripping
                original_cell_count = len(notebook_dict.get("cells", []))

                # Strip hidden cells to prevent leaking secrets
                notebook_dict = strip_hidden_cells_from_notebook(notebook_dict)

                # Count cells after stripping
                filtered_cell_count = len(notebook_dict.get("cells", []))
                cells_removed = original_cell_count - filtered_cell_count

                if cells_removed > 0:
                    stripped_cells_count += cells_removed
                    logger.info(f"Stripped {cells_removed} hidden cell(s) from {notebook_path.name}")

                # Expand {include} directives to show actual content.
                # Include paths are written relative to the source file location, not the
                # generated notebook location. Compute the source-equivalent path so that
                # relative includes (e.g. ../../_snippets/...) resolve correctly.
                source_equiv_path = srcdir / notebook_path.relative_to(build_dir)
                notebook_dict = expand_include_directives(notebook_dict, source_equiv_path)

                # Promote code fences that landed inside markdown cells (e.g. from
                # {include} expansion) into proper code cells so they are filterable
                # by language and executable in Jupyter.
                notebook_dict = split_code_fences_in_markdown_cells(notebook_dict)

                # Get relative path from build_dir
                rel_path = notebook_path.relative_to(build_dir)

                # Skip if we already processed this path from source directory
                if rel_path in processed_paths:
                    logger.debug(f"Skipping duplicate notebook: {rel_path}")
                    continue

                # Determine base output path in the same directory structure
                base_output_path = outdir / rel_path

                # Check if notebook should be split into language variants
                if _should_split_notebook(notebook_dict):
                    # Count code cells by language
                    lang_counts = count_code_cells_by_language(notebook_dict)

                    # Create Python variant if has Python cells
                    if lang_counts.get("python", 0) > 0:
                        variant_path, orig_count, filt_count = _process_notebook_variant(
                            notebook_dict,
                            base_output_path,
                            "-python",
                            {"python"},
                            is_cli_variant=False,
                        )
                        processed_paths.add(variant_path.relative_to(outdir))
                        copied_count += 1
                        logger.debug(
                            f"Created Python variant for {notebook_path.name}: "
                            f"{filt_count} cells (from {orig_count} total)"
                        )

                    # Create CLI variant if has bash/sh/shell cells
                    cli_count = sum(lang_counts.get(lang, 0) for lang in ["bash", "sh", "shell"])
                    if cli_count > 0:
                        variant_path, orig_count, filt_count = _process_notebook_variant(
                            notebook_dict,
                            base_output_path,
                            "-cli",
                            {"bash", "sh", "shell"},
                            is_cli_variant=True,
                        )
                        processed_paths.add(variant_path.relative_to(outdir))
                        copied_count += 1
                        logger.debug(
                            f"Created CLI variant for {notebook_path.name}: "
                            f"{filt_count} cells (from {orig_count} total)"
                        )

                    # Skip writing main notebook (variants were created instead)
                    if lang_counts.get("python", 0) == 0 and cli_count == 0:
                        logger.warning(
                            f"Notebook {notebook_path.name} has split marker but no code cells - no variants created"
                        )

                else:
                    # Standard processing: single notebook (backward compatible)
                    # Strip MyST directive syntax from markdown cells
                    notebook_dict = strip_myst_directives_from_notebook(notebook_dict)

                    # Add %%bash magic to shell cells for Jupyter execution
                    notebook_dict = add_bash_magic_to_shell_cells(notebook_dict)

                    base_output_path.parent.mkdir(parents=True, exist_ok=True)

                    # Write the filtered notebook
                    with open(base_output_path, "w", encoding="utf-8") as f:
                        json.dump(notebook_dict, f, indent=1)

                    copied_count += 1
                    logger.debug(f"Copied generated notebook for download: {rel_path}")

            except Exception as e:
                logger.warning(f"Failed to copy generated notebook {notebook_path}: {e}")

    if copied_count > 0:
        logger.info(f"NeMo-NB: Copied {copied_count} notebook(s) to HTML output for downloads")
    if stripped_cells_count > 0:
        logger.info(f"NeMo-NB: Stripped {stripped_cells_count} total hidden cell(s) from downloadable notebooks")
