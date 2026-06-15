// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FormModalProps } from '@nemo/common/src/components/FormModal';
import type { AgentTableRow } from '@studio/components/dataViews/AgentsDataView';
import type { cloneAgentFormSchema } from '@studio/routes/agents/AgentsListRoute/CloneAgentModal/const';
import type { z } from 'zod';

export type CloneAgentFormData = z.infer<typeof cloneAgentFormSchema>;

export interface CloneAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  sourceAgent: AgentTableRow | null;
}
