// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FileFormatType } from '@nemo/common/src/types';
import type {
  FileFormatDetectionResult,
  FileValidationResult,
} from '@nemo/common/src/utils/fileValidation';
import type { DatasetKeyMapping } from '@studio/components/DatasetInputFile/types';
import { useReducer } from 'react';

/** Location of the dataset file (for cached-content lookups and preview) */
export interface DatasetLocation {
  workspace: string;
  name: string;
  path: string;
}

/** File-level metadata needed once validation completes */
export interface FileMetadata {
  format: FileFormatType;
  firstRow: Record<string, unknown>;
  parsedRows: Record<string, unknown>[];
  rowCount: number;
}

export interface DatasetInputFileState {
  uploadModalOpen: boolean;
  previewModalOpen: boolean;
  isValidating: boolean;
  fileUrl: string | null;
  datasetLocation: DatasetLocation | null;
  validationResult: FileValidationResult | null;
  detectionResult: FileFormatDetectionResult;
  availableKeys: Array<{ label: string; value: string }>;
  keyMapping: DatasetKeyMapping;
  fileMetadata: FileMetadata | null;
}

export type DatasetInputFileAction =
  | { type: 'RESET' }
  | { type: 'SET_UPLOAD_MODAL_OPEN'; payload: boolean }
  | { type: 'SET_PREVIEW_MODAL_OPEN'; payload: boolean }
  | {
      type: 'FILE_SELECTED';
      payload: { fileUrl: string; datasetLocation: DatasetLocation };
    }
  | { type: 'VALIDATION_FAILED'; payload: FileValidationResult }
  | {
      type: 'VALIDATION_SUCCEEDED';
      payload: {
        validationResult: FileValidationResult;
        detectionResult: FileFormatDetectionResult;
        availableKeys: Array<{ label: string; value: string }>;
        keyMapping: DatasetKeyMapping;
        fileMetadata: FileMetadata;
      };
    }
  | {
      type: 'SET_KEY_MAPPING_FIELD';
      payload: { field: keyof DatasetKeyMapping; value: string | null };
    };

export const initialState: DatasetInputFileState = {
  uploadModalOpen: false,
  previewModalOpen: false,
  isValidating: false,
  fileUrl: null,
  datasetLocation: null,
  validationResult: null,
  detectionResult: null,
  availableKeys: [],
  keyMapping: { promptKey: null, completionKey: null, idealResponseKey: null },
  fileMetadata: null,
};

export const datasetInputFileReducer = (
  state: DatasetInputFileState,
  action: DatasetInputFileAction
): DatasetInputFileState => {
  switch (action.type) {
    case 'RESET':
      // Preserve modal-open flags when resetting file state? No — clearing the
      // file also dismisses any open preview. Upload modal is handled separately.
      return initialState;

    case 'SET_UPLOAD_MODAL_OPEN':
      return { ...state, uploadModalOpen: action.payload };

    case 'SET_PREVIEW_MODAL_OPEN':
      return { ...state, previewModalOpen: action.payload };

    case 'FILE_SELECTED':
      // New file incoming — reset file-related state and enter validating mode
      return {
        ...initialState,
        uploadModalOpen: false,
        isValidating: true,
        fileUrl: action.payload.fileUrl,
        datasetLocation: action.payload.datasetLocation,
      };

    case 'VALIDATION_FAILED':
      return {
        ...state,
        isValidating: false,
        validationResult: action.payload,
      };

    case 'VALIDATION_SUCCEEDED':
      return {
        ...state,
        isValidating: false,
        validationResult: action.payload.validationResult,
        detectionResult: action.payload.detectionResult,
        availableKeys: action.payload.availableKeys,
        keyMapping: action.payload.keyMapping,
        fileMetadata: action.payload.fileMetadata,
      };

    case 'SET_KEY_MAPPING_FIELD':
      return {
        ...state,
        keyMapping: {
          ...state.keyMapping,
          [action.payload.field]: action.payload.value,
        },
      };

    default:
      return state;
  }
};

export const useDatasetInputFileReducer = (state?: DatasetInputFileState) =>
  useReducer(datasetInputFileReducer, state ?? initialState);
