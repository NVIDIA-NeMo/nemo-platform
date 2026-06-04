# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pass-based notebook sugar pipeline.

This module implements a compiler-pass architecture for adding syntactic sugar
transformations to notebook cells. Each pass is a self-contained unit that:
1. Detects a specific pattern in cells
2. Transforms cells based on that detection
3. Returns the modified cell list

Passes can:
- Modify cell source (add markers, comment out lines)
- Combine multiple cells into one
- Split one cell into multiple
- Remove cells entirely

The pipeline runs passes in sequence, feeding the output of one pass
as input to the next.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable

from .structures import Cell

# ---------------------------------------------------------------------------
# Constants: Marker strings and patterns
# ---------------------------------------------------------------------------

# Nemo-NB comment marker prefix
MARKER_PREFIX = "@nemo-nb:"

# Nemo-NB directives (used after MARKER_PREFIX)
DIRECTIVE_INSERT = "insert"
DIRECTIVE_MULTI_CELL_INDENT_START = "multi-cell-indent-space-start"
DIRECTIVE_MULTI_CELL_INDENT_END = "multi-cell-indent-space-end"
DIRECTIVE_WRAP_CELL_START = "wrap-cell-start"
DIRECTIVE_WRAP_CELL_END = "wrap-cell-end"
DIRECTIVE_INSERT_CODE_BLOCK_START = "insert-code-block-start"
DIRECTIVE_LANGUAGE = "language"

# MyST directive markers
MYST_TAB_SET = "::::{tab-set}"
MYST_TAB_ITEM = ":::{tab-item}"
MYST_DROPDOWN = ":::{dropdown}"
MYST_CODE_BLOCK = "{code-block}"

# Fence patterns (compiled regexes for precise matching)
# Matches closing fence with 4+ colons (for tab-set)
RE_CLOSING_FENCE_4 = re.compile(r"^\s*:{4,}\s*$")
# Matches closing fence with 2-3 colons (for tab-item, dropdown)
RE_CLOSING_FENCE_3 = re.compile(r"^\s*:::?\s*$")
# Generic fence prefix (used to detect any MyST fence syntax)
FENCE_PREFIX = ":::"
# Matches MyST label pattern at start: (label-name)=
RE_MYST_LABEL = re.compile(r"^\(([^)]+)\)=\s*\n")
# Matches tab-item directive with title
RE_TAB_ITEM = re.compile(r":::{tab-item}\s+(.+)")
# Matches dropdown directive with title
RE_DROPDOWN = re.compile(r":::{dropdown}\s+(.+)")
# Matches :sync: option
RE_SYNC_OPTION = re.compile(r":sync:\s+([\w-]+)")


@dataclass
class PassOptions:
    """Options that control pass behavior."""

    fence_conversion_disabled: bool = False
    verbose: bool = False


@runtime_checkable
class SugarPass(Protocol):
    """Protocol for a sugar pass.

    Each pass is a self-contained transformation that:
    1. Scans cells for a specific pattern
    2. Applies transformations (add markers, merge cells, etc.)
    3. Returns the modified cell list
    """

    @property
    def name(self) -> str:
        """Human-readable name for this pass."""
        ...

    def apply(self, cells: List[Cell], options: PassOptions) -> List[Cell]:
        """Apply this pass to cells.

        Args:
            cells: List of notebook cells to process.
            options: Pass configuration options.

        Returns:
            Modified list of cells (may be same length, shorter, or longer).
        """
        ...


class BasePass(ABC):
    """Base class for sugar passes with common utilities."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this pass."""
        ...

    @abstractmethod
    def apply(self, cells: List[Cell], options: PassOptions) -> List[Cell]:
        """Apply this pass to cells."""
        ...

    def get_comment_char(self, cell: Cell) -> str:
        """Get the appropriate comment character for a cell."""
        return cell.get_comment_char()

    def strip_leading_empty_lines(self, lines: List[str]) -> List[str]:
        """Remove leading empty lines from a list of lines."""
        start = 0
        for i, line in enumerate(lines):
            if line.strip():
                start = i
                break
        else:
            return []
        return lines[start:]

    def strip_trailing_empty_lines(self, lines: List[str]) -> List[str]:
        """Remove trailing empty lines from a list of lines."""
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip():
                end = i + 1
                break
        else:
            return []
        return lines[:end]

    def content_as_string(self, cell: Cell) -> str:
        """Get cell source as a single string."""
        return "".join(cell.source)


