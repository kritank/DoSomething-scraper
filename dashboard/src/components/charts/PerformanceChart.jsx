import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { platformLabel, PLATFORM_COLORS } from '../../utils/platform';

function aggregateByDate(buckets) {
  const byDate = new Map();
  for (const b of buckets) {
    if (!byDate.has(b.date)) byDate.set(b.date, { date: b.date, durations: [], mins: [], maxes: [] });
    const row = byDate.get(b.date);
    if (b.quota_units_used != null) {
      row.youtube_quota = (row.youtube_quota ?? 0) + b.quota_units_used;
    }
    if (b.status === 'failed') continue;
    row[`${b.platform}_posts`] = (row[`${b.platform}_posts`] ?? 0) + b.posts_processed;
    row[`${b.platform}_comments`] = (row[`${b.platform}_comments`] ?? 0) + b.comments_processed;
    if (b.avg_duration_s != null) row.durations.push(b.avg_duration_s);
    if (b.min_duration_s != null) row.mins.push(b.min_duration_s);
    if (b.max_duration_s != null) row.maxes.push(b.max_duration_s);
  }
  return [...byDate.values()]
    .map((row) => {
      const min = row.mins.length ? Math.min(...row.mins) : null;
      const max = row.maxes.length ? Math.max(...row.maxes) : null;
      return {
        ...row,
        avg_duration_s: row.durations.length
          ? row.durations.reduce((a, b) => a + b, 0) / row.durations.length
          : null,
        duration_min: min,
        duration_max: max,
      };
    })
    .sort((a, b) => a.date.localeCompare(b.date));
}

