---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

license: other
license_name: nvidia-open-model-license
license_link: >-
  https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
tags:
  - text
  - text-embeddings
  - retrieval
  - semantic-search
  - transformers
language:
  - multilingual
library_name: sentence-transformers
---

## **Model Overview**

### **Description**

The Llama Nemotron Embedding 1B model is optimized for **multilingual and cross-lingual** text question-answering retrieval with **support for long documents (up to 8192 tokens) and dynamic embedding size (Matryoshka Embeddings)**. This model was evaluated on 26 languages: English, Arabic, Bengali, Chinese, Czech, Danish, Dutch, Finnish, French, German, Hebrew, Hindi, Hungarian, Indonesian, Italian, Japanese, Korean, Norwegian, Persian, Polish, Portuguese, Russian, Spanish, Swedish, Thai, and Turkish.

In addition to enabling multilingual and cross-lingual question-answering retrieval, this model reduces the data storage footprint by 35x through dynamic embedding sizing and support for longer token length, making it feasible to handle large-scale datasets efficiently.

An embedding model is a crucial component of a text retrieval system, as it transforms textual information into dense vector representations. They are typically transformer encoders that process tokens of input text (for example: question, passage) to output an embedding.

This model is ready for commercial use.

The Llama Nemotron Embedding 1B model is a part of the NVIDIA NeMo Retriever collection of NIM, which provide state-of-the-art, commercially-ready models and microservices, optimized for the lowest latency and highest throughput. It features a production-ready information retrieval pipeline with enterprise support. The models that form the core of this solution have been trained using responsibly selected, auditable data sources. With multiple pre-trained models available as starting points, developers can also readily customize them for domain-specific use cases, such as information technology, human resource help assistants, and research & development research assistants.

