// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { useFilePreview } from '@nemo/common/src/components/DatasetFileSelect/hooks/useFilePreview';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { FileList, FileListItem } from '@nemo/common/src/components/FileList';
import { getEntityReference, getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import {
  useFilesListFilesets as useListFilesets,
  useFilesRetrieveFileset,
} from '@nemo/sdk/generated/platform/api';
import { FilesetOutput as Fileset } from '@nemo/sdk/generated/platform/schema';
import {
  Anchor,
  Block,
  Button,
  FormField,
  SelectContent,
  SelectItem,
  SelectRoot,
  SelectTrigger,
  SidePanel,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { CustomizationFilesetCreateModal } from '@studio/components/CustomizationFilesetCreateModal';
import { FileValidationPanel } from '@studio/components/customizer/CustomizationFilesetSelect/FileValidationPanel';
import { PatternsTooltipTrigger } from '@studio/components/customizer/CustomizationFilesetSelect/FileValidationPanel/PatternsTooltip';
import { Loading } from '@studio/components/Layouts/Loading';
import { CustomizationFormFields } from '@studio/components/NewCustomizationForm';
import { LINK_DOCS_FINE_TUNE_DATASET_FORMAT_REQUIREMENTS } from '@studio/constants/links';
import { useCustomizationDatasetValidation } from '@studio/hooks/useCustomizationDatasetValidation';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { inferJsonContentType, isJsonFile } from '@studio/util/files';
import { Database, FolderOpen } from 'lucide-react';
import { FC, useMemo, useState } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

const NEW_DATASET_VALUE = '__new_dataset__';

export interface CustomizationFilesetSelectProps {
  disabled?: boolean;
  onImportSubmit: (data: Fileset) => void;
}

export const CustomizationFilesetSelect: FC<CustomizationFilesetSelectProps> = ({
  disabled,
  onImportSubmit,
}) => {
  const workspace = useWorkspaceFromPath();
  const [openModal, setOpenModal] = useState<'create' | undefined>();

  const {
    data: filesetsResponse,
    isPending,
    isFetching,
    error,
  } = useListFilesets(workspace, {
    // Pull the largest page the backend allows for client-side filtering.
    // The filesets endpoint caps page_size at 100 (validates with 422 on
    // larger values — DEFAULT_LARGE_PAGE_SIZE = 1000 fails). Once server-side
    // search lands, drop this and paginate properly.
    page_size: 100,
    sort: 'created_at',
    filter: { purpose: 'dataset' },
  });
  const filesets = useMemo(() => filesetsResponse?.data ?? [], [filesetsResponse?.data]);
  const dropdownDisabled = isPending || isFetching || !!error;

  const { control } = useFormContext<CustomizationFormFields>();
  const selectedFilesetBase = useWatch({ control, name: 'dataset' });
  const trainingType = useWatch({ control, name: 'training.type' });
  const filesetURN = getURNFromNamedEntityRef(selectedFilesetBase);

  const {
    data: fileset,
    status: fetchFilesetStatus,
    refetch: refetchFileset,
  } = useFilesRetrieveFileset(
    selectedFilesetBase?.workspace ?? '',
    selectedFilesetBase?.name ?? '',
    { query: { enabled: !!(selectedFilesetBase?.workspace && selectedFilesetBase?.name) } }
  );

  const validation = useCustomizationDatasetValidation({
    fileset: filesetURN,
    trainingType,
  });
  const { training, validation: validationFiles } = validation;

  const onCreate = (createdFileset: Fileset) => {
    onImportSubmit(createdFileset);
    setOpenModal(undefined);
  };

  const handleSelectChange = (value: string) => {
    if (value === NEW_DATASET_VALUE) {
      setOpenModal('create');
      return;
    }
    const picked = filesets.find((f) => getEntityReference(f) === value);
    if (picked) {
      onImportSubmit(picked);
    }
  };

  const selectedDropdownValue = selectedFilesetBase
    ? getEntityReference(selectedFilesetBase)
    : undefined;

  // File preview state and content fetching
  const {
    previewFile,
    previewContent,
    isLoadingPreview,
    previewError,
    setPreviewFile,
    clearPreview,
  } = useFilePreview();

  // FileList items: training files first, then validation files. The
  // FileValidationPanel handles error/info banners separately.
  const filesetFiles = useMemo<FileListItem[]>(() => {
    if (fetchFilesetStatus !== 'success') return [];
    return [...training, ...validationFiles].map((file) => ({
      path: file.path,
      dataset: fileset ?? undefined,
      rowCount: file.rowCount,
    }));
  }, [training, validationFiles, fileset, fetchFilesetStatus]);

  const {
    formState: { errors },
  } = useFormContext<CustomizationFormFields>();

  const hasMissingTrainingFiles =
    !validation.hasTraining && !validation.isPending && selectedDropdownValue;

  return (
    <Stack gap="density-2xl">
      <Text kind="label/bold/lg">Training Data</Text>
      <Text kind="body/regular/md">
        Datasets should be in JSONL format and split into separate, representative training and
        validation sets. For formatting guidelines, refer to the{' '}
        <Anchor
          href={LINK_DOCS_FINE_TUNE_DATASET_FORMAT_REQUIREMENTS}
          target="_blank"
          rel="noopener noreferrer"
        >
          Dataset Format Requirements
        </Anchor>
        .
      </Text>

      <FormField
        slotLabel="Dataset"
        slotError={
          errors.dataset?.message ??
          (hasMissingTrainingFiles
            ? 'No training files were found in this dataset. Customizer needs at least one training file to start fine-tuning.'
            : undefined)
        }
        status={errors.dataset || hasMissingTrainingFiles ? 'error' : undefined}
      >
        {/* Compound Select form (rather than `<Select items={...}>`) so the
            per-item className on the New Dataset row is honored — the items
            array drops className silently. */}
        <SelectRoot
          value={selectedDropdownValue}
          onValueChange={handleSelectChange}
          disabled={disabled || dropdownDisabled}
        >
          <SelectTrigger
            aria-label="dataset-select"
            placeholder="Select a dataset"
            slotStart={
              selectedDropdownValue && selectedDropdownValue !== NEW_DATASET_VALUE ? (
                <Database width={16} height={16} className="text-fg-subdued" />
              ) : undefined
            }
          />
          <SelectContent>
            {filesets.map((f) => {
              const ref = getEntityReference(f);
              return (
                <SelectItem key={ref} value={ref}>
                  {f.name ?? ''}
                </SelectItem>
              );
            })}
            {/* Visually offsets the create-new action from the dataset list. */}
            <SelectItem className="border-t border-base" value={NEW_DATASET_VALUE}>
              New Dataset
            </SelectItem>
          </SelectContent>
        </SelectRoot>
      </FormField>

      {fetchFilesetStatus === 'pending' && selectedFilesetBase?.name && (
        <Block paddingX="density-md">
          <Loading description="Dataset loading..." />
        </Block>
      )}

      {fetchFilesetStatus === 'error' && (
        <Block paddingX="density-md">
          <ErrorMessage
            header="Loading Error"
            message="This dataset was unable to load. Please try again."
            slotFooter={<Button onClick={() => refetchFileset()}>Retry</Button>}
          />
        </Block>
      )}

      {fetchFilesetStatus === 'success' && filesetFiles.length > 0 && (
        <FileList files={filesetFiles} allowDelete={false} onPreviewFile={setPreviewFile} />
      )}

      {/* Always visible. Sits between the matched files list (above) and the
          auto-split + File Validation sections (below) so users can read the
          discovery rules right where they need them. When no fileset is
          selected yet, the file list is absent and the tooltip naturally sits
          right below the dropdown. */}
      <PatternsTooltipTrigger
        label={hasMissingTrainingFiles ? undefined : 'How are files matched within the Dataset?'}
      />
      {fetchFilesetStatus === 'success' && <FileValidationPanel validation={validation} />}

      {openModal === 'create' && (
        <CustomizationFilesetCreateModal
          open
          onClose={() => setOpenModal(undefined)}
          onFilesetCreated={onCreate}
        />
      )}

      {previewFile && (
        <SidePanel
          slotHeading={
            <div className="flex gap-2 items-center">
              <FolderOpen />
              {previewFile.dataset
                ? `${previewFile.dataset.workspace}/${previewFile.dataset.name}/${previewFile.path}`
                : previewFile.path}
            </div>
          }
          side="right"
          open
          onOpenChange={clearPreview}
          onEscapeKeyDown={(e) => {
            e.preventDefault();
            clearPreview();
          }}
          onPointerDownOutside={(e) => {
            e.preventDefault();
            clearPreview();
          }}
          attributes={{
            SidePanelHeading: { className: 'font-normal' },
          }}
          bordered
          modal
          className="max-w-[960px] w-full"
        >
          {/* Use the same CodeEditor the Fileset browser uses for previews —
              it virtualizes content so multi-MB JSONL files render without
              freezing the browser. The lightweight FileContentPreview from
              @nemo/common runs Shiki on the entire string and hangs above
              ~1 MB. */}
          {previewError ? (
            <div className="flex h-full items-center justify-center text-red-600">
              Error loading file: {previewError.message}
            </div>
          ) : isLoadingPreview ? (
            <div className="flex h-full items-center justify-center">
              <span>Loading content...</span>
            </div>
          ) : (
            <div className="h-full">
              <CodeEditor
                content={previewContent ?? ''}
                contentType={
                  isJsonFile(inferJsonContentType(previewFile.path))
                    ? ContentType.JSON
                    : ContentType.TEXT
                }
                readOnly
              />
            </div>
          )}
        </SidePanel>
      )}
    </Stack>
  );
};
