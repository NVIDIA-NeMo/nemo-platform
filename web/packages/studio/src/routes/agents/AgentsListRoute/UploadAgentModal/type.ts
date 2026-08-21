// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FormModalProps } from '@nemo/common/src/components/FormModal';
import type { uploadAgentFormSchema } from '@studio/routes/agents/AgentsListRoute/UploadAgentModal/const';
import type { z } from 'zod';

export type UploadAgentFormData = z.infer<typeof uploadAgentFormSchema>;

/** A file plus the path it was picked or dropped under, still including the root directory. */
export interface PickedFile {
  file: File;
  relativePath: string;
}

/** A picked file paired with its path inside the agent spec fileset. */
export interface UploadAgentEntry {
  path: string;
  file: File;
}

export interface UploadAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
}