# ---------------------------------------------------------------------------
# Pass: Label Insert
# ---------------------------------------------------------------------------


class LabelInsertPass(BasePass):
    """Detect MyST labels at document start and add insert markers.

    Looks for patterns like `(my-label)=` at the beginning of the first cell
    and adds an insert marker so the label is preserved in output.
    """

    @property
    def name(self) -> str:
        return "LabelInsert"

    def apply(self, cells: List[Cell], options: PassOptions) -> List[Cell]:
        if not cells or cells[0].cell_type != "markdown":
            return cells

        first_cell = cells[0]
        content = self.content_as_string(first_cell)

        # Look for MyST label pattern at the start: (label-name)=
        label_match = RE_MYST_LABEL.match(content)
        if not label_match:
            return cells

        label = label_match.group(0).strip()
        lines = list(first_cell.source)

        # Remove the label line
        if lines and label in lines[0]:
            lines = lines[1:]
            lines = self.strip_leading_empty_lines(lines)

        # Find position to insert marker (after frontmatter and existing markers)
        insert_pos = self._find_insert_position(lines)

        # Insert the marker
        lines.insert(insert_pos, f"<!-- {MARKER_PREFIX} {DIRECTIVE_INSERT} {label} -->\n")

        # Update cell in place
        first_cell.source = lines
        return cells

    def _find_insert_position(self, lines: List[str]) -> int:
        """Find the position to insert a marker."""
        insert_pos = 0
        content_str = "".join(lines)

        # Skip past frontmatter if present
        if content_str.strip().startswith("---"):
            for i, line in enumerate(lines):
                if i > 0 and line.strip() == "---":
                    insert_pos = i + 1
                    break

        # Skip past existing @nemo-nb markers
        for i in range(insert_pos, len(lines)):
            if MARKER_PREFIX not in lines[i]:
                return i

        return len(lines)


# ---------------------------------------------------------------------------
# Pass: Tab Set Detection and Marking
# ---------------------------------------------------------------------------


