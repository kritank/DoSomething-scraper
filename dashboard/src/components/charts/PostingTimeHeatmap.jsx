import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import EmptyState from '../common/EmptyState';

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

// Weekday x hour heatmap -- the standard "best time to post" visualization
// (day-level and hour-level patterns readable in one glance), replacing two
// separate skinny bar charts that couldn't show the *combination* (e.g.
// "Wednesday evenings" vs just "Wednesdays" and "evenings" independently).
export default function PostingTimeHeatmap({ distribution }) {
  const matrix = distribution?.hourly_weekday_matrix;
  const total = distribution?.total_posts ?? 0;

  const { data, maxCount } = useMemo(() => {
    if (!matrix) return { data: [], maxCount: 0 };
    const out = [];
    let max = 0;
    for (let wd = 0; wd < 7; wd++) {
      for (let hr = 0; hr < 24; hr++) {
        const count = matrix[wd]?.[hr] ?? 0;
        out.push([hr, wd, count]);
        max = Math.max(max, count);
      }
    }
    return { data: out, maxCount: max };
  }, [matrix]);

  const option = useMemo(
    () => ({
      grid: { top: 10, right: 12, bottom: 28, left: 44 },
      tooltip: {
        backgroundColor: 'rgba(26, 26, 37, 0.9)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        formatter: (params) => {
          const [hr, wd, count] = params.value;
          return `<div style="font-weight:600;margin-bottom:4px;">${WEEKDAY_LABELS[wd]} ${hr}:00 UTC</div><div>${count} post${count === 1 ? '' : 's'}</div>`;
        },
      },
      xAxis: {
        type: 'category',
        data: Array.from({ length: 24 }, (_, i) => i),
        splitArea: { show: true, areaStyle: { color: ['transparent', 'rgba(255,255,255,0.015)'] } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (val) => (val % 3 === 0 ? `${val}h` : ''),
          color: '#8888a0',
          fontSize: 10,
        },
      },
      yAxis: {
        type: 'category',
        data: WEEKDAY_LABELS,
        splitArea: { show: true, areaStyle: { color: ['transparent', 'rgba(255,255,255,0.015)'] } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#8888a0', fontSize: 11 },
      },
      visualMap: {
        show: false,
        min: 0,
        max: Math.max(maxCount, 1),
        inRange: { color: ['rgba(6,182,212,0.06)', 'rgba(6,182,212,0.35)', 'rgba(6,182,212,0.7)', '#06b6d4'] },
      },
      series: [
        {
          type: 'heatmap',
          data,
          itemStyle: { borderWidth: 2, borderColor: '#1a1a25' },
          emphasis: { itemStyle: { borderColor: '#06b6d4', borderWidth: 2 } },
        },
      ],
    }),
    [data, maxCount]
  );

  if (total === 0) {
    return (
      <EmptyState
        title="Not enough posts yet"
        message="Posting-time patterns need at least a few posts in the selected window."
      />
    );
  }

  return (
    <div className="w-full h-56">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
