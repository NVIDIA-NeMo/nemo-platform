// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { logger } from '@nemo/common/src/utils/logger';
import { Button } from '@nvidia/foundations-react-core';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ChatThreadErrorBoundaryProps {
  onRetry: () => void;
  children: ReactNode;
}

interface ChatThreadErrorBoundaryState {
  error: Error | null;
}

// A failed chunk load throws during render; without this it unwinds to the root
// and blanks all of Studio, not just the pop-out.
export class ChatThreadErrorBoundary extends Component<
  ChatThreadErrorBoundaryProps,
  ChatThreadErrorBoundaryState
> {
  state: ChatThreadErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ChatThreadErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    logger.error(`Assistant chat thread failed to render: ${error.message}`, info.componentStack);
  }

  private retry = (): void => {
    this.setState({ error: null });
    this.props.onRetry();
  };

  render(): ReactNode {
    if (!this.state.error) return this.props.children;

    return (
      <ErrorMessage
        header="Chat failed to load"
        message="Check your connection and try again."
        slotFooter={
          <Button kind="secondary" onClick={this.retry}>
            Try Again
          </Button>
        }
      />
    );
  }
}
