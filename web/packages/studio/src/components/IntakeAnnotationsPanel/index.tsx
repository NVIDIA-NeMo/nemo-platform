// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import {
  getListAnnotationsQueryKey,
  useCreateAnnotation,
  useDeleteAnnotation,
  useListAnnotations,
} from '@nemo/sdk/generated/platform/api';
import {
  AnnotationSortField,
  FeedbackAnnotationInputKind,
  FeedbackAnnotationInputValue,
  NoteAnnotationInputKind,
  type Annotation,
  type FeedbackAnnotationInputValue as FeedbackAnnotationInputValueType,
} from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  CodeSnippet,
  Flex,
  FormField,
  Panel,
  Stack,
  Text,
  TextArea,
} from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { ThumbButton } from '@studio/components/buttons/ThumbButton';
import { useQueryClient } from '@tanstack/react-query';
import { MessageSquarePlus, NotebookPen, Trash2 } from 'lucide-react';
import { type FC, useMemo, useState } from 'react';
import { type SubmitHandler, useForm } from 'react-hook-form';
import { z } from 'zod';

const noteSchema = z.object({
  text: z.string().trim().min(1, 'Note is required.'),
});

type NoteFormValues = z.infer<typeof noteSchema>;

const getAnnotationErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? getErrorMessage(error, fallback) : fallback;

const formatAnnotationTitle = (annotation: Annotation): string => {
  switch (annotation.kind) {
    case 'feedback':
      return annotation.value === 'positive' ? 'Positive feedback' : 'Negative feedback';
    case 'note':
      return 'Note';
    case 'label':
      return annotation.name ? `Label: ${annotation.name}` : 'Label';
    case 'metadata':
      return 'Metadata';
  }
};

const renderAnnotationBody = (annotation: Annotation) => {
  switch (annotation.kind) {
    case 'feedback':
      return (
        <Text kind="body/regular/sm" className="capitalize">
          {annotation.value}
        </Text>
      );
    case 'note':
      return (
        <Text kind="body/regular/sm" className="whitespace-pre-wrap break-words">
          {annotation.text}
        </Text>
      );
    case 'label':
      return (
        <Text kind="body/regular/sm" className="break-words">
          {String(annotation.value)}
        </Text>
      );
    case 'metadata':
      return (
        <CodeSnippet
          value={JSON.stringify(annotation.metadata, null, 2)}
          language="json"
          kind="block"
          collapsible
          defaultOpen={false}
          attributes={{
            CodeSnippetCode: {
              className:
                'max-h-[220px] [&_code]:whitespace-pre-wrap [&_code]:break-words [&_pre]:whitespace-pre-wrap',
            },
          }}
        />
      );
  }
};

export interface IntakeAnnotationsPanelProps {
  workspace: string;
  spanId: string;
  sessionId: string;
}

