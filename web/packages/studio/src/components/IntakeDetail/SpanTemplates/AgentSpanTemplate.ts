// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AgentSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/AgentSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Agent: task in, result out — no model/usage at this level. */
export const agentSpanTemplate: SpanTemplate = {
  Content: AgentSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
  attributeNamespaces: ['agent'],
};