class TabSetPass(BasePass):
    """Detect tab-sets and add multi-cell-indent markers.

    Looks for `::::{tab-set}` directives and adds:
    - multi-cell-indent-space-start marker at the opening
    - multi-cell-indent-space-end marker at the closing ::::
    - insert markers for the directive fences
    """

    @property
    def name(self) -> str:
        return "TabSet"

    def __init__(self):
        self._group_counter = 0

    def apply(self, cells: List[Cell], options: PassOptions) -> List[Cell]:
        if options.fence_conversion_disabled:
            return cells

        self._group_counter = 0
        result: List[Cell] = []
        i = 0

        while i < len(cells):
            cell = cells[i]

            if cell.cell_type == "markdown":
                content = self.content_as_string(cell)

                if MYST_TAB_SET in content:
                    # Process this tab-set and all cells until its closing
                    processed, consumed = self._process_tab_set(cells, i)
                    result.extend(processed)
                    i += consumed
                    continue

            result.append(cell)
            i += 1

        return result

    def _process_tab_set(self, cells: List[Cell], start_idx: int) -> tuple[List[Cell], int]:
        """Process a tab-set starting at start_idx.

        Returns:
            Tuple of (processed cells, number of cells consumed).
        """
        group_id = f"indent-{chr(97 + self._group_counter)}"
        self._group_counter += 1

        cell = cells[start_idx]
        content = self.content_as_string(cell)
        lines = list(cell.source)

        # Detect indentation level
        indent_spaces = self._detect_indent_level(content, MYST_TAB_SET)

        # Find where tab-set starts in the cell
        tab_set_idx = None
        for j, line in enumerate(lines):
            if MYST_TAB_SET in line:
                tab_set_idx = j
                break

        result_cells: List[Cell] = []

        if tab_set_idx is not None and tab_set_idx > 0:
            # Split: content before tab-set stays in one cell
            before_lines = lines[:tab_set_idx]
            after_lines = lines[tab_set_idx + 1 :]

            # Keep content before tab-set
            before_cell = Cell(cell_type="markdown", source=before_lines)
            result_cells.append(before_cell)

            # Create new cell with markers
            new_source = [
                f"<!-- {MARKER_PREFIX} {DIRECTIVE_MULTI_CELL_INDENT_START} {group_id} {indent_spaces} -->\n",
                f"<!-- {MARKER_PREFIX} {DIRECTIVE_INSERT} {MYST_TAB_SET} -->\n",
            ]
            new_source.extend(after_lines)
            marker_cell = Cell(cell_type="markdown", source=new_source)
            result_cells.append(marker_cell)
        else:
            # Tab-set is at beginning of cell
            new_source = [
                f"<!-- {MARKER_PREFIX} {DIRECTIVE_MULTI_CELL_INDENT_START} {group_id} {indent_spaces} -->\n",
                f"<!-- {MARKER_PREFIX} {DIRECTIVE_INSERT} {MYST_TAB_SET} -->\n",
            ]
            for line in lines:
                if MYST_TAB_SET not in line:
                    new_source.append(line)
            cell.source = new_source
            result_cells.append(cell)

        # Find the closing :::: and process intervening cells
        consumed = 1
        i = start_idx + 1

        while i < len(cells):
            current = cells[i]
            consumed += 1

            if current.cell_type == "markdown":
                # Check for tab-set closing
                closing_idx = self._find_closing_fence(current.source)
                if closing_idx is not None:
                    # Found closing - add end marker
                    processed = self._process_closing(current, closing_idx, group_id)
                    result_cells.extend(processed)
                    break

            result_cells.append(current)
            i += 1

        return result_cells, consumed

    def _find_closing_fence(self, lines: List[str]) -> Optional[int]:
        """Find index of closing :::: line."""
        for j, line in enumerate(lines):
            if RE_CLOSING_FENCE_4.match(line):
                return j
        return None

    def _process_closing(self, cell: Cell, closing_idx: int, group_id: str) -> List[Cell]:
        """Process a cell containing the closing fence."""
        lines = list(cell.source)
        closing_fence = lines[closing_idx].strip()

        # Check if there is content before the closing line
        has_content_before = any(line.strip() and FENCE_PREFIX not in line for line in lines[:closing_idx])

        result: List[Cell] = []

        if has_content_before:
            # Keep content before closing in current cell
            before_lines = self.strip_trailing_empty_lines(lines[:closing_idx])
            before_lines.append(f"<!-- {MARKER_PREFIX} {DIRECTIVE_INSERT} {closing_fence} -->\n")
            cell.source = before_lines
            result.append(cell)

            # End marker in new cell
            after_lines = lines[closing_idx + 1 :]
            new_source = [f"<!-- {MARKER_PREFIX} {DIRECTIVE_MULTI_CELL_INDENT_END} {group_id} -->\n"]
            new_source.extend(after_lines)
            end_cell = Cell(cell_type="markdown", source=new_source)
            result.append(end_cell)
        else:
            # No content before - insert marker must come before end marker
            new_source = [
                f"<!-- {MARKER_PREFIX} {DIRECTIVE_INSERT} {closing_fence} -->\n",
                f"<!-- {MARKER_PREFIX} {DIRECTIVE_MULTI_CELL_INDENT_END} {group_id} -->\n",
            ]
            new_source.extend(lines[closing_idx + 1 :])
            cell.source = new_source
            result.append(cell)

        return result

    def _detect_indent_level(self, content: str, marker: str) -> int:
        """Detect indentation level of a marker in content."""
        for line in content.split("\n"):
            if marker in line:
                return len(line) - len(line.lstrip())
        return 0


# ---------------------------------------------------------------------------
# Pass: Tab Item Marking
# ---------------------------------------------------------------------------


