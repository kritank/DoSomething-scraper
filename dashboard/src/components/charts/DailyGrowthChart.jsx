import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { formatSignedCompact } from '../../utils/format';

// The vidiq-style "Daily Subscriber Growth" view -- day-over-day change
// as green (gain) / red (loss) bars, distinct from GrowthChart's
// cumulative area above it. Points with daily_delta == null (the series'
// first day, or a gap where no snapshot was captured) are dropped rather
// than drawn as a 0-height bar, which would misleadingly read as "no
// change" instead of "no data."
export default function DailyGrowthChart({ points, label = 'Followers' }) {
  const data = useMemo(
    () => (points ?? []).filter((p) => p.daily_delta !== null && p.daily_delta !== undefined),
    [points]
  );

  const option = useMemo(() => {
    return {
      grid: { top: 20, right: 16, bottom: 36, left: 52 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: 'rgba(26, 26, 37, 0.85)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        padding: [10, 14],
        formatter: (params) => {
          const p = params[0];
          if (!p) return '';
          const val = p.value;
          const color = val >= 0 ? '#22c55e' : '#ef4444';
          const sign = val >= 0 ? '+' : '';
          const date = format(parseISO(p.axisValue), 'MMM d, yyyy');
          return `
            <div style="font-weight:600;margin-bottom:6px;">${date}</div>
            <div style="color:${color};font-weight:500;">
              ${sign}${formatSignedCompact(val)} daily ${label.toLowerCase()} change
            </div>`;
        }
      },
      xAxis: {
        type: 'category',
        data: data.map(p => p.date),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (val) => format(parseISO(val), 'MMM d'),
          color: '#8888a0',
          fontSize: 12,
        }
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.05)' } },
        axisLabel: {
          formatter: (val) => formatSignedCompact(val),
          color: '#8888a0',
          fontSize: 11,
        },
        // Always show a zero reference line by ensuring the axis crosses 0
        min: (value) => Math.min(value.min, 0),
        max: (value) => Math.max(value.max, 0),
      },
      series: [
        {
          type: 'bar',
          data: data.map(p => ({
            value: p.daily_delta,
            itemStyle: {
              color: p.daily_delta >= 0 ? 'rgba(34, 197, 94, 0.85)' : 'rgba(239, 68, 68, 0.85)',
              borderRadius: p.daily_delta >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
            }
          })),
          barMaxWidth: 28,
          emphasis: {
            itemStyle: {
              color: (params) =>
                data[params.dataIndex]?.daily_delta >= 0
                  ? 'rgba(34, 197, 94, 1)'
                  : 'rgba(239, 68, 68, 1)',
            }
          },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: 'rgba(255,255,255,0.15)', type: 'solid', width: 1 },
            data: [{ yAxis: 0 }],
            label: { show: false }
          }
        }
      ]
    };
  }, [data, label]);

  if (data.length === 0) {
    return (
      <EmptyState
        title="Not enough history yet"
        message="Daily change needs at least two consecutive days of snapshots to plot."
      />
    );
  }

  return (
    <div className="w-full h-48">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
