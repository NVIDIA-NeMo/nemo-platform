// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Banner,
  Panel,
  TableBody,
  TableDataCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
  Text,
} from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { parseArtifactUrl } from '@studio/routes/AnonymizerJobDetailRoute/util';
import { useMemo, type FC } from 'react';

interface FailedRecordsPanelProps {
  readonly workspace: string;
  readonly artifactUrl: string | undefined;
}

interface FailedRecord {
  readonly record_id?: string;
  readonly step?: string;
  readonly reason?: string;
}

export const FailedRecordsPanel: FC<FailedRecordsPanelProps> = ({ workspace, artifactUrl }) => {
  const location = parseArtifactUrl(artifactUrl);

  const { data, error } = useDatasetFileContent({
    workspace,
    name: location?.fileset ?? '',
    path: `${location?.basePath}/failed_records.json`,
    // Pretty-printed JSON array: the size-capped preview truncates mid-array and the parse
    // below then silently yields zero records, hiding every failure.
    fullContent: true,
    enabled: !!location,
  });

  const records = useMemo<FailedRecord[]>(() => {
    try {
      const parsed = JSON.parse(data ?? '[]');
      return Array.isArray(parsed) ? (parsed as FailedRecord[]) : [];
    } catch {
      return [];
    }
  }, [data]);

  if (error || !records.length) return null;

  return (
    <Panel slotHeading={`Failed Records (${records.length})`} elevation="high" density="compact">
      <Banner kind="inline" status="warning">
        These records were dropped during processing and are absent from the results.
      </Banner>
      <TableRoot className="bg-transparent w-full mt-density-md" align="left">
        <TableHead>
          <TableRow>
            <TableHeaderCell>Record</TableHeaderCell>
            <TableHeaderCell>Step</TableHeaderCell>
            <TableHeaderCell>Reason</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {records.map((record, index) => (
            <TableRow key={record.record_id ?? index}>
              <TableDataCell>
                <Text kind="body/regular/sm">{record.record_id ?? '—'}</Text>
              </TableDataCell>
              <TableDataCell>{record.step ?? '—'}</TableDataCell>
              <TableDataCell>{record.reason ?? '—'}</TableDataCell>
            </TableRow>
          ))}
        </TableBody>
      </TableRoot>
    </Panel>
  );
};
