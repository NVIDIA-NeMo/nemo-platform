<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Sample Datasets

This directory contains sample dataset files that users can select when creating new datasets.

## Directory Structure

```
sample-datasets/
├── qa-generation/
│   ├── training.jsonl
│   ├── validation.jsonl
│   └── test.jsonl
├── qa-generation-2/
│   ├── training.jsonl
│   ├── validation.jsonl
│   └── test.jsonl
└── qa-generation-3/
    ├── training.jsonl
    ├── validation.jsonl
    └── test.jsonl
```

## File Format Requirements

- Files should be in JSONL format (JSON Lines)
- Each line should contain a valid JSON object
- Files should follow the expected schema for your use case

## Adding New Sample Datasets

1. Create a new directory under `sample-datasets/` for your dataset
2. Add your dataset files to the directory
3. Update `packages/ui/src/constants/sampleDatasets.ts` to include your new dataset configuration
4. Ensure files are served correctly by your web server

## Example JSONL Format

```jsonl
{"input": "What is machine learning?", "output": "Machine learning is a subset of artificial intelligence..."}
{"input": "How does neural network work?", "output": "Neural networks are computing systems inspired by biological neural networks..."}
```

## File Size Considerations

- Keep individual files under 10MB for optimal loading performance
- Consider splitting large datasets into multiple files if needed
- Files are loaded entirely into memory when a user selects a sample dataset
