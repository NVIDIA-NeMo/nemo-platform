// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { Flex, PageHeader, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { logger } from '@studio/util/logger';
import { FileX } from 'lucide-react';
import { ComponentProps, FC, ReactNode, useEffect } from 'react';
import { useRouteError, isRouteErrorResponse } from 'react-router-dom';

const DEFAULT_ERROR_MESSAGE =
  'An unexpected error occurred.\nPlease contact your Administrator for support.';

export interface ErrorPanelProps {
  /** The title displayed in the header */
  title?: ReactNode;
  /** The error message to display. If you need greater control over the error message, use attributes.ErrorMessage to pass props to the ErrorMessage component directly. */
  errorMessage?: string;
  /** Props to pass to the ErrorMessage component */
  attributes?: {
    ErrorMessage?: ComponentProps<typeof ErrorMessage>;
  };
}

/**
 * Extracts a user-friendly error message from various error types.
 */
const getRouterErrorMessage = (error: unknown): string | undefined => {
  if (isRouteErrorResponse(error)) {
    return error.statusText || `Error ${error.status}`;
  } else if (error instanceof Error) {
    return getErrorMessage(error);
  }

  return undefined;
};

const getErrorCode = (error: unknown): string | undefined => {
  if (isRouteErrorResponse(error)) {
    return error.status.toString();
  }
};

/**
 * Generic error panel component for React Router's errorElement.
 *
 * Use this as the errorElement in your route configuration to display
 * error UI with a custom title and error message attributes.
 *
 * @example
 * ```tsx
 * // In your route configuration:
 * {
 *   path: ROUTES.workspace.evaluation,
 *   element: <EvaluationLayout />,
 *   errorElement: <ErrorPanel title="Evaluator" />,
 * }
 *
 * // With custom error message props:
 * {
 *   path: ROUTES.workspace.filesets,
 *   element: <FilesetLayout />,
 *   errorElement: (
 *     <ErrorPanel
 *       title="Data Store"
 *       attributes={{
 *         slotMedia: <CustomIcon />,
 *         slotFooter: <CustomFooter />,
 *       }}
 *     />
 *   ),
 * }
 * ```
 */
export const ErrorPanel: FC<ErrorPanelProps> = ({ title, errorMessage, attributes }) => {
  const error = useRouteError();
  const errorCode = getErrorCode(error);
  const errorMessageInternal =
    errorMessage ?? getRouterErrorMessage(error) ?? DEFAULT_ERROR_MESSAGE;

  // Log the error on mount
  useEffect(() => {
    if (error) {
      const logMessage = JSON.stringify(errorMessage, null, 2);
      logger.error(logMessage);
    }
  }, [error, errorMessage, title]);

  const message = (
    <Stack gap="2">
      <Text kind="body/regular/md" className="whitespace-pre-wrap">
        {errorMessageInternal}
      </Text>
    </Stack>
  );

  return (
    <Stack className="h-full" padding="4" gap="3">
      <PageHeader slotHeading={title} />
      <Panel className="flex-1 justify-center" elevation="high">
        <Flex
          align="center"
          justify="center"
          className="h-full w-full p-8"
          data-testid="error-panel"
        >
          <ErrorMessage
            slotMedia={<FileX className="size-16" />}
            header={<Text kind="title/md">Error{errorCode ? `: ${errorCode}` : ''}</Text>}
            message={message}
            {...attributes?.ErrorMessage}
          />
        </Flex>
      </Panel>
    </Stack>
  );
};
