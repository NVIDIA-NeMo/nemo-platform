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

```mdx
import { NotebookViewer } from "@/components/NotebookViewer";
import notebook from "@/components/notebooks/sft-customization-job";

<NotebookViewer
  notebook={notebook}
  colabUrl="https://colab.research.google.com/github/NVIDIA-NeMo/Platform/blob/main/docs/customizer/tutorials/sft-customization-job.ipynb"
/>
```
