<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# NeMo-NB Usage Guide

_Back to [README.md](README.md)._

Guide for using NeMo-NB in your Sphinx documentation projects.

---

## File Types

NeMo-NB works with three file types:

1. **`.ipynb`** - Jupyter Notebook (standard format)
2. **`.md` (notebook format)** - Source markdown (`notebook.md`)
3. **`.md` (Sphinx docs format)** - Generated docs (`notebook.sphinx.md`)

**Conversion Path:** MD (notebook) -> .ipynb -> MD (Sphinx docs) -> HTML

See [CLI.md](CLI.md) for file type details and conversion workflows.

---

## Documentation Structure

This guide provides usage patterns and workflows. For detailed references:

- **[MARKERS.md](MARKERS.md)** - Complete marker commands reference
- **[CLI.md](CLI.md)** - CLI tool reference  
- **[INSTALL.md](INSTALL.md)** - Installation and setup
- **[README.md](README.md)** - Overview and features

---

## Quick Start

### 1. Create a Markdown Notebook

Use standard markdown with fenced code blocks:

````markdown
# My Notebook

This is markdown text.

```python
x = 1
print(x)
```

More markdown here.

```bash
echo "Hello"
```
````

Or use explicit cell markers for more control:

```markdown
<!-- @nemo-nb: process -->
# My Notebook

<!-- @nemo-nb: cell python -->
x = 1
print(x)
```

### 2. Add Opt-In Marker (if using explicit markers)

Add the opt-in marker to enable conversion:

**In markdown cells:**

```markdown
<!-- @nemo-nb: process -->
# Your Notebook Title
```

**In code cells:**

```python
# @nemo-nb: process
```

### 3. Use Marker Commands

Control conversion with marker commands in your cells:

```python
# @nemo-nb: hide
secret_key = "hidden-from-docs"
```

```markdown
<!-- @nemo-nb: download -->
```

```python
# @nemo-nb: wrap-cell-start :::{dropdown} Advanced Example
# @nemo-nb: wrap-cell-end :::
advanced_code()
```

### 4. Build with Sphinx

```bash
sphinx-build -b html docs _build/html
```

**For complete marker reference, see [MARKERS.md](MARKERS.md).**

---

## Common Patterns

### Pattern 1: Creating Tab-Sets

Tab-sets display alternative code examples (Python SDK, cURL, etc.) in tabs.

**Cell 1: Open Tab-Set**

```markdown
<!-- @nemo-nb: insert ::::{tab-set} -->
<!-- @nemo-nb: multi-cell-indent-space-start tabs 0 -->
```

**Cell 2: First Tab**

```python
# @nemo-nb: wrap-cell-start :::{tab-item} Python SDK
# @nemo-nb: wrap-cell-end :::
# @nemo-nb: insert :sync: sdk

from nemo import Client
client = Client()
result = client.process()
```

**Cell 3: Second Tab**

```bash
# @nemo-nb: wrap-cell-start :::{tab-item} cURL
# @nemo-nb: wrap-cell-end :::
# @nemo-nb: insert :sync: sdk

curl -X POST http://api.example.com/process
```

**Cell 4: Close Tab-Set**

```markdown
<!-- @nemo-nb: multi-cell-indent-space-end tabs -->
<!-- @nemo-nb: insert :::: -->
```

---

### Pattern 2: Collapsible Code

Use dropdowns to hide advanced or optional code.

```python
# @nemo-nb: wrap-cell-start :::{dropdown} Advanced Configuration
# @nemo-nb: wrap-cell-end :::

config = {
    "option_1": "value",
    "option_2": "value",
    # ... many more options
}
client.configure(config)
```

---

### Pattern 3: Hiding Setup Code

Hide API keys, imports, or setup code not relevant to documentation.

```python
# @nemo-nb: hide
import os
api_key = os.environ.get("API_KEY")
internal_setup()
```

---

### Pattern 4: Multi-Step Workflow

Create readable workflows with markdown headings between code steps.

**Cell 1:**

