/**
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import type { ReactNode } from "react";

export const DATA_DESIGNER_DOCS_VERSION = "v0.7.0";

const DATA_DESIGNER_DOCS_BASE_URL = `https://docs.nvidia.com/nemo/datadesigner/${DATA_DESIGNER_DOCS_VERSION}`;

export interface DataDesignerDocsLinkProps {
  path: string;
  children: ReactNode;
}

export function dataDesignerDocsUrl(path: string) {
  const normalizedPath = path.replace(/^\/+/, "");
  return `${DATA_DESIGNER_DOCS_BASE_URL}/${normalizedPath}`;
}

export function DataDesignerDocsLink({
  path,
  children,
}: DataDesignerDocsLinkProps) {
  return (
    <a href={dataDesignerDocsUrl(path)} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

export default DataDesignerDocsLink;
