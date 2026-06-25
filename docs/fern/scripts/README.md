# Fern scripts

Run these from the **repository root**. For local development, use `uv run` — dependencies are resolved via the workspace `pyproject.toml`.

`requirements.txt` in this directory lists the direct Python dependencies for CI or other `pip install -r` workflows.

## `ipynb-to-fern-json.py`

Converts Jupyter notebooks to the JSON/TS format consumed by
`fern/components/NotebookViewer.tsx`. Pulled from
[NVIDIA-NeMo/DataDesigner](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/fern/scripts/ipynb-to-fern-json.py).

### Run

```bash
uv run python docs/fern/scripts/ipynb-to-fern-json.py \
  docs/customizer/tutorials/sft-customization-job.ipynb \
  -o docs/fern/components/notebooks/sft-customization-job.json
```

Writes both `<name>.json` (canonical data) and `<name>.ts` (default-export wrapper
that MDX imports). Re-run whenever the source `.ipynb` changes.

### MDX usage

After writing the `.ts` module, register it in `fern/components/NotebookViewer.tsx`
(import + entry in the `notebooks` map). Pages outside `docs/fern/` can't use
`@/` imports, so the registry pattern is required.

```mdx
<NotebookViewer
  name="sft-customization-job"
  colabUrl="https://colab.research.google.com/github/NVIDIA-NeMo/nemo-platform/blob/main/docs/customizer/tutorials/sft-customization-job.ipynb"
/>
```

## `ipynb-to-mdx.py`

Converts Jupyter notebooks to **inline Fern MDX** using `nemo_nb` (`NotebookConverter`,
same engine as `nemo-nb to-sphinx-md`). Post-processes for Fern frontmatter, a Google
Colab banner, and canonical `/documentation/...` internal links.

### Run MDX conversion

```bash
uv run python docs/fern/scripts/ipynb-to-mdx.py --all-customizer-tutorials
```

Or a single notebook:

```bash
uv run python docs/fern/scripts/ipynb-to-mdx.py \
  docs/customizer/tutorials/sft-customization-job.ipynb \
  -o docs/customizer/tutorials/sft-customization-job.mdx \
  --title "Full SFT Customization"
```

Re-run whenever the source `.ipynb` changes.