class TabItemPass(BasePass):
    """Detect tab-items and add wrap-cell markers.

    Looks for `:::{tab-item}` directives that precede code cells
    and adds wrap-cell-start/end markers to wrap the code.
    """

    @property
    def name(self) -> str:
        return "TabItem"

    def apply(self, cells: List[Cell], options: PassOptions) -> List[Cell]:
        if options.fence_conversion_disabled:
            return cells

        result: List[Cell] = []

        for i, cell in enumerate(cells):
            if cell.cell_type == "markdown":
                content = self.content_as_string(cell)

                if MYST_TAB_ITEM in content:
                    # Check if next cell is code
                    if i + 1 < len(cells) and cells[i + 1].cell_type == "code":
                        # Split if multiple tab-items in one cell
                        split_cells = self._split_tab_items(cell)

                        for j, split_cell in enumerate(split_cells):
                            # For each split cell with tab-item followed by code
                            if MYST_TAB_ITEM in self.content_as_string(split_cell):
                                next_idx = i + 1 + j
                                if next_idx < len(cells) and cells[next_idx].cell_type == "code":
                                    self._mark_code_cell(split_cell, cells[next_idx])
                                    if split_cell.source:
                                        result.append(split_cell)
                                else:
                                    result.append(split_cell)
                            else:
                                result.append(split_cell)

                        continue

            result.append(cell)

        return result

    def _split_tab_items(self, cell: Cell) -> List[Cell]:
        """Split a cell containing multiple tab-items."""
        lines = cell.source
        tab_positions = [idx for idx, line in enumerate(lines) if MYST_TAB_ITEM in line]

        if len(tab_positions) <= 1:
            return [cell]

        split_cells: List[Cell] = []
        for idx, start in enumerate(tab_positions):
            end = tab_positions[idx + 1] if idx + 1 < len(tab_positions) else len(lines)
            segment = lines[start:end]
            if idx == 0:
                segment = lines[:start] + segment
            split_cells.append(Cell(cell_type="markdown", source=segment))

        return split_cells

    def _mark_code_cell(self, md_cell: Cell, code_cell: Cell) -> None:
        """Add wrap-cell markers to a code cell for tab-item."""
        content = self.content_as_string(md_cell)

        # Extract tab-item info
        tab_item_match = RE_TAB_ITEM.search(content)
        if not tab_item_match:
            return

        tab_name = tab_item_match.group(1).strip()
        sync_match = RE_SYNC_OPTION.search(content)
        sync_line = sync_match.group(0) if sync_match else None

        # Separate prefix markers from text
        prefix_lines: List[str] = []
        text_lines: List[str] = []

        for line in md_cell.source:
            if MYST_TAB_ITEM in line or RE_CLOSING_FENCE_3.match(line):
                continue
            if line.strip().startswith(f"<!-- {MARKER_PREFIX}"):
                prefix_lines.append(line)
            else:
                text_lines.append(line.rstrip("\n"))

        md_cell.source = prefix_lines

        # Build code cell markers
        comment = self.get_comment_char(code_cell)
        new_lines = [
            f"{comment} {MARKER_PREFIX} {DIRECTIVE_WRAP_CELL_START} {MYST_TAB_ITEM} {tab_name}\n",
        ]

        if sync_line:
            new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_INSERT} {sync_line}\n")

        new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_WRAP_CELL_END} :::\n")

        # Add text lines as insert markers (skip sync line if already added)
        found_sync = False
        for line in text_lines:
            if sync_line and sync_line in line:
                found_sync = True
                continue
            if line:
                new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_INSERT} {line}\n")
            elif found_sync:
                new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_INSERT}\n")

        new_lines.extend(code_cell.source)
        code_cell.source = new_lines


# ---------------------------------------------------------------------------
# Pass: Dropdown Marking
# ---------------------------------------------------------------------------


