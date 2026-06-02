Focus generation of question on performing evaluation for public https://huggingface.co/datasets/nvidia/ProfBench dataset:
- Task 1: use `rubrics` column as ground truth to evaluate how `nvidia/llama-3.3-nemotron-super-49b-v1.5` model at https://integrate.api.nvidia.com/v1 model provider pefrorms on the first 3 samples from the dataset
- Task 2: negative case scenario - `How do I configure a Kubernetes horizontal pod autoscaler to scale my Flask application based on custom Prometheus metrics?`

Tips for writing good test prompts:
Start with 2-3 test cases. Don’t over-invest before you’ve seen your first round of results. You can expand the set later.
Vary the prompts. Use different phrasings, levels of detail, and formality. Some prompts should be casual (“hey can you clean up this csv”), others precise (“Parse the CSV at data/input.csv, drop rows where column B is null, and write the result to data/output.csv”).
Cover edge cases. Include at least one prompt that tests a boundary condition — a malformed input, an unusual request, or a case where the skill’s instructions might be ambiguous.
Use realistic context. Real users mention file paths, column names, and personal context. Prompts like “process this data” are too vague to test anything useful.