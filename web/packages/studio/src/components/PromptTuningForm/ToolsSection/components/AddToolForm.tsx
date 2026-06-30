// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { Button, Flex, FormField, Stack } from '@nvidia/foundations-react-core';
import { AddToolFormFields } from '@studio/components/PromptTuningForm/ToolsSection/components/validation';
import { Info } from 'lucide-react';
import { type FC, useCallback } from 'react';
import { Controller, useFormContext } from 'react-hook-form';

interface AddToolFormProps {
  disabled?: boolean;
}

export const AddToolForm: FC<AddToolFormProps> = ({ disabled }) => {
  const {
    control,
    setValue,
    formState: { errors },
  } = useFormContext<AddToolFormFields>();

  // Handle file upload and auto-fill form fields
  const handleFileUpload = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        // Always populate the JSON editor with the file content
        setValue('json', text, { shouldValidate: true, shouldDirty: true });
      };
      reader.readAsText(file);
    },
    [setValue]
  );

  return (
    <Stack gap="density-xl">
      {/* JSON Parameters Field */}
      <Controller
        name="json"
        control={control}
        render={({ field: { onChange, value } }) => (
          <FormField
            slotLabel="Tool Definition"
            status={errors.json ? 'error' : undefined}
            slotError={errors.json?.message}
            slotHelp={
              <Flex gap="density-xs" align="center">
                <Info height={12} width={12} /> JSON schema defining the function's input arguments
                using the OpenAI compatible function format.
              </Flex>
            }
          >
            {() => (
              <CodeEditor
                content={value || '{}'}
                contentType={ContentType.JSON}
                readOnly={disabled || false}
                onChange={(newContent) => onChange(newContent)}
                className="min-h-[300px] max-h-[600px] overflow-y-auto"
              />
            )}
          </FormField>
        )}
      />

      {/* File Upload for Auto-fill */}
      <Controller
        name="file"
        control={control}
        render={({ field: { onChange }, fieldState: { error } }) => {
          const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
            const file = e.target.files?.[0] || null;
            onChange(file);
            if (file) {
              handleFileUpload(file);
            }
          };
          return (
            <FormField
              status={error ? 'error' : undefined}
              slotError={error?.message}
              className="mt-density-lg"
            >
              {() => (
                <Button kind="secondary" type="button" disabled={disabled} asChild>
                  <label htmlFor="upload-button">
                    Upload Tool Definition File
                    <input
                      id="upload-button"
                      className="sr-only peer"
                      type="file"
                      accept=".json,.jsonl"
                      onChange={handleFileChange}
                      disabled={disabled}
                      aria-label="Upload tool definition file"
                    />
                  </label>
                </Button>
              )}
            </FormField>
          );
        }}
      />
    </Stack>
  );
};
