// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from 'react';

export type AgentBlockingInputStatus = 'pending' | 'submitting';

export interface AgentBlockingInputRequest {
  readonly description?: string;
  readonly id: string;
  readonly title: string;
}

export interface AgentBlockingInputSubmission {
  readonly displayText: string;
  readonly value: Record<string, unknown>;
}

export interface AgentBlockingInputSecondaryAction {
  readonly disabled?: boolean;
  readonly label: string;
  readonly onClick: () => Promise<void> | void;
}

export interface AgentBlockingInputFrameProps {
  readonly children: ReactNode;
  readonly isSubmitting?: boolean;
  readonly onSecondaryAction?: () => Promise<void> | void;
  readonly onSkip?: () => Promise<void> | void;
  readonly onSubmit: () => Promise<void> | void;
  readonly request: AgentBlockingInputRequest;
  readonly secondaryActions?: readonly AgentBlockingInputSecondaryAction[];
  readonly secondaryActionLabel?: string;
  readonly submitDisabled?: boolean;
  readonly submitLabel?: string;
}

export interface FilesetFileBlockingInputProps {
  readonly input?: Record<string, unknown>;
  readonly onSkip?: () => Promise<void> | void;
  readonly onSubmit: (submission: AgentBlockingInputSubmission) => Promise<void> | void;
  readonly request: AgentBlockingInputRequest;
  readonly status?: AgentBlockingInputStatus;
  readonly workspace: string;
}
