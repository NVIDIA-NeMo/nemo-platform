// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { Button, Flex, Tag, Text } from '@nvidia/foundations-react-core';
import type { StartOptionTag } from '@studio/components/CreateFilesetStart/types';
import type { JobBuilderFormValues } from '@studio/routes/DataDesignerJobBuildRoute/useJobBuilder';
import { FileJson, Pencil } from 'lucide-react';
import { type FC, useState } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

export interface BuilderToolbarProps {
  /** The template's badge (recipe use case), shown when building from a template. */
  templateTag?: StartOptionTag;
  columnCount: number;
  onPreview: () => void;
  isPreviewing: boolean;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export const BuilderToolbar: FC<BuilderToolbarProps> = ({
  templateTag,
  columnCount,
  onPreview,
  isPreviewing,
  onSubmit,
  isSubmitting,
}) => {
  const [isEditingName, setIsEditingName] = useState(false);
  const { control } = useFormContext<JobBuilderFormValues>();
  const name = useWatch({ control, name: 'name' }) ?? '';
  const rows = useWatch({ control, name: 'rows' }) ?? '';
  const previewRows = Number(rows) > 0 ? Math.min(Number(rows), 10) : 10;

  return (
    <Flex
      align="center"
      justify="between"
      gap="density-lg"
      className="shrink-0 border-b border-base bg-surface-base px-density-2xl py-density-md"
    >
      <Flex align="center" gap="density-sm" className="min-w-0">
        <FileJson size={20} className="shrink-0 text-secondary" aria-hidden />
        {isEditingName ? (
          <ControlledTextInput
            autoFocus
            useControllerProps={{ name: 'name' }}
            onBlur={() => setIsEditingName(false)}
            formFieldProps={{ className: 'w-[220px]' }}
            attributes={{ Input: { 'aria-label': 'Fileset name' } }}
          />
        ) : (
          <Text kind="label/bold/md" className="whitespace-nowrap">
            {name}
          </Text>
        )}
        <Button
          kind="tertiary"
          color="neutral"
          size="small"
          aria-label="Rename fileset"
          onClick={() => setIsEditingName(true)}
        >
          <Pencil size={14} aria-hidden />
        </Button>
        {templateTag && (
          <Tag color={templateTag.color} kind={templateTag.kind} readOnly>
            {templateTag.label}
          </Tag>
        )}
        <Text className="text-secondary" aria-hidden>
          ·
        </Text>
        <Text kind="body/regular/sm" className="text-secondary whitespace-nowrap">
          {columnCount} {columnCount === 1 ? 'column' : 'columns'}
        </Text>
      </Flex>

      <Flex align="center" gap="density-md">
        <Flex align="center" gap="density-sm">
          <Text kind="body/regular/sm" className="text-secondary whitespace-nowrap">
            Rows
          </Text>
          <ControlledTextInput
            useControllerProps={{ name: 'rows' }}
            formFieldProps={{ className: 'w-[96px]' }}
            attributes={{
              Input: {
                'aria-label': 'Records to generate',
                min: 1,
                step: 1,
                type: 'number',
              },
            }}
          />
        </Flex>
        <LoadingButton
          kind="secondary"
          color="neutral"
          loading={isPreviewing}
          onClick={onPreview}
        >{`Preview ${previewRows} rows`}</LoadingButton>
        <LoadingButton kind="primary" color="brand" loading={isSubmitting} onClick={onSubmit}>
          Create fileset
        </LoadingButton>
      </Flex>
    </Flex>
  );
};
