# Retrieval SDG

Use dedicated Data Designer jobs to replicate Nemotron embed/rerank Stage 0 (`sdg`) and Stage 1 (`prep`). Do not use `nemo data-designer create` for this pipeline.

Stage 0:

```bash
nemo data-designer retrieval-generate --spec '{"corpus":"default/my-docs","provider":"default/nvidia-build","profile":"embed"}'
```

Stage 1 (conversion only, skip GPU mining):

```bash
nemo data-designer retrieval-prepare --spec '{"sdg_input":"default/stage0-out","skip_mining":true}'
```

Skip SDG entirely by pointing `sdg_input` at `hf://nvidia/Retrieval-Synthetic-NVDocs-v1@...` or a fileset that already contains `generation_result.json`.

Model roles resolve through Inference Gateway (`provider` + served model names). Do not set `NVIDIA_API_KEY` on the job.

Chaining generate then prepare is a jobs-service multi-step job (`retrieval-run`), not Data Designer workflow chaining.
