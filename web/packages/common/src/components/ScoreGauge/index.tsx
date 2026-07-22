// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

type ScoreGaugeSize = 'lg' | 'sm';

export const SCORE_TIER_COLORS = {
  Excellent: '#22c55e',
  'Very Good': '#84cc16',
  Good: '#eab308',
  Moderate: '#f97316',
  Poor: '#ef4444',
} as const;

export type ScoreTier = keyof typeof SCORE_TIER_COLORS | 'Unavailable';

const UNAVAILABLE_COLOR = '#888888';

const GRADIENT_PALETTE: [number, number, number][] = [
  [239, 68, 68],
  [249, 115, 22],
  [234, 179, 8],
  [132, 204, 22],
  [34, 197, 94],
];

export function scoreTier(score: number): ScoreTier {
  if (!Number.isFinite(score) || score <= 0) return 'Unavailable';
  if (score >= 8) return 'Excellent';
  if (score >= 6) return 'Very Good';
  if (score >= 4) return 'Good';
  if (score >= 2) return 'Moderate';
  return 'Poor';
}

export function scoreColor(score: number): string {
  const tier = scoreTier(score);
  return tier === 'Unavailable' ? UNAVAILABLE_COLOR : SCORE_TIER_COLORS[tier];
}

const CENTER = 50;
const RADIUS = 38;
const ARC_START = 135;
const ARC_SWEEP = 270;

function point(angleDeg: number): { x: number; y: number } {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: CENTER + RADIUS * Math.cos(rad), y: CENTER + RADIUS * Math.sin(rad) };
}

function arcPath(fromPct: number, toPct: number): string {
  const a0 = ARC_START + (ARC_SWEEP * fromPct) / 100;
  const a1 = ARC_START + (ARC_SWEEP * toPct) / 100;
  const p0 = point(a0);
  const p1 = point(a1);
  const largeArc = a1 - a0 > 180 ? 1 : 0;
  return `M ${p0.x} ${p0.y} A ${RADIUS} ${RADIUS} 0 ${largeArc} 1 ${p1.x} ${p1.y}`;
}

function interpolate(t: number): string {
  const position = t * (GRADIENT_PALETTE.length - 1);
  const low = Math.floor(position);
  const high = Math.min(low + 1, GRADIENT_PALETTE.length - 1);
  const ratio = position - low;
  const [r, g, b] = GRADIENT_PALETTE[low].map((value, index) =>
    Math.round(value + (GRADIENT_PALETTE[high][index] - value) * ratio)
  );
  return `rgb(${r}, ${g}, ${b})`;
}

const GRADIENT_SEGMENTS = 120;

const gradientSegments = Array.from({ length: GRADIENT_SEGMENTS }, (_, index) => ({
  d: arcPath((index / GRADIENT_SEGMENTS) * 100, ((index + 1) / GRADIENT_SEGMENTS) * 100),
  stroke: interpolate(index / (GRADIENT_SEGMENTS - 1)),
}));

interface ScoreGaugeProps {
  /** Raw score on a 0-10 scale. Falsy / non-finite renders as unavailable. */
  score?: number;
  size?: ScoreGaugeSize;
  /** Scales the gauge to fit its parent while keeping a square aspect ratio. */
  scaleToFit?: boolean;
}

export const ScoreGauge = ({ score, size = 'lg', scaleToFit = false }: ScoreGaugeProps) => {
  const available = typeof score === 'number' && Number.isFinite(score) && score > 0;
  const clamped = available ? Math.min(Math.max(score, 0), 10) : 0;
  const percentage = clamped * 10;
  const display = available ? clamped.toFixed(1) : '—';

  const dimension = size === 'lg' ? 220 : 56;
  const strokeWidth = size === 'lg' ? 12 : 6;

  return (
    <div
      role="img"
      aria-label={available ? `Score: ${display} out of 10` : 'Score unavailable'}
      /* eslint-disable-next-line no-restricted-syntax */
      style={
        scaleToFit
          ? {
              width: '100%',
              height: '100%',
              maxWidth: dimension,
              maxHeight: dimension,
              aspectRatio: 1,
            }
          : { width: dimension, height: dimension }
      }
    >
      <svg
        width={scaleToFit ? '100%' : dimension}
        height={scaleToFit ? '100%' : dimension}
        viewBox="0 0 100 100"
        /* eslint-disable-next-line no-restricted-syntax */
        style={{ display: 'block' }}
      >
        {size === 'lg' && available ? (
          gradientSegments.map((segment, index) => (
            <path
              key={index}
              d={segment.d}
              fill="none"
              stroke={segment.stroke}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              data-testid="gauge-gradient-segment"
            />
          ))
        ) : (
          <>
            <path
              d={arcPath(0, 100)}
              fill="none"
              stroke="var(--background-color-accent-gray)"
              strokeWidth={strokeWidth}
              strokeLinecap="round"
            />
            {available && (
              <path
                d={arcPath(0, percentage)}
                fill="none"
                stroke={scoreColor(clamped)}
                strokeWidth={strokeWidth}
                strokeLinecap="round"
                data-testid="gauge-progress"
              />
            )}
          </>
        )}

        {size === 'lg' && available && (
          <g data-testid="gauge-marker">
            <circle
              cx={point(ARC_START + (ARC_SWEEP * percentage) / 100).x}
              cy={point(ARC_START + (ARC_SWEEP * percentage) / 100).y}
              r={strokeWidth / 2 + 2}
              fill="none"
              stroke="rgba(255, 255, 255, 0.5)"
              strokeWidth={2}
            />
            <circle
              cx={point(ARC_START + (ARC_SWEEP * percentage) / 100).x}
              cy={point(ARC_START + (ARC_SWEEP * percentage) / 100).y}
              r={strokeWidth / 2}
              fill="#ffffff"
              stroke="rgba(0, 0, 0, 0.35)"
              strokeWidth={1}
            />
          </g>
        )}

        <text
          x={CENTER}
          y={size === 'lg' ? 48 : 52}
          textAnchor="middle"
          dominantBaseline="central"
          data-testid="gauge-display"
          /* eslint-disable-next-line no-restricted-syntax */
          style={{
            fontSize: size === 'lg' ? 26 : 24,
            fontWeight: 700,
            fill: available ? 'currentColor' : 'var(--background-color-accent-gray)',
          }}
        >
          {display}
        </text>
        {size === 'lg' && (
          <text
            x={CENTER}
            y={64}
            textAnchor="middle"
            dominantBaseline="central"
            /* eslint-disable-next-line no-restricted-syntax */
            style={{ fontSize: 9, fontWeight: 500, fill: 'currentColor', fillOpacity: 0.6 }}
          >
            of 10
          </text>
        )}
      </svg>
    </div>
  );
};
