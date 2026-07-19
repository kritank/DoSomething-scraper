import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { formatCompactNumber } from '../../utils/format';

// followers/following over time -- single line on its own axis (unlike
// GrowthChart's two raw counters, the *ratio* is the point here: a
// climbing line reads as "following far fewer than are following back",
// a common authenticity signal).
export default function FollowerRatioChart({ points, color = '#6366f1' }) {
  const data = useMemo(() => (points ?? []).filter((p) => p.ratio !== null), [points]);

  const option = useMemo(() => {
    if (data.length === 0) return null;
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
          const point = data[p.dataIndex];
          return `
            <div style="font-weight:600;margin-bottom:6px;">${format(parseISO(point.date), 'MMM d, yyyy')}</div>
            <div style="color:#8888a0">Ratio: ${point.ratio.toFixed(1)}×</div>
            <div style="color:#8888a0">${formatCompactNumber(point.followers)} followers / ${formatCompactNumber(point.following)} following</div>`;
        },
      },
      xAxis: {
        type: 'category',
        data: data.map((p) => p.date),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { formatter: (val) => format(parseISO(val), 'MMM d'), color: '#8888a0', fontSize: 12 },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.05)' } },
        axisLabel: { formatter: (v) => `${formatCompactNumber(v)}×`, color: '#8888a0', fontSize: 12 },
      },
      series: [
        {
          type: 'line',
          data: data.map((p) => p.ratio),
          itemStyle: { color },
          lineStyle: { width: 2, color },
          symbol: 'none',
        },
      ],
    };
  }, [data, color]);

  if (!option) {
    return (
      <EmptyState
        title="Not enough history yet"
        message="Followers/following ratio needs at least one profile snapshot with a nonzero following count."
      />
    );
  }

  return (
    <div className="w-full h-[240px]">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
