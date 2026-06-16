// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CustomizationFileUpload } from '@studio/components/CustomizationFileUpload';
import {
  CUSTOMIZATION_FILESET_FILE_PREFIXES,
  CustomizationFileType,
} from '@studio/constants/customization';
import { mockFile } from '@studio/mocks/studio-ui/files';
import { render, screen } from '@studio/tests/util/render';

describe('CustomizationFileUpload', () => {
  it('renders without error', () => {
    render(
      <CustomizationFileUpload
        customizationFileType={CustomizationFileType.Training}
        required
        accept={{ 'image/jpeg': ['.jpeg'] }}
      />
    );
    expect(screen.getByText('Drop a file or click to select a file')).toBeInTheDocument();
  });

  it.each([[CustomizationFileType.Training], [CustomizationFileType.Validation]])(
    'should show the correct file tag for %s',
    (customizationFileType) => {
      const mockOnChange = vi.fn();
      render(
        <CustomizationFileUpload
          customizationFileType={customizationFileType}
          required
          accept={{ 'image/jpeg': ['.jpeg'] }}
          files={[mockFile]}
          onChange={mockOnChange}
        />
      );
      expect(
        screen.getByText(
          `${CUSTOMIZATION_FILESET_FILE_PREFIXES[customizationFileType]}/${mockFile.name}`
        )
      ).toBeInTheDocument();
    }
  );
});
