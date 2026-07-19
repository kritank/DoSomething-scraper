import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { formatPercent } from '../../utils/format';

// (likes+comments)/followers per posting-date bucket -- same line-chart
// shape as GrowthChart, but a rate rather than a cumulative counter, so no
// area fill (an area under a rate reads as "volume", which this isn't).
export default function EngagementTrendChart({ points, color = '#6366f1' }) {
  const data = useMemo(() => (points ?? []).filter((p) => p.avg_engagement_rate !== null), [points]);

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
            <div style="color:#8888a0">Engagement rate: ${formatPercent(point.avg_engagement_rate)}</div>
            <div style="color:#8888a0">${point.post_count} post${point.post_count === 1 ? '' : 's'}</div>`;
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
        axisLabel: { formatter: (v) => formatPercent(v, 1), color: '#8888a0', fontSize: 12 },
      },
      series: [
        {
          type: 'line',
          data: data.map((p) => p.avg_engagement_rate),
          itemStyle: { color },
          lineStyle: { width: 2, color },
          symbol: 'circle',
          symbolSize: 6,
        },
      ],
    };
  }, [data, color]);

  if (!option) {
    return (
      <EmptyState
        title="Not enough history yet"
        message="Engagement trend needs at least one post with a recorded like/comment count in this window."
      />
    );
  }

  return (
    <div className="w-full h-[240px]">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