export default function PerformanceChart({ buckets }) {
  const data = useMemo(() => aggregateByDate(buckets ?? []), [buckets]);
  const platforms = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.platform))],
    [buckets],
  );
  const hasQuota = useMemo(() => (buckets ?? []).some((b) => b.quota_units_used != null), [buckets]);

  // Hooks must run in the same order every render -- see QueueDepthChart.jsx
  // for why the empty-state check lives inside this useMemo rather than as
  // an early return before it.
  const option = useMemo(() => {
    if (data.length === 0) return null;
    const xAxisData = data.map(d => d.date);
    const series = [];

    // Duration Range (Area)
    series.push({
      name: 'Duration Max',
      type: 'line',
      data: data.map(d => d.duration_max),
      yAxisIndex: 1,
      lineStyle: { opacity: 0 },
      stack: 'duration',
      symbol: 'none',
      itemStyle: { color: 'var(--color-chart-4)' }
    });
    series.push({
      name: 'Duration Min',
      type: 'line',
      data: data.map(d => d.duration_max - d.duration_min),
      yAxisIndex: 1,
      lineStyle: { opacity: 0 },
      areaStyle: { color: 'var(--color-chart-4)', opacity: 0.15 },
      stack: 'duration',
      symbol: 'none'
    });
    
    // Average Duration Line
    series.push({
      name: 'Avg duration (s)',
      type: 'line',
      data: data.map(d => d.avg_duration_s),
      yAxisIndex: 1,
      symbol: 'circle',
      symbolSize: 6,
      itemStyle: { color: 'var(--color-chart-4)' },
      lineStyle: { width: 2 }
    });

    // YouTube Quota
    if (hasQuota) {
      series.push({
        name: 'YouTube quota used',
        type: 'line',
        data: data.map(d => d.youtube_quota),
        yAxisIndex: 2, // Map to hidden yAxis if needed or main axis
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: 'var(--color-warning)' },
        lineStyle: { width: 2, type: 'dashed' }
      });
    }

    // Platforms Bars & Lines
    platforms.forEach(p => {
      // Posts (Bars)
      series.push({
        name: `${platformLabel(p)} posts`,
        type: 'bar',
        data: data.map(d => d[`${p}_posts`]),
        stack: 'posts',
        itemStyle: { color: PLATFORM_COLORS[p], borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 24,
      });

      // Comments (Lines)
      series.push({
        name: `${platformLabel(p)} comments`,
        type: 'line',
        data: data.map(d => d[`${p}_comments`]),
        yAxisIndex: 3, // Hidden axis for comments to not squish posts
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: PLATFORM_COLORS[p] },
        lineStyle: { width: 2 }
      });
    });

    return {
      // bottom: 90 (not 65) -- this legend can carry up to 7 series
      // (2 platforms x posts/comments, avg duration, quota), which wraps to
      // 2-3 rows at typical card widths. Too little room here means the
      // legend's later rows overlap the x-axis date labels instead of
      // sitting below them, and get visually clipped by the chart's fixed
      // container height (bumped to h-96 below for the same reason).
      grid: { top: 30, right: 50, bottom: 90, left: 50 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', label: { backgroundColor: '#1a1a25' } },
        backgroundColor: 'rgba(26, 26, 37, 0.85)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        padding: [10, 14],
        formatter: (params) => {
          let date = params[0].axisValue;
          let html = `<div style="font-weight: 600; margin-bottom: 6px;">${format(parseISO(date), 'MMM d, yyyy')}</div>`;
          
          params.forEach(param => {
            if (param.seriesName === 'Duration Max' || param.seriesName === 'Duration Min') return; // Handled specially or ignore
            
            let valStr = param.value != null ? (typeof param.value === 'number' && param.value % 1 !== 0 ? param.value.toFixed(1) : param.value) : 'N/A';
            if (param.seriesName.includes('duration')) valStr += 's';

            html += `<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 6px; color: var(--color-text-secondary)">
                <span style="width: 8px; height: 8px; border-radius: 2px; background: ${param.color}"></span>
                ${param.seriesName}
              </div>
              <div style="font-weight: 500; color: var(--color-text-primary)">${valStr}</div>
            </div>`;
          });
          return html;
        }
      },
      legend: {
        bottom: 4,
        textStyle: { color: '#8888a0', fontSize: 11 },
        icon: 'roundRect',
        itemGap: 12,
        itemWidth: 10,
        itemHeight: 10,
        data: [
          ...platforms.map(p => `${platformLabel(p)} posts`),
          ...platforms.map(p => `${platformLabel(p)} comments`),
          'Avg duration (s)',
          ...(hasQuota ? ['YouTube quota used'] : [])
        ]
      },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 }
      ],
      xAxis: {
        type: 'category',
        data: xAxisData,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (val) => format(parseISO(val), 'MMM d'),
          color: '#8888a0',
          fontSize: 12
        },
        // Without this, the crosshair's own label falls back to the raw
        // category value instead of matching the tick labels below it.
        axisPointer: { label: { formatter: (params) => format(parseISO(params.value), 'MMM d, yyyy') } }
      },
      yAxis: [
        {
          type: 'value',
          name: 'Posts',
          nameTextStyle: { color: '#55556a', padding: [0, 20, 0, 0] },
          splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.05)' } },
          axisLabel: { color: '#8888a0', fontSize: 11 }
        },
        {
          type: 'value',
          name: 'Duration',
          nameTextStyle: { color: '#55556a', padding: [0, 0, 0, 20] },
          splitLine: { show: false },
          axisLabel: {
            formatter: (v) => `${Math.round(v)}s`,
            color: '#8888a0',
            fontSize: 11
          },
          // Same as xAxis above -- keeps the crosshair's "s" suffix
          // consistent with the tick labels instead of a bare number.
          axisPointer: { label: { formatter: (params) => `${Math.round(params.value)}s` } }
        },
        {
          type: 'value',
          show: false // Quota
        },
        {
          type: 'value',
          show: false // Comments
        }
      ],
      series: series
    };
  }, [data, platforms, hasQuota]);

  if (!option) {
    return <EmptyState title="No performance data yet" message="Duration and throughput trends show up here." />;
  }

  return (
    <div className="w-full h-96">
      <ReactECharts 
        option={option} 
        style={{ height: '100%', width: '100%' }} 
        notMerge={true}
      />
    </div>
  );
}
