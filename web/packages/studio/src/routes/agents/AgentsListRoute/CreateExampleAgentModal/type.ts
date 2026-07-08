// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FormModalProps } from '@nemo/common/src/components/FormModal';
import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import type { sampleAgentFormSchema } from '@studio/constants/sampleAgents';
import type { z } from 'zod';

export type ExampleAgentFormData = z.infer<typeof sampleAgentFormSchema>;

export interface CreateExampleAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  existingAgents: Agent[];
}
