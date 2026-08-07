// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { AccordionSection } from '@nemo/common/src/components/AccordionSection';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { Anchor, Button, Flex, Stack, Switch, Text } from '@nvidia/foundations-react-core';
import { DetailRow } from '@studio/components/DetailRow';
import { AddToolForm } from '@studio/components/PromptTuningForm/ToolsSection/components/AddToolForm';
import { ToolMetadataPanel } from '@studio/components/PromptTuningForm/ToolsSection/components/ToolMetadataPanel';
import {
  AddToolFormFields,
  addToolFormSchema,
} from '@studio/components/PromptTuningForm/ToolsSection/components/validation';
import { TOOL_JSON_EXAMPLE } from '@studio/components/PromptTuningForm/ToolsSection/constants';
import { useSubmitSingleTool } from '@studio/components/PromptTuningForm/ToolsSection/hooks/useSubmitSingleTool';
import { PromptTuningFormFields } from '@studio/routes/PromptTuningFormRoute/utils';
import { handleFormErrorsGeneric } from '@studio/util/forms/error';
import { Plus, ExternalLink, Toolbox } from 'lucide-react';
import { FC, useState } from 'react';
import { FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form';

export interface ToolsSectionProps {
  isEditable?: boolean;
}

export const ToolsSection: FC<ToolsSectionProps> = ({ isEditable }) => {
  const parentForm = useFormContext<PromptTuningFormFields>();
  const addToolForm = useForm<AddToolFormFields>({
    resolver: zodResolver(addToolFormSchema),
    mode: 'onChange',
    defaultValues: {
      json: TOOL_JSON_EXAMPLE,
    },
  });
  const [openModal, setOpenModal] = useState<'import' | 'metadata' | undefined>();
  const [selectedTool, setSelectedTool] = useState<string>();
  const tools = useWatch({ control: parentForm.control, name: 'tools' }) ?? [];
  const toolsEnabled = useWatch({ control: parentForm.control, name: 'toolsEnabled' }) ?? true;
  const onSubmitSingleTool = useSubmitSingleTool(tools, parentForm, addToolForm);

  const resetAndClose = () => {
    addToolForm.reset();
    setOpenModal(undefined);
  };

  const handleToolsEnabledChange = (checked: boolean) => {
    parentForm.setValue('toolsEnabled', checked, { shouldValidate: true });
  };

  const handleViewToolMetadata = (name: string) => {
    setSelectedTool(name);
    setOpenModal('metadata');
  };

  const handleDeleteTool = (name: string) => {
    const currentTools = parentForm.getValues('tools') ?? [];
    const updatedTools = currentTools.filter((t) => t.function.name !== name);
    parentForm.setValue('tools', updatedTools, { shouldValidate: true });
  };

  return (
    <>
      <AccordionSection title="Tools" icon={<Toolbox size="var(--spacing-md)" />} value="tools">
        <Stack gap="density-lg">
          <p>
            Tools expand the capabilities of large language models by enabling access to external
            data and functionalities.
            <Anchor
              kind="standalone"
              href="https://docs.nvidia.com/nemo/microservices/latest/studio/models.html#tools"
              target="_blank"
              rel="noreferrer"
            >
              <Text kind="label/bold/sm">Learn more about tool calling</Text>
              <ExternalLink />
            </Anchor>
          </p>
          {tools.length > 0 && (
            <Flex justify="between" align="center">
              <Text kind="label/semibold/md">Tools Enabled</Text>
              <Switch checked={toolsEnabled ?? false} onCheckedChange={handleToolsEnabledChange} />
            </Flex>
          )}
          {tools.map((tool) => (
            <DetailRow
              key={tool.function.name}
              label={tool.function.name}
              onView={handleViewToolMetadata}
              onDelete={handleDeleteTool}
              isEditable={isEditable}
              disabled={!toolsEnabled}
            />
          ))}
          {isEditable && (
            <Button
              kind="secondary"
              type="button"
              onClick={() => setOpenModal('import')}
              className="w-full"
            >
              <Plus />
              Add Tools
            </Button>
          )}
        </Stack>
      </AccordionSection>

      {openModal === 'import' && (
        <FormProvider {...addToolForm}>
          <FormModal
            open={openModal === 'import'}
            onClose={resetAndClose}
            title={
              <Flex gap="density-md" align="center">
                <Toolbox />
                Add an LLM Tool
              </Flex>
            }
            className="w-[800px]"
            disabled={addToolForm.formState.isSubmitting}
            loading={addToolForm.formState.isSubmitting}
            submitButtonText="Save"
            onSubmit={addToolForm.handleSubmit(
              async (data) => {
                const success = await onSubmitSingleTool(data);
                if (success) {
                  resetAndClose();
                }
              },
              handleFormErrorsGeneric({ title: 'Add Tool Form Errors' })
            )}
          >
            <AddToolForm disabled={addToolForm.formState.isSubmitting} />
          </FormModal>
        </FormProvider>
      )}
      {openModal === 'metadata' && (
        <ToolMetadataPanel
          open={openModal === 'metadata'}
          tool={tools.find((t) => t.function.name === selectedTool)}
          onClose={() => setOpenModal(undefined)}
        />
      )}
    </>
  );
};
