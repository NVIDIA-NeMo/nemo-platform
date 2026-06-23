# Fern scripts

## `ipynb-to-fern-json.py`

Converts Jupyter notebooks to the JSON/TS format consumed by
`fern/components/NotebookViewer.tsx`. Pulled from
[NVIDIA-NeMo/DataDesigner](https://github.com/NVIDIA-NeMo/DataDesigner/blob/main/fern/scripts/ipynb-to-fern-json.py).

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r fern/scripts/requirements.txt
```

### Run

```bash
python fern/scripts/ipynb-to-fern-json.py \
  docs/customizer/tutorials/sft-customization-job.ipynb \
  -o fern/components/notebooks/sft-customization-job.json
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

### Run

From the repo root:

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

Re-run whenever the source `.ipynb` changes. DPO is intentionally excluded from
`--all-customizer-tutorials` (still uses `<NotebookViewer />`).
