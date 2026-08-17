<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Customizer Service Agentic Flows

The Customizer service provides model fine-tuning capabilities including LoRA, full SFT, DPO, and Knowledge Distillation. It supports distributed training across multiple nodes.

**PIC**: Aaron Gabow
**Priority**: Medium

---

## Flows

| # | Flow Name | Complexity | MCP Eval | CLI Eval | Description | Source |
|---|-----------|------------|----------|----------|-------------|--------|
| 17a | Basic LoRA Customization Job | 4 | No | No | Upload a dataset, create a customization job with LoRA fine-tuning, wait for completion, verify the output model appears in entity store. | POR |
| 17b | Full SFT | 4 | No | No | Upload a dataset, create a customization job with full SFT, wait for completion, verify the output model appears in entity store. | POR |
| 17c | DPO | 4 | No | No | Upload a DPO dataset, create a customization job with DPO, wait for completion, verify the output model appears in entity store. | POR |
| 17d | Knowledge Distillation | 4 | No | No | Upload a dataset, create a customization job with KD, wait for completion, verify the output model appears in entity store. | POR |
| 18 | Chat-Format Dataset Customization | 4 | No | No | Fine-tune a model using chat-format messages (system/user/assistant) dataset instead of prompt/completion format. | POR |
| 19 | Multi-Node Customization Flow | 5 | No | No | Configure and run a multi-node customization job (tensor parallelism across nodes). Verify successful completion and model quality. | POR |

---

## Flow Details

### 17a. Basic LoRA Customization Job

**Complexity**: 4 (Complex)

**Operations**:
1. Upload training dataset to Files service
2. Create customization configuration for LoRA
3. Launch customization job
4. Monitor job progress
5. Wait for completion
6. Verify output model in entity store

**Prerequisites**:
- Dataset in correct format (JSONL)
- Base model available
- GPU resources allocated

**Success Criteria**:
- Customization job created
- Job runs without errors
- Output model (LoRA adapter) saved
- Model appears in entity store

---

### 17b. Full SFT

**Complexity**: 4 (Complex)

**Operations**:
1. Upload training dataset to Files service
2. Create customization configuration for full SFT
3. Launch customization job
4. Monitor job progress
5. Wait for completion
6. Verify full weight model in entity store

**Prerequisites**:
- Dataset in correct format
- Base model available
- Sufficient GPU memory for full weights

**Success Criteria**:
- Full SFT job completes
- Output model weights saved to Files service
- Model can be deployed via IGW

---

### 17c. DPO

**Complexity**: 4 (Complex)

**Operations**:
1. Upload DPO-format dataset (chosen/rejected pairs)
2. Create customization configuration for DPO
3. Launch DPO job
4. Monitor and wait for completion
5. Verify output model

**DPO Dataset Format**:
```json
{"prompt": "...", "chosen": "...", "rejected": "..."}
```

**Prerequisites**:
- DPO-format dataset
- Base model available
- GPU resources

**Success Criteria**:
- DPO job completes
- Model shows preference alignment
- Output model saved

---

### 17d. Knowledge Distillation

**Complexity**: 4 (Complex)

**Operations**:
1. Upload dataset
2. Configure teacher model
3. Create KD customization job
4. Monitor training
5. Verify student model output

**Prerequisites**:
- Teacher model accessible
- Training dataset
- GPU resources for both models

**Success Criteria**:
- KD job completes
- Student model created
- Student approximates teacher behavior

---

### 18. Chat-Format Dataset Customization

**Complexity**: 4 (Complex)

**Operations**:
1. Prepare chat-format dataset with messages array
2. Upload to Files service
3. Configure customization for chat format
4. Run customization job
5. Verify output model handles chat format

**Chat Dataset Format**:
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Prerequisites**:
- Chat-format dataset
- Chat-capable base model

**Success Criteria**:
- Job processes chat format correctly
- Output model improved on chat tasks

---

### 19. Multi-Node Customization Flow

**Complexity**: 5 (Advanced)

**Operations**:
1. Configure multi-node training parameters
2. Set up tensor parallelism across nodes
3. Launch distributed customization job
4. Monitor all nodes
5. Verify checkpoint synchronization
6. Validate final model quality

**Prerequisites**:
- Multiple GPU nodes available
- Distributed training configuration
- Large model requiring multi-node

**Success Criteria**:
- All nodes participate in training
- Checkpoints synchronized
- Final model quality matches expectations
- No node failures

---

## Documentation References

- LoRA tutorial: docs/customizer/tutorials/lora-customization-job.md
- Data format: docs/customizer/models/data-format.md
- Training dataset format: docs/customizer/tutorials/format-training-dataset.md
- Create config: docs/customizer/manage-customization-configs/create-config.md
- Distillation tutorial: docs/customizer/tutorials/distillation-customization-job.md