class DropdownPass(BasePass):
    """Detect dropdowns and add wrap-cell markers.

    Looks for `:::{dropdown}` directives that precede code cells
    and adds wrap-cell-start/end markers.
    """

    @property
    def name(self) -> str:
        return "Dropdown"

    def apply(self, cells: List[Cell], options: PassOptions) -> List[Cell]:
        if options.fence_conversion_disabled:
            return cells

        result: List[Cell] = []
        i = 0

        while i < len(cells):
            cell = cells[i]

            if cell.cell_type == "markdown":
                content = self.content_as_string(cell)

                if MYST_DROPDOWN in content:
                    # Check if dropdown closes in this cell (inline content)
                    if self._dropdown_closes_in_cell(cell):
                        result.append(cell)
                        i += 1
                        continue

                    # Check if next cell is code
                    if i + 1 < len(cells) and cells[i + 1].cell_type == "code":
                        code_cell = cells[i + 1]
                        next_md = cells[i + 2] if i + 2 < len(cells) and cells[i + 2].cell_type == "markdown" else None
                        self._wrap_code_cell(cell, code_cell, next_md)
                        result.append(cell)
                        result.append(code_cell)
                        i += 2
                        if next_md:
                            result.append(next_md)
                            i += 1
                        continue

            result.append(cell)
            i += 1

        return result

    def _dropdown_closes_in_cell(self, cell: Cell) -> bool:
        """Check if dropdown directive closes within the same cell."""
        found_dropdown = False
        for line in cell.source:
            if MYST_DROPDOWN in line:
                found_dropdown = True
            elif found_dropdown and RE_CLOSING_FENCE_3.match(line):
                return True
        return False

    def _wrap_code_cell(self, md_cell: Cell, code_cell: Cell, next_md: Optional[Cell]) -> None:
        """Wrap a code cell with dropdown markers."""
        content = self.content_as_string(md_cell)

        # Extract dropdown info
        dropdown_match = RE_DROPDOWN.search(content)
        if not dropdown_match:
            return

        title = dropdown_match.group(1).strip()

        # Extract options
        icon_line = None
        open_line = None
        emphasize_line = None

        for line in md_cell.source:
            if ":icon:" in line:
                icon_line = line.strip()
            if ":open:" in line:
                open_line = line.strip()
            if ":emphasize-lines:" in line:
                emphasize_line = line.strip()

        # Determine if we need code-block
        use_code_block = MYST_CODE_BLOCK in content or emphasize_line

        # Remove dropdown section from markdown cell
        new_md_lines: List[str] = []
        skip_mode = False
        for line in md_cell.source:
            if MYST_DROPDOWN in line:
                skip_mode = True
                continue
            if skip_mode and any(x in line for x in [":icon:", ":open:", ":emphasize-lines:"]):
                continue
            if skip_mode and RE_CLOSING_FENCE_3.match(line):
                skip_mode = False
                continue
            if not skip_mode:
                new_md_lines.append(line)

        md_cell.source = self.strip_trailing_empty_lines(new_md_lines)

        # Consume closing ::: from next markdown cell if present
        if next_md:
            lines = next_md.source
            start_idx = 0
            while start_idx < len(lines) and not lines[start_idx].strip():
                start_idx += 1
            if start_idx < len(lines) and RE_CLOSING_FENCE_3.match(lines[start_idx]):
                lines.pop(start_idx)
                next_md.source = lines

        # Build code cell markers
        comment = self.get_comment_char(code_cell)
        new_lines = [
            f"{comment} {MARKER_PREFIX} {DIRECTIVE_WRAP_CELL_START} {MYST_DROPDOWN} {title}\n",
        ]

        if icon_line:
            new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_INSERT} {icon_line}\n")
        if open_line:
            new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_INSERT} {open_line}\n")

        new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_WRAP_CELL_END} :::\n")

        if use_code_block and emphasize_line:
            new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_INSERT_CODE_BLOCK_START} {emphasize_line}\n")
            new_lines.append(f"{comment} {MARKER_PREFIX} {DIRECTIVE_LANGUAGE} {MYST_CODE_BLOCK}\n")

        new_lines.extend(code_cell.source)
        code_cell.source = new_lines


# ---------------------------------------------------------------------------
# Pipeline: Run passes in sequence
# ---------------------------------------------------------------------------


class SugarPipeline:
    """Run a sequence of sugar passes over notebook cells.

    Each pass receives the output of the previous pass, allowing
    transformations to build on each other.
    """

    def __init__(self, passes: Optional[List[SugarPass]] = None):
        """Initialize pipeline with passes.

        Args:
            passes: List of passes to run. If None, uses default passes.
        """
        if passes is None:
            passes = self.default_passes()
        self.passes = passes

    @staticmethod
    def default_passes() -> List[SugarPass]:
        """Return the default set of passes."""
        return [
            TabSetPass(),
            TabItemPass(),
            DropdownPass(),
            LabelInsertPass(),
        ]

    def run(self, cells: List[Cell], options: Optional[PassOptions] = None) -> List[Cell]:
        """Run all passes over the cells.

        Args:
            cells: Input cells to process.
            options: Pass options. If None, uses defaults.

        Returns:
            Transformed cells.
        """
        if options is None:
            options = PassOptions()

        for p in self.passes:
            cells = p.apply(cells, options)

        return cells
