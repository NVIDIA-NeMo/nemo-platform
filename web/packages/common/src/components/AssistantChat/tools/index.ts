// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  StudioTool,
  StudioToolRegistry,
} from '@nemo/common/src/components/AssistantChat/tools/types';
import { webSearchTool } from '@nemo/common/src/components/AssistantChat/tools/webSearch';

export {
  setWebSearchProvider,
  type WebSearchProvider,
} from '@nemo/common/src/components/AssistantChat/tools/webSearch';
export type {
  AssistantChatTool,
  StudioTool,
  StudioToolRegistry,
  ToolExecutionContext,
  ToolExecutionOutcome,
} from '@nemo/common/src/components/AssistantChat/tools/types';
export {
  getAssistantChatToolName,
  isStudioTool,
  toOpenAITool,
} from '@nemo/common/src/components/AssistantChat/tools/types';

export const DEFAULT_STUDIO_TOOLS: StudioToolRegistry = [webSearchTool];

export const findStudioTool = (
  registry: StudioToolRegistry,
  name: string
): StudioTool | undefined => registry.find((tool) => tool.name === name);
