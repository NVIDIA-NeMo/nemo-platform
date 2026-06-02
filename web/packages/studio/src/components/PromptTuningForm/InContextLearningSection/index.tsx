// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { FileContentPreview } from '@nemo/common/src/components/FileContentPreview';
import { FileList, FileListItem } from '@nemo/common/src/components/FileList';
import { UploadModal } from '@nemo/common/src/components/UploadModal';
import { compileSystemPrompt } from '@nemo/common/src/models/utils';
import { Button, Flex, SidePanel, Stack, Text } from '@nvidia/foundations-react-core';
import { AccordionSection } from '@studio/components/AccordionSection';
import {
  ImportFileContentFormFields,
  importFileContentSchema,
} from '@studio/components/ImportFileContent/validation';
import { useSubmitICLsFile } from '@studio/components/PromptTuningForm/InContextLearningSection/hooks/useSubmitICLsFile';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  PromptTuningFormFields,
  PromptTuningFormSectionProps,
} from '@studio/routes/PromptTuningFormRoute/utils';
import { Plus, CircleCheckBig, File } from 'lucide-react';
import { FC, useId, useMemo, useState } from 'react';
import { useForm, useFormContext, useWatch } from 'react-hook-form';

export const InContextLearningSection: FC<PromptTuningFormSectionProps> = ({ isEditable }) => {
  const workspace = useWorkspaceFromPath();
  const parentForm = useFormContext<PromptTuningFormFields>();
  const importFileForm = useForm<ImportFileContentFormFields>({
    resolver: zodResolver(importFileContentSchema),
    mode: 'onChange',
  });
  const [openModal, setOpenModal] = useState<'import' | 'view' | undefined>(undefined);
  const [selectedICL, setSelectedICL] = useState<{ fileName: string; content?: string }>();
  const previewPanelId = useId();
  const iclFewShotExamples = useWatch({ control: parentForm.control, name: 'iclFewShotExamples' });
  const systemPromptTemplate =
    useWatch({
      control: parentForm.control,
      name: 'systemPromptTemplate',
    }) ?? '';
  const onImportFileSubmit = useSubmitICLsFile(parentForm, importFileForm);

  // Convert ICL format to FileListItem format for FileList
  const iclAsFileItems: FileListItem[] = useMemo(() => {
    return (iclFewShotExamples || []).map((icl) => ({
      path: icl.fileName,
      content: icl.content,
    }));
  }, [iclFewShotExamples]);

  const handleDeleteICL = (filePath: string) => {
    const updatedICLs = iclFewShotExamples?.filter((icl) => icl.fileName !== filePath);
    const updatedSystemPrompt = compileSystemPrompt({
      systemPromptTemplate,
      iclFewShotExamples: updatedICLs?.map((icl) => icl.content).join('\n'),
    }).prompt;
    parentForm.setValue('systemPrompt', updatedSystemPrompt, { shouldValidate: true });
    parentForm.setValue('iclFewShotExamples', updatedICLs, { shouldValidate: true });
  };

  const handlePreviewFile = (file: FileListItem) => {
    setSelectedICL({ fileName: file.path, content: file.content });
    setOpenModal('view');
  };

  const resetAndClose = () => {
    importFileForm.reset();
    setOpenModal(undefined);
  };

  return (
    <AccordionSection value="learning-examples" title="Learning Examples" icon={<CircleCheckBig />}>
      <Stack gap="density-lg">
        <p>
          Examples help the Model understand the context and the desired output by providing
          references for possible inputs and outputs.
        </p>

        {iclAsFileItems.length > 0 && (
          <FileList
            files={iclAsFileItems}
            onDeleteFile={handleDeleteICL}
            onPreviewFile={handlePreviewFile}
            label="Examples"
          />
        )}

        {isEditable && (
          <Button
            className="w-full"
            disabled={parentForm.formState.disabled}
            kind="secondary"
            type="button"
            onClick={() => setOpenModal('import')}
          >
            <Plus />
            Import Examples
          </Button>
        )}
      </Stack>
      <SidePanel
        id={previewPanelId}
        className="w-[800px]"
        bordered
        modal
        open={openModal === 'view'}
        onOpenChange={() => setOpenModal(undefined)}
        slotHeading={
          <Flex align="center" gap="density-sm">
            <File />
            <Text kind="title/xs">{selectedICL?.fileName}</Text>
          </Flex>
        }
      >
        {selectedICL && (
          <FileContentPreview
            file={{ path: selectedICL.fileName, content: selectedICL.content }}
            content={selectedICL.content}
            isLoading={false}
            error={null}
          />
        )}
      </SidePanel>

      {openModal === 'import' && !parentForm.formState.disabled && (
        <UploadModal
          open
          onClose={resetAndClose}
          workspace={workspace}
          includeTabs
          title="Add Learning Examples"
          submitButtonText="Confirm"
          onSubmit={async (data) => {
            if (data.type === 'dataset') {
              const success = await onImportFileSubmit({
                datasetId: `${data.dataset.workspace}/${data.dataset.name}`,
                filepath: data.path,
              });
              if (success) {
                resetAndClose();
              }
            } else if (data.type === 'file') {
              const success = await onImportFileSubmit({
                file: data.files?.[0],
              });
              if (success) {
                resetAndClose();
              }
            }
          }}
        />
      )}
    </AccordionSection>
  );
};
