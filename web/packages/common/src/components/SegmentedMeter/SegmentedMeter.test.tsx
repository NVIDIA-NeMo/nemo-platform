// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SegmentedMeter } from '@nemo/common/src/components/SegmentedMeter';
import { fireEvent, render, screen } from '@testing-library/react';

describe('SegmentedMeter', () => {
  it('renders nothing when there are no segments', () => {
    const { container } = render(<SegmentedMeter segments={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when every segment value is zero', () => {
    const { container } = render(
      <SegmentedMeter
        segments={[
          { value: 0, color: '#888888' },
          { value: 0, color: '#22c55e' },
        ]}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders one bar per segment with the given color', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 62, color: '#6b7280' },
          { value: 34, color: '#4ade80' },
          { value: 4, color: '#84cc16' },
        ]}
      />
    );

    const bars = screen.getAllByTestId('segmented-meter-segment');
    expect(bars).toHaveLength(3);
    expect(bars[0]).toHaveStyle({ backgroundColor: '#6b7280' });
    expect(bars[1]).toHaveStyle({ backgroundColor: '#4ade80' });
    expect(bars[2]).toHaveStyle({ backgroundColor: '#84cc16' });
  });

  it('sizes segments proportionally to their value', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 62, color: '#6b7280' },
          { value: 34, color: '#4ade80' },
          { value: 4, color: '#84cc16' },
        ]}
      />
    );

    const bars = screen.getAllByTestId('segmented-meter-segment');
    expect(bars[0].style.flexGrow).toBe('62');
    expect(bars[1].style.flexGrow).toBe('34');
    expect(bars[2].style.flexGrow).toBe('4');
  });

  it('renders captions only for segments that have one, in document order', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 62, color: '#6b7280', caption: '62% zero' },
          { value: 34, color: '#4ade80' },
          { value: 4, color: '#84cc16', caption: '4% max' },
        ]}
      />
    );

    expect(screen.getByText('62% zero')).toBeInTheDocument();
    expect(screen.getByText('4% max')).toBeInTheDocument();
    expect(screen.getAllByText(/%/)).toHaveLength(2);
  });

  it('does not render a caption row when no segment has a caption', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 62, color: '#6b7280' },
          { value: 4, color: '#84cc16' },
        ]}
      />
    );

    expect(screen.queryByTestId('segmented-meter-captions')).not.toBeInTheDocument();
  });

  it('shows only the hovered segment caption while hovering, hiding the others', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 62, color: '#6b7280', caption: '62% zero' },
          { value: 34, color: '#4ade80' },
          { value: 4, color: '#84cc16', caption: '4% max' },
        ]}
      />
    );

    const bars = screen.getAllByTestId('segmented-meter-segment');
    fireEvent.mouseEnter(bars[2]);

    expect(screen.getByText('4% max')).toBeInTheDocument();
    expect(screen.queryByText('62% zero')).not.toBeInTheDocument();
  });

  it('reverts to the default caption row after the mouse leaves the segment', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 62, color: '#6b7280', caption: '62% zero' },
          { value: 34, color: '#4ade80' },
          { value: 4, color: '#84cc16', caption: '4% max' },
        ]}
      />
    );

    const bars = screen.getAllByTestId('segmented-meter-segment');
    fireEvent.mouseEnter(bars[2]);
    fireEvent.mouseLeave(bars[2]);

    expect(screen.getByText('62% zero')).toBeInTheDocument();
    expect(screen.getByText('4% max')).toBeInTheDocument();
  });

  it('shows only the first and last captions by default when every segment has one', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 20, color: '#6b7280', caption: '20% zero' },
          { value: 20, color: '#84cc16', caption: '20% low' },
          { value: 20, color: '#22c55e', caption: '20% typical' },
          { value: 20, color: '#eab308', caption: '20% high' },
          { value: 20, color: '#ef4444', caption: '20% outliers' },
        ]}
      />
    );

    expect(screen.getByText('20% zero')).toBeInTheDocument();
    expect(screen.getByText('20% outliers')).toBeInTheDocument();
    expect(screen.queryByText('20% low')).not.toBeInTheDocument();
    expect(screen.queryByText('20% typical')).not.toBeInTheDocument();
    expect(screen.queryByText('20% high')).not.toBeInTheDocument();
  });

  it('reveals a middle segment caption on hover even when it is hidden by default', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 20, color: '#6b7280', caption: '20% zero' },
          { value: 20, color: '#84cc16', caption: '20% low' },
          { value: 20, color: '#22c55e', caption: '20% typical' },
          { value: 20, color: '#eab308', caption: '20% high' },
          { value: 20, color: '#ef4444', caption: '20% outliers' },
        ]}
      />
    );

    const bars = screen.getAllByTestId('segmented-meter-segment');
    fireEvent.mouseEnter(bars[2]);

    expect(screen.getByText('20% typical')).toBeInTheDocument();
    expect(screen.queryByText('20% zero')).not.toBeInTheDocument();
    expect(screen.queryByText('20% outliers')).not.toBeInTheDocument();
  });

  it('keeps the default caption row when hovering a segment without a caption', () => {
    render(
      <SegmentedMeter
        segments={[
          { value: 62, color: '#6b7280', caption: '62% zero' },
          { value: 34, color: '#4ade80' },
          { value: 4, color: '#84cc16', caption: '4% max' },
        ]}
      />
    );

    const bars = screen.getAllByTestId('segmented-meter-segment');
    fireEvent.mouseEnter(bars[1]);

    expect(screen.getByText('62% zero')).toBeInTheDocument();
    expect(screen.getByText('4% max')).toBeInTheDocument();
  });
});
