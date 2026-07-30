// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AnonymizerRecordView } from '@studio/components/AnonymizerRecordView/AnonymizerRecordView';
import { buildAnonymizerRecord } from '@studio/components/AnonymizerRecordView/parse';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const traceRow = {
  biography: 'Bobby, a 40-year-old veterinarian.',
  biography_replaced: 'Teddy, a 45-year-old veterinarian.',
  final_entities: {
    entities: [
      { value: 'Bobby', label: 'first_name', start_position: 0, end_position: 5 },
      { value: '40', label: 'age', start_position: 9, end_position: 11 },
    ],
  },
  _replacement_map: {
    replacements: [
      { original: 'Bobby', label: 'first_name', synthetic: 'Teddy' },
      { original: '40', label: 'age', synthetic: '45' },
    ],
  },
};

const renderRecord = (row: Record<string, unknown>, outputHeading = 'Replaced') =>
  render(
    <MemoryRouter>
      <AnonymizerRecordView
        outputHeading={outputHeading}
        record={buildAnonymizerRecord(row, 'biography')}
      />
    </MemoryRouter>
  );

describe('AnonymizerRecordView', () => {
  it('tags detected entities in both columns', () => {
    renderRecord(traceRow);

    expect(screen.getAllByText('Original').length).toBeGreaterThan(0);
    expect(screen.getByText('Replaced')).toBeInTheDocument();
    expect(screen.getAllByText('Bobby').length).toBeGreaterThan(0);
    expect(screen.getAllByText('first_name').length).toBeGreaterThan(0);
    expect(screen.getAllByText('45').length).toBeGreaterThan(0);
  });

  it('lists every replacement in the map', () => {
    renderRecord(traceRow);

    expect(screen.getByText('Replacement Map')).toBeInTheDocument();
    expect(screen.getAllByText('Teddy').length).toBeGreaterThan(0);
    expect(screen.getAllByText('age').length).toBeGreaterThan(0);
  });

  it('uses the caller heading for the output column', () => {
    renderRecord(traceRow, 'Rewritten');

    expect(screen.getByText('Rewritten')).toBeInTheDocument();
  });

  it('explains when nothing was replaced', () => {
    renderRecord({ biography: 'Nothing sensitive here.', biography_replaced: '' });

    expect(screen.getByText('No entities were replaced in this record.')).toBeInTheDocument();
    expect(screen.getByText('No output was produced for this record.')).toBeInTheDocument();
  });
});
