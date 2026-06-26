// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToolSpanContent } from '@studio/components/IntakeDetail/SpanTemplates/ToolSpanContent';
import type { SpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/types';

/** Tool: arguments in, result out — no model/usage. */
export const toolSpanTemplate: SpanTemplate = {
  Content: ToolSpanContent,
  sections: ['kind', 'input', 'output', 'metadata', 'annotations'],
  attributeNamespaces: ['tool'],
};