We are excited to announce the open sourcing of this commercial embedding model. For users interested in deploying this model in production environments, it is also available via the model API in NVIDIA Inference Microservices (NIM) at [llama-nemotron-embed-1b-v2](https://build.nvidia.com/nvidia/llama-3_2-nv-embedqa-1b-v2).

### **Intended use**

The Llama Nemotron Embedding 1B model is most suitable for users who want to build a multilingual question-and-answer application over a large text corpus, leveraging the latest dense retrieval technologies.

### **License/Terms of use**

Use of this model is governed by the [NVIDIA Open Model License Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/). Additional Information: [Llama 3.2 Community Model License Agreement](https://www.llama.com/llama3_2/license/).

### **Model Architecture**

**Architecture Type:** Transformer
**Network Architecture:** Fine-tuned Llama3.2 1B Retriever

This NeMo embedding model is a transformer encoder - a fine-tuned version of Llama3.2 1b, with 16 layers and an embedding size of 2048, which is trained on public datasets. The AdamW optimizer is employed incorporating 100 warm up steps and 5e-6 learning rate with WarmupDecayLR scheduler. Embedding models for text retrieval are typically trained using a bi-encoder architecture. This involves encoding a pair of sentences (for example, query and chunked passages) independently using the embedding model. Contrastive learning is used to maximize the similarity between the query and the passage that contains the answer, while minimizing the similarity between the query and sampled negative passages not useful to answer the question.

### **Input**

**Input Type:** Text
**Input Format:** List of strings
**Input Parameter:** 1D
**Other Properties Related to Input:** The model's maximum context length is 8192 tokens. Texts longer than maximum length must either be chunked or truncated.

### **Output**

**Output Type:** Floats
**Output Format:** List of float arrays
**Output:** Model outputs embedding vectors of maximum dimension 2048 for each text string (can be configured based on 384, 512, 768, 1024, or 2048).
**Other Properties Related to Output:** N/A

### **Installation**

### **Sentence Transformers Usage**

The model supports transformers versions 4.44 through 5.0+.

```bash
pip install transformers sentence-transformers
```

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("nvidia/llama-nemotron-embed-1b-v2", trust_remote_code=True)

queries = [
    "how much protein should a female eat",
    "summit define",
]
documents = [
    "As a general guideline, the CDC's average requirement of protein for women ages 19 to 70 is 46 grams per day. But, as you can see from this chart, you'll need to increase that if you're expecting or training for a marathon. Check out the chart below to see how much protein you should be eating each day.",
    "Definition of summit for English Language Learners. : 1  the highest point of a mountain : the top of a mountain. : 2  the highest level. : 3  a meeting or series of meetings between the leaders of two or more governments."
]

query_embeddings = model.encode_query(queries, convert_to_tensor=True)
document_embeddings = model.encode_document(documents, convert_to_tensor=True)

# Compute similarity scores
scores = model.similarity(query_embeddings, document_embeddings)
"""
tensor([[ 0.5968, -0.0454],
        [-0.0336,  0.4613]], device='cuda:0')
"""
```

### **Transformers Usage**
You can also use transformers directly to run the model. The model supports transformers versions 4.44 through 5.0+.

```bash
pip install transformers
```

```python
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

def average_pool(last_hidden_states, attention_mask):
    """Average pooling with attention mask."""
    last_hidden_states_masked = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
    embedding = last_hidden_states_masked.sum(dim=1) / attention_mask.sum(dim=1)[..., None]
    embedding = F.normalize(embedding, dim=-1)
    return embedding

tokenizer = AutoTokenizer.from_pretrained("nvidia/llama-nemotron-embed-1b-v2")
model = AutoModel.from_pretrained("nvidia/llama-nemotron-embed-1b-v2", trust_remote_code=True)
model = model.to("cuda:0")
model.eval()
query_prefix = "query:"
document_prefix = "passage:"

queries = [
    "how much protein should a female eat",
    "summit define",
]
documents = [
    "As a general guideline, the CDC's average requirement of protein for women ages 19 to 70 is 46 grams per day. But, as you can see from this chart, you'll need to increase that if you're expecting or training for a marathon. Check out the chart below to see how much protein you should be eating each day.",
    "Definition of summit for English Language Learners. : 1  the highest point of a mountain : the top of a mountain. : 2  the highest level. : 3  a meeting or series of meetings between the leaders of two or more governments."
]
queries = [f"{query_prefix} {query}" for query in queries]
documents = [f"{document_prefix} {document}" for document in documents]

batch_queries = tokenizer(queries, padding=True, truncation=True, return_tensors='pt').to("cuda:0")
batch_documents = tokenizer(documents, padding=True, truncation=True, return_tensors='pt').to("cuda:0")

with torch.no_grad():
    outputs_queries = model(**batch_queries)
    outputs_documents = model(**batch_documents)

# Average Pooling
embeddings_queries = average_pool(outputs_queries.last_hidden_state, batch_queries["attention_mask"])
print("Query embeddings:")
print(embeddings_queries)
print(embeddings_queries.shape)
#torch.Size([2, 2048])

embeddings_documents = average_pool(outputs_documents.last_hidden_state, batch_documents["attention_mask"])
print("\nDocument embeddings:")
print(embeddings_documents)
print(embeddings_documents.shape)
#torch.Size([2, 2048])

# Compute similarity scores
scores = (embeddings_queries @ embeddings_documents.T)
print("\nSimilarity scores:")
print(scores.tolist())

#Similarity scores:
#[[0.5968121290206909, -0.04534469544887543], [-0.03361201286315918, 0.46140915155410767]]
```

#### vLLM Usage

1. Ensure you are using `vllm==0.11.0`.
2. Clone [this model's repository](https://huggingface.co/nvidia/llama-nemotron-embed-1b-v2/tree/main).
3. Overwrite `config.json` with `config_vllm.json`.
4. Start the vLLM server with the following command (replace the `<path_to_the_cloned_repository>` and `<num_gpus_to_use>` with your values):
```
vllm serve \
    <path_to_the_cloned_repository> \
    --trust-remote-code \
    --runner pooling \
    --model-impl vllm \
    --override-pooler-config '{\"pooling_type\": \"MEAN\"}' \
    --data-parallel-size <num_gpus_to_use> \
    --dtype float32 \
    --port 8000
```

You can now access the model using the OpenAI sdk, for instance:

```
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1")
models = client.models.list()
model_name = models.data[0].id

response = client.embeddings.create(
    input=['query: summit define'],
    model=model_name
)
response.data[0].embedding
```

### **Software Integration**

**Runtime Engine:** Llama Nemotron embedding NIM
**Supported Hardware Microarchitecture Compatibility**: NVIDIA Ampere, NVIDIA Hopper, NVIDIA Lovelace
**Supported Operating System(s):** Linux

### **Model Version(s)**

Llama Nemotron Embedding 1B v2
Short Name: llama-nemotron-embed-1b-v2

## **Training Dataset & Evaluation**

### **Training Dataset**

The development of large-scale public open-QA datasets has enabled tremendous progress in powerful embedding models. However, one popular dataset named MS MARCO restricts ‌commercial licensing, limiting the use of these models in commercial settings. To address this, NVIDIA created its own training dataset blend based on public QA datasets, which each have a license for commercial applications.

**Data Collection Method by dataset**: Automated, Unknown

**Labeling Method by dataset**: Automated, Unknown

**Properties:** Semi-supervised pre-training on 12M samples from public datasets and fine-tuning on 1M samples from public datasets.

### **Evaluation Results**

Properties: We evaluated the NeMo Rtriever embdding model in comparison to literature open & commercial retriever models on academic benchmarks for question-answering - [NQ](https://huggingface.co/datasets/BeIR/nq), [HotpotQA](https://huggingface.co/datasets/hotpot_qa) and [FiQA (Finance Q\&A)](https://huggingface.co/datasets/BeIR/fiqa) from BeIR benchmark and TechQA dataset. Note that the model was evaluated offline on A100 GPUs using the model's PyTorch checkpoint.  In this benchmark, the metric used was Recall@5.

| Open & Commercial Retrieval Models | Average Recall@5 on NQ, HotpotQA, FiQA, TechQA dataset |
| ----- | ----- |
| llama-nemotron-embed-1b-v2 (embedding dim 2048) | 68.60% |
| llama-nemotron-embed-1b-v2 (embedding dim 384) | 64.48% |
| llama-3.2-nv-embedqa-1b-v1 (embedding dim 2048) | 68.97% |
| nv-embedqa-mistral-7b-v2 | 72.97% |
| nv-embedqa-mistral-7B-v1 | 64.93% |
| nv-embedqa-e5-v5 | 62.07% |
| nv-embedqa-e5-v4 | 57.65% |
| e5-large-unsupervised | 48.03% |
| BM25 | 44.67%  |

We evaluated the multilingual capabilities on the academic benchmark [MIRACL](https://github.com/project-miracl/miracl) across 15 languages and translated the English and Spanish version of MIRACL into additional 11 languages. The reported scores are based on an internal version of MIRACL by selecting hard negatives for each query to reduce the corpus size.

| Open & Commercial Retrieval Models | Average Recall@5 on multilingual |
| ----- | ----- |
| llama-nemotron-embed-1b-v2 (embedding dim 2048) | 60.75% |
| llama-nemotron-embed-1b-v2 (embedding dim 384) | 58.62% |
| llama-3.2-nv-embedqa-1b-v1 | 60.07% |
| nv-embedqa-mistral-7b-v2 | 50.42% |
| BM25 | 26.51% |

We evaluated the cross-lingual capabilities on the academic benchmark [MLQA](https://github.com/facebookresearch/MLQA/) based on 7 languages (Arabic, Chinese, English, German, Hindi, Spanish, Vietnamese). We consider only evaluation datasets when the query and documents are in different languages. We calculate the average Recall@5 across the 42 different language pairs.

| Open & Commercial Retrieval Models | Average Recall@5 on MLQA dataset with different languages |
| ----- | ----- |
| llama-nemotron-embed-1b-v2 (embedding dim 2048) | 79.86% |
| llama-nemotron-embed-1b-v2 (embedding dim 384) | 71.61% |
| llama-3.2-nv-embedqa-1b-v1 (embedding dim 2048) | 78.77% |
| nv-embedqa-mistral-7b-v2 | 68.38% |
| BM25 | 13.01% |

We evaluated the support of long documents on the academic benchmark [Multilingual Long-Document Retrieval (MLDR)](https://huggingface.co/datasets/Shitao/MLDR) built on Wikipedia and mC4, covering 12 typologically diverse languages. The English version has a median length of 2399 tokens and 90th percentile of 7483 tokens using the llama 3.2 tokenizer. The MLDR dataset is based on synthetic generated questions with a LLM, which has the tendency to create questions with similar keywords than the positive document, but might not be representative for real user queries. This characteristic of the dataset benefits sparse embeddings like BM25.

| Open & Commercial Retrieval Models | Average Recall@5 on MLDR |
| ----- | ----- |
| llama-nemotron-embed-1b-v2 (embedding dim 2048) | 59.55% |
| llama-nemotron-embed-1b-v2 (embedding dim 384) | 54.77% |
| llama-3.2-nv-embedqa-1b-v1 (embedding dim 2048) | 60.49% |
| nv-embedqa-mistral-7b-v2 | 43.24% |
| BM25 | 71.39% |

**Data Collection Method by dataset**: Unknown

**Labeling Method by dataset:** Unknown

**Properties:** The evaluation datasets are based on [MTEB/BEIR](https://github.com/beir-cellar/beir), TextQA, TechQA, [MIRACL](https://github.com/project-miracl/miracl), [MLQA](https://github.com/facebookresearch/MLQA), and [MLDR](https://huggingface.co/datasets/Shitao/MLDR). The size ranges between 10,000s up to 5M depending on the dataset.

**Inference**
**Engine:** TensorRT
**Test Hardware:** H100 PCIe/SXM, A100 PCIe/SXM, L40s, L4, and A10G

## **Citation**
```
@article{moreira2024nv,
  title={NV-Retriever: Improving text embedding models with effective hard-negative mining},
  author={Moreira, Gabriel de Souza P and Osmulski, Radek and Xu, Mengyao and Ak, Ronay and Schifferer, Benedikt and Oldridge, Even},
  journal={arXiv preprint arXiv:2407.15831},
  year={2024}
}
```

## **Ethical Considerations**

NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their supporting model team to ensure this model meets requirements for the relevant industry and use case and addresses unforeseen product misuse.

For more detailed information on ethical considerations for this model, please see the Model Card++ tab for the Explainability, Bias, Safety & Security, and Privacy subcards.

Please report security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/).

## Get Help

### Enterprise Support

Get access to knowledge base articles and support cases or  submit a ticket at the [NVIDIA AI Enterprise Support Services page.](https://www.nvidia.com/en-us/data-center/products/ai-enterprise-suite/support/).

### NVIDIA NIM Documentation
Visit the [NeMo Retriever docs page](https://docs.nvidia.com/nemo/retriever/index.html) for release documentation, deployment guides and more.

## Bias

| Field | Response |
| ----- | ----- |
| Participation considerations from adversely impacted groups [protected classes](https://www.senate.ca.gov/content/protected-classes) in model design and testing | None |
| Measures taken to mitigate against unwanted bias | None |

## Explainability

| Field | Response |
| ----- | ----- |
| Intended Application & Domain: | Passage and query embedding for question and answer retrieval |
| Model Type: | Transformer encoder |
| Intended User: | Generative AI creators working with conversational AI models - users who want to build a multilingual question and answer application over a large text corpus, leveraging the latest dense retrieval technologies. |
| Output: | Array of float numbers (Dense Vector Representation for the input text) |
| Describe how the model works: | Model transforms the tokenized input text into a dense vector representation. |
| Performance Metrics: | Accuracy, Throughput, and Latency |
| Potential Known Risks: | This model does not always guarantee to retrieve the correct passage(s) for a given query. |
| Licensing & Terms of Use: | Use of this model is governed by the [NVIDIA Open Model License Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/). Additional Information: [Llama 3.2 Community Model License Agreement](https://www.llama.com/llama3_2/license/). |
| Technical Limitations | The model’s max sequence length is 8192. Therefore, the longer text inputs should be truncated.   |
| Name the adversely impacted groups this has been tested to deliver comparable outcomes regardless of: | N/A |
| Verified to have met prescribed NVIDIA quality standards: | Yes |

## Privacy

| Field | Response |
| ----- | ----- |
| Generatable or reverse engineerable personally-identifiable information (PII)? | None |
| Was consent obtained for any personal data used? | Not Applicable |
| PII used to create this model? | None |
| How often is the dataset reviewed? | Before Every Release |
| Is a mechanism in place to honor data subject right of access or deletion of personal data? | No |
| If personal data was collected for the development of the model, was it collected directly by NVIDIA? | Not Applicable |
| If personal data was  collected for the development of the model by NVIDIA, do you maintain or have access to disclosures made to data subjects? | Not Applicable |
| If personal data was collected for the development of this AI model, was it minimized to only what was required? | Not Applicable |
| Is there provenance for all datasets used in training? | Yes |
| Does data labeling (annotation, metadata) comply with privacy laws? | Yes |
| Is data compliant with data subject requests for data correction or removal, if such a request was made? | No, not possible with externally-sourced data. |

## Safety

| Field | Response |
| ----- | ----- |
| Model Application(s): | Text Embedding for Retrieval |
| Describe the physical safety impact (if present). | Not Applicable |
| Use Case Restrictions: | Use of this model is governed by the [NVIDIA Open Model License Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/). Additional Information: [Llama 3.2 Community Model License Agreement](https://www.llama.com/llama3_2/license/).  |
| Model and dataset restrictions: | The Principle of least privilege (PoLP) is applied limiting access for dataset generation and model development. Restrictions enforce dataset access during training, and dataset license constraints adhered to. |