```markdown
<!-- @nemo-nb: insert :::{dropdown} Complete Workflow
<!-- @nemo-nb: multi-cell-indent-space-start workflow 0 -->

## Step 1: Initialize Client
```

**Cell 2:**

```python
client = NeMoClient()
client.authenticate()
```

**Cell 3:**

```markdown
## Step 2: Process Data
```

**Cell 4:**

```python
result = client.process(data)
```

**Cell 5:**

```python
# @nemo-nb: multi-cell-indent-space-end workflow
print(f"Result: {result}")
```

**Cell 6:**

```markdown
<!-- @nemo-nb: insert ::: -->
```

---

### Pattern 5: Emphasizing Important Code Lines

Highlight specific lines in code blocks.

```python
# @nemo-nb: insert-code-block-start :emphasize-lines: 2-3
# @nemo-nb: language {code-block}

def important_function():
    critical_line_1()  # Emphasized
    critical_line_2()  # Emphasized
    normal_line()
```

---

### Pattern 6: Nested Directives

Create complex nested structures using multiple wrap pairs.

```python
# @nemo-nb: wrap-cell-start :::{dropdown} Details
# @nemo-nb: wrap-cell-end :::
# @nemo-nb: wrap-cell-start :::{warning}
# @nemo-nb: wrap-cell-end :::
# @nemo-nb: insert This operation is destructive!

delete_all_data()
```

**Generates:**

````markdown
::::{dropdown} Details
::::{warning}
This operation is destructive!

```python
delete_all_data()
```
::::
::::
````

---

## Authoring in Markdown (MD Notebook Format)

### Creating Markdown Notebooks

Author documentation in **MD (notebook format)** instead of JSON.

**Create `tutorial.md`:**

````markdown
<!-- @nemo-nb: process -->
# Getting Started Tutorial

Introduction text here.

```python
print("Hello, world!")
```

<!-- @nemo-nb: output-cell-start -->

```
Hello, world!
```

<!-- @nemo-nb: output-cell-end -->

More markdown content...
````

### Including Expected Outputs

Add expected outputs inline using output cell markers.

**Syntax:**

````markdown
```python
# Your code here
```

<!-- @nemo-nb: output-cell-start -->

```
Expected output here
```

<!-- @nemo-nb: output-cell-end -->
````

**Output Types:**
- `stream` - Standard output (stdout/stderr)
- `execute_result` - Result of expression
- `display_data` - Rich display output
- `error` - Error/exception output

