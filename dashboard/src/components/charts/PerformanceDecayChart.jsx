import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import EmptyState from '../common/EmptyState';
import { formatCompactNumber } from '../../utils/format';

// Cohort views(or likes)-per-hour by post age -- a falling curve across
// buckets is the expected shape (most of a post's lifetime metric accrues
// early, so the cumulative average rate drops as age outpaces it).
// Category x-axis (fixed bucket labels), not a date axis -- this isn't a
// time series, it's "how a typical post decays over its own lifetime".
export default function PerformanceDecayChart({ decay, color = '#6366f1' }) {
  const points = useMemo(() => (decay?.points ?? []).filter((p) => p.sample_size > 0), [decay]);

  const option = useMemo(() => {
    if (points.length === 0) return null;
    return {
      grid: { top: 20, right: 20, bottom: 40, left: 60 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(26, 26, 37, 0.85)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        padding: [10, 14],
        formatter: (params) => {
          const p = params[0];
          if (!p) return '';
          const point = points[p.dataIndex];
          return `
            <div style="font-weight:600;margin-bottom:6px;">${point.bucket_label} since posting</div>
            <div style="color:#8888a0">${formatCompactNumber(point.avg_velocity_per_hour)} / hour (avg)</div>
            <div style="color:#8888a0">${point.sample_size} snapshot${point.sample_size === 1 ? '' : 's'}</div>`;
        },
      },
      xAxis: {
        type: 'category',
        data: points.map((p) => p.bucket_label),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#8888a0', fontSize: 11, interval: 0, rotate: 30 },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.05)' } },
        axisLabel: { formatter: formatCompactNumber, color: '#8888a0', fontSize: 12 },
      },
      series: [
        {
          type: 'line',
          data: points.map((p) => p.avg_velocity_per_hour),
          itemStyle: { color },
          lineStyle: { width: 2, color },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [{ offset: 0, color }, { offset: 1, color: 'transparent' }],
            },
            opacity: 0.2,
          },
          symbol: 'circle',
          symbolSize: 6,
        },
      ],
    };
  }, [points, color]);

  if (!option) {
    return (
      <EmptyState
        title="Not enough history yet"
        message="Needs at least one metrics snapshot on a post published in this window."
      />
    );
  }

  return (
    <div className="w-full h-[240px]">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
