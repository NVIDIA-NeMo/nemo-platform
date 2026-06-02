// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export interface ClaudeCodeStreamHandlers {
  onClaudeEvent: (event: unknown) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export interface ClaudeCodeChatRouteState {
  initialPrompt?: string;
}