**See [MARKERS.md](MARKERS.md#output-cell-markers) for complete output cell reference.**

---

## Workflows

### Workflow 1: Notebook-First Development

Create notebooks in Jupyter, then convert for docs.

1. Create and execute notebook in Jupyter/VSCode
2. Add `<!-- @nemo-nb: process -->` marker
3. Add marker commands to control conversion
4. Build Sphinx docs to generate final HTML

```bash
# Develop notebook
jupyter notebook my_tutorial.ipynb

# Build docs
sphinx-build docs _build/html
```

---

### Workflow 2: Markdown-First Authoring

Author in markdown format, convert to notebooks as needed.

1. Create `.md` file (MD notebook format)
2. Write markdown with code fences
3. Add output cell markers for expected outputs
4. Build with Sphinx (auto-converts to .ipynb then docs)

```bash
# Edit markdown
vim docs/tutorials/getting_started.md

# Build docs (handles conversions automatically)
sphinx-build docs _build/html
```

---

### Workflow 3: Version Control Friendly

Use markdown format for easier version control.

```bash
# Convert existing notebooks to markdown format
nemo-nb nb-to-md tutorial.ipynb

# Add .md to git
git add tutorial.md

# Ignore generated files
echo "*.ipynb" >> .gitignore
echo "*.sphinx.md" >> .gitignore

# Team members convert back to notebooks
nemo-nb md-to-nb tutorial.md
```

---

### Workflow 4: Local Testing

Test conversion locally before committing.

```bash
# Convert to Sphinx docs format to preview
nemo-nb to-sphinx-md notebook.ipynb

# Review generated markdown
cat notebook.sphinx.md

# Test full build
sphinx-build docs _build/html
```

---

## Troubleshooting

### Notebook Not Converting

**Problem:** Notebook doesn't appear in documentation

**Solution:** Add opt-in marker to at least one cell:

```markdown
<!-- @nemo-nb: process -->
```

---

### Tab-Sets Not Rendering

**Problem:** Tab-sets appear as plain text

**Solution:** Ensure correct structure:

1. Open with `::::{tab-set}` (4 colons)
2. Use `multi-cell-indent-space-start` with 0 spaces
3. Each tab uses `:::{tab-item}` (3 colons)
4. Close with `::::`

See [Common Pattern 1](#pattern-1-creating-tab-sets) for complete example.

---

### Indentation Issues

**Problem:** Code not aligned with directives

**Solution:** Use indentation commands:

- `indent-space <number>` - Single cell
- `multi-cell-indent-space-start/end` - Multiple cells

---

### Marker Not Working

**Problem:** Marker command not processed

**Solutions:**

1. Check marker syntax (correct comment style for cell type)
2. Ensure marker is on its own line
3. Verify marker is supported (see [MARKERS.md](MARKERS.md))
4. Check for typos in command name

---

### Output Cells Not Showing in Notebook

**Problem:** Output cell markers don't create outputs in `.ipynb`

**Note:** Output markers only work in **MD (notebook format)**:

- Works in: `tutorial.md`
- Doesn't work in: `tutorial.ipynb`
- Doesn't work in: `tutorial.sphinx.md`

---

## Tips and Best Practices

### File Organization

**Recommended structure:**

```text
docs/
    tutorials/
        getting_started.md         # Source (commit to git)
        getting_started.ipynb      # Generated (gitignore)
        getting_started.sphinx.md  # Generated (gitignore)
```

**Gitignore:**

```gitignore
# Generated files
*.ipynb
*.sphinx.md
```

---

### Marker Placement

**Best practices:**

- Place `process` marker in first cell
- Place `notebook-convert-4-space-to-tab` with `process` marker
- Place `hide` marker on first line of cell to hide
- Place `wrap-cell-start`/`end` markers consecutively

---

### Directive Naming

**Use descriptive tab/dropdown titles:**

```python
# Good
# @nemo-nb: wrap-cell-start :::{tab-item} Python SDK Example

# Less clear
# @nemo-nb: wrap-cell-start :::{tab-item} Python
```

---

### Testing Changes

**Always test locally before committing:**

```bash
# 1. Convert locally
nemo-nb nb-to-md tutorial.ipynb

# 2. Review output
cat tutorial.sphinx.md | less

# 3. Full build
sphinx-build docs _build/html

# 4. Check browser
firefox _build/html/tutorials/tutorial.html
```

---

## Advanced Usage

### Custom Indentation

Combine multiple indentation commands for complex structures:

```python
# @nemo-nb: indent-space 4
# @nemo-nb: wrap-cell-start :::{note}
# @nemo-nb: wrap-cell-end :::
content()
```

---

### Multiple Nested Wraps

Create complex nested directives with multiple wrap pairs:

```python
# @nemo-nb: wrap-cell-start ::::{grid} 2
# @nemo-nb: wrap-cell-end ::::
# @nemo-nb: wrap-cell-start :::{grid-item}
# @nemo-nb: wrap-cell-end :::
# @nemo-nb: wrap-cell-start :::{dropdown} Example
# @nemo-nb: wrap-cell-end :::
nested_content()
```

---

### Reference Targets

Add reference targets for cross-linking:

```python
# @nemo-nb: insert (api-authentication)=

def authenticate():
    pass
```

Link to it elsewhere:

```markdown
See [authentication section](api-authentication).
```

---

## See Also

- **[MARKERS.md](MARKERS.md)** - Complete marker commands reference with all syntax and options
- **[CLI.md](CLI.md)** - CLI tool reference with conversion workflows
- **[README.md](README.md)** - Overview, features, and architecture
- **[INSTALL.md](INSTALL.md)** - Installation, configuration, and setup

---

**Version**: 0.5.0
