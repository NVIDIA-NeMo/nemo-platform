// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { filesDownloadFile } from '@nemo/sdk/generated/platform/api';
import { Button, Spinner } from '@nvidia/foundations-react-core';
import { type FilesetRef } from '@studio/routes/optimizer/OptimizerEvalAuthorRunRoute/artifactUtils';
import { Download } from 'lucide-react';
import { type FC } from 'react';

interface ArtifactCodeProps {
  content: string | undefined;
  loading: boolean;
  contentType?: ContentType;
  emptyMessage: string;
}

export const ArtifactCode: FC<ArtifactCodeProps> = ({
  content,
  loading,
  contentType = ContentType.JSON,
  emptyMessage,
}) => {
  if (loading) {
    return <Spinner aria-label="Loading artifact" description="Loading artifact..." />;
  }
  if (content === undefined) {
    return <div className="text-secondary">{emptyMessage}</div>;
  }
  return (
    <CodeEditor
      className="min-h-[320px] max-h-[640px]"
      content={content}
      contentType={contentType}
      readOnly
    />
  );
};

interface DownloadArtifactButtonProps {
  fileset: FilesetRef;
  path: string;
}

export const DownloadArtifactButton: FC<DownloadArtifactButtonProps> = ({ fileset, path }) => {
  const download = async () => {
    const blob = await filesDownloadFile(fileset.workspace, fileset.name, path);
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = href;
    link.download = path.split('/').at(-1) ?? 'artifact';
    link.click();
    URL.revokeObjectURL(href);
  };

  return (
    <Button kind="secondary" size="small" onClick={() => void download()}>
      <Download />
      Download
    </Button>
  );
};