export const IntakeAnnotationsPanel: FC<IntakeAnnotationsPanelProps> = ({
  workspace,
  spanId,
  sessionId,
}) => {
  const queryClient = useQueryClient();
  const [mutationError, setMutationError] = useState<string | undefined>();
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isValid },
  } = useForm<NoteFormValues>({
    resolver: zodResolver(noteSchema),
    defaultValues: { text: '' },
    mode: 'onChange',
  });

  const listParams = useMemo(
    () => ({
      page: 1,
      page_size: 100,
      sort: AnnotationSortField['-created_at'],
      filter: {
        span_id: spanId,
      },
    }),
    [spanId]
  );

  const {
    data: annotationsResponse,
    error: listError,
    isLoading,
  } = useListAnnotations(workspace, listParams);
  const createAnnotation = useCreateAnnotation();
  const deleteAnnotation = useDeleteAnnotation();

  const noteText = watch('text');
  const annotations = annotationsResponse?.data ?? [];
  const activeFeedback = annotations.find((annotation) => annotation.kind === 'feedback');
  const isMutating = createAnnotation.isPending || deleteAnnotation.isPending;

  const refreshAnnotations = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: getListAnnotationsQueryKey(workspace),
    });
  };

  const handleFeedback = async (value: FeedbackAnnotationInputValueType): Promise<void> => {
    setMutationError(undefined);
    try {
      await createAnnotation.mutateAsync({
        workspace,
        data: {
          kind: FeedbackAnnotationInputKind.feedback,
          value,
          session_id: sessionId,
          span_id: spanId,
        },
      });
      await refreshAnnotations();
    } catch (error) {
      setMutationError(getAnnotationErrorMessage(error, 'Failed to save feedback.'));
    }
  };

  const handleNoteSubmit: SubmitHandler<NoteFormValues> = async ({ text }) => {
    setMutationError(undefined);
    try {
      await createAnnotation.mutateAsync({
        workspace,
        data: {
          kind: NoteAnnotationInputKind.note,
          text,
          session_id: sessionId,
          span_id: spanId,
        },
      });
      reset();
      await refreshAnnotations();
    } catch (error) {
      setMutationError(getAnnotationErrorMessage(error, 'Failed to save note.'));
    }
  };

  const handleDelete = async (annotationId: string): Promise<void> => {
    setMutationError(undefined);
    try {
      await deleteAnnotation.mutateAsync({
        workspace,
        annotationId,
      });
      await refreshAnnotations();
    } catch (error) {
      setMutationError(getAnnotationErrorMessage(error, 'Failed to delete annotation.'));
    }
  };

  return (
    <Panel
      elevation="high"
      slotIcon={<NotebookPen />}
      slotHeading="Annotations"
      className="min-w-0 overflow-hidden"
    >
      <Stack gap="density-xl" className="min-w-0">
        <Stack gap="density-sm">
          <Text kind="label/bold/sm">Feedback</Text>
          <Flex gap="density-sm" wrap="wrap">
            <ThumbButton
              direction="up"
              selected={activeFeedback?.value === 'positive'}
              disabled={isMutating}
              onClick={() => void handleFeedback(FeedbackAnnotationInputValue.positive)}
            >
              Positive
            </ThumbButton>
            <ThumbButton
              direction="down"
              selected={activeFeedback?.value === 'negative'}
              disabled={isMutating}
              onClick={() => void handleFeedback(FeedbackAnnotationInputValue.negative)}
            >
              Negative
            </ThumbButton>
          </Flex>
        </Stack>

        <form onSubmit={(event) => void handleSubmit(handleNoteSubmit)(event)}>
          <Stack gap="density-sm">
            <FormField
              name="annotation-note"
              slotLabel="Note"
              slotError={errors.text?.message}
              status={errors.text && 'error'}
            >
              <TextArea
                value={noteText}
                placeholder="Add a note about this span."
                disabled={isMutating}
                status={errors.text && 'error'}
                resizeable="manual"
                attributes={{
                  TextAreaElement: {
                    rows: 3,
                  },
                }}
                {...register('text')}
              />
            </FormField>
            <Flex justify="end">
              <Button type="submit" disabled={isMutating || !isValid}>
                <MessageSquarePlus />
                Add Note
              </Button>
            </Flex>
          </Stack>
        </form>

        {(mutationError || listError) && (
          <Text kind="body/regular/sm" className="text-danger">
            {mutationError ?? getAnnotationErrorMessage(listError, 'Failed to load annotations.')}
          </Text>
        )}

        <Stack gap="density-md" className="min-w-0">
          <Text kind="label/bold/sm">History</Text>
          {isLoading ? (
            <Text kind="body/regular/sm" className="text-secondary">
              Loading annotations...
            </Text>
          ) : annotations.length === 0 ? (
            <Text kind="body/regular/sm" className="text-secondary">
              No annotations yet.
            </Text>
          ) : (
            annotations.map((annotation) => (
              <div
                key={annotation.annotation_id}
                role="article"
                aria-label={`${formatAnnotationTitle(annotation)} annotation`}
                className="min-w-0 rounded-md border border-base bg-surface-raised p-density-lg"
              >
                <Stack gap="density-sm" className="min-w-0">
                  <Flex align="start" justify="between" gap="density-md">
                    <Stack gap="density-xxs" className="min-w-0">
                      <Text kind="label/bold/sm" className="break-words">
                        {formatAnnotationTitle(annotation)}
                      </Text>
                      <Text kind="body/regular/xs" className="text-secondary">
                        {formatAbsoluteTimestamp(annotation.created_at)}
                      </Text>
                    </Stack>
                    <Button
                      size="small"
                      kind="tertiary"
                      disabled={isMutating}
                      onClick={() => void handleDelete(annotation.annotation_id)}
                    >
                      <Trash2 />
                      Delete
                    </Button>
                  </Flex>
                  {renderAnnotationBody(annotation)}
                </Stack>
              </div>
            ))
          )}
        </Stack>
      </Stack>
    </Panel>
  );
};
