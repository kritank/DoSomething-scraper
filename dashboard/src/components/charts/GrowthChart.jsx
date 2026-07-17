import React, { useMemo, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { formatCompactNumber, formatUsdRange } from '../../utils/format';

const METRIC_LABELS = {
  followers: 'Followers',
  total_views: 'Total views',
  posts: 'Posts',
  earnings: 'Estimated earnings',
};

const EVENT_COLORS = {
  top_post: '#22c55e',
  milestone: '#6366f1',
};

const EVENT_TYPE_LABELS = {
  top_post: 'Standout post',
  milestone: 'Follower milestone',
};

export default function GrowthChart({ points, metric, color = '#6366f1', events = [], onEventClick }) {
  const chartRef = useRef(null);
  const isEarnings = metric === 'earnings';

  // Hooks must run in the same order every render -- see QueueDepthChart.jsx
  // for why the empty-state check has to live inside this useMemo (and the
  // derived values below are computed unconditionally with `points ?? []`)
  // rather than an early return before it.
  const { option, clusters } = useMemo(() => {
    const points_ = points ?? [];
    if (points_.length === 0) return { option: null, clusters: [] };

    const pointDates = points_.map((p) => p.date);
    const nearestPointDate = (targetDate) => {
      const targetMs = new Date(targetDate).getTime();
      let nearest = pointDates[0];
      let smallestDiffMs = Infinity;
      for (const d of pointDates) {
        const diffMs = Math.abs(new Date(d).getTime() - targetMs);
        if (diffMs < smallestDiffMs) {
          smallestDiffMs = diffMs;
          nearest = d;
        }
      }
      return nearest;
    };

    const valueByDate = new Map(
      points_.map((p) => [p.date, isEarnings ? ((p.value_low ?? 0) + (p.value_high ?? 0)) / 2 : p.value])
    );

    const clustersByDate = new Map();
    for (const e of events) {
      const snappedDate = nearestPointDate(e.date);
      const y = valueByDate.get(snappedDate);
      if (y === undefined || y === null) continue;
      if (!clustersByDate.has(snappedDate)) clustersByDate.set(snappedDate, { date: snappedDate, y, items: [] });
      clustersByDate.get(snappedDate).items.push(e);
    }
    const clusters = [...clustersByDate.values()];

    const xAxisData = points_.map(p => p.date);

    let series = [];
    
    if (isEarnings) {
      series = [
        {
          name: 'High',
          type: 'line',
          data: points_.map(p => p.value_high),
          lineStyle: { opacity: 0 },
          stack: 'confidence-band',
          symbol: 'none'
        },
        {
          name: 'Low',
          type: 'line',
          data: points_.map(p => p.value_high - p.value_low),
          lineStyle: { opacity: 0 },
          areaStyle: {
            color: color,
            opacity: 0.25
          },
          stack: 'confidence-band',
          symbol: 'none'
        },
        {
          name: 'Average',
          type: 'line',
          data: points_.map(p => ((p.value_low ?? 0) + (p.value_high ?? 0)) / 2),
          itemStyle: { color: color },
          lineStyle: { width: 1.5, color: color },
          symbol: 'none'
        }
      ];
    } else {
      series = [
        {
          name: METRIC_LABELS[metric] || metric,
          type: 'line',
          data: points_.map(p => p.value),
          itemStyle: { color: color },
          lineStyle: { width: 2, color: color },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: color },
                { offset: 1, color: 'transparent' }
              ]
            },
            opacity: 0.25
          },
          symbol: 'none'
        }
      ];
    }

    // Add scatter series for events
    if (clusters.length > 0) {
      series.push({
        name: 'Events',
        type: 'scatter',
        data: clusters.map(c => [c.date, c.y, c]),
        itemStyle: {
          color: (params) => {
            const cluster = params.data[2];
            const singleType = cluster.items.every(e => e.type === cluster.items[0].type) ? cluster.items[0].type : null;
            return singleType ? EVENT_COLORS[singleType] : '#fff';
          },
          borderColor: '#1a1a25',
          borderWidth: 2
        },
        symbolSize: (data) => {
          const cluster = data[2];
          return cluster.items.length > 1 ? 14 : 10;
        },
        zlevel: 1
      });
    }

    const chartOption = {
      grid: { top: 20, right: 20, bottom: 40, left: 60 },
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
          
          if (isEarnings) {
            const high = points_.find(p => p.date === date)?.value_high;
            const low = points_.find(p => p.date === date)?.value_low;
            if (high && low) html += `<div style="color: #8888a0">${METRIC_LABELS.earnings}: ${formatUsdRange(low, high)}</div>`;
          } else {
            const val = params.find(p => p.seriesType === 'line')?.value;
            if (val !== undefined) html += `<div style="color: #8888a0">${METRIC_LABELS[metric] ?? metric}: ${formatCompactNumber(val)}</div>`;
          }

          const cluster = clustersByDate.get(date);
          if (cluster) {
            cluster.items.forEach(e => {
              html += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.05)">
                <div style="display: flex; align-items: center; gap: 6px; font-weight: 500; color: ${EVENT_COLORS[e.type] || '#f0f0f5'}">
                  <span style="width: 6px; height: 6px; border-radius: 50%; background: ${EVENT_COLORS[e.type] || '#8888a0'}"></span>
                  ${EVENT_TYPE_LABELS[e.type] || e.type}
                  ${e.date !== date ? `<span style="margin-left: auto; font-weight: 400; color: #8888a0">${format(parseISO(e.date), 'MMM d')}</span>` : ''}
                </div>
                <div style="color: #f0f0f5; margin-top: 4px;">${e.label}</div>
              </div>`;
            });
          }
          return html;
        }
      },
      dataZoom: [
        {
          type: 'inside',
          start: 0,
          end: 100
        },
        {
          start: 0,
          end: 100,
          handleIcon: 'M10.7,11.9v-1.3H9.3v1.3c-4.9,0.3-8.8,4.4-8.8,9.4c0,5,3.9,9.1,8.8,9.4v1.3h1.3v-1.3c4.9-0.3,8.8-4.4,8.8-9.4C19.5,16.3,15.6,12.2,10.7,11.9z M13.3,24.4H6.7V23h6.6V24.4z M13.3,19.6H6.7v-1.4h6.6V19.6z',
          handleSize: '80%',
          handleStyle: { color: '#fff', shadowBlur: 3, shadowColor: 'rgba(0, 0, 0, 0.6)', shadowOffsetX: 2, shadowOffsetY: 2 },
          textStyle: { color: '#8888a0' },
          borderColor: 'transparent',
          backgroundColor: 'rgba(255,255,255,0.02)',
          fillerColor: 'rgba(99, 102, 241, 0.1)',
          bottom: 0,
          height: 16
        }
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
        // category value (e.g. "2026-07-05") instead of matching the
        // "Jul 5" the tick labels use just below it.
        axisPointer: { label: { formatter: (params) => format(parseISO(params.value), 'MMM d, yyyy') } }
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.05)' } },
        axisLabel: {
          formatter: isEarnings ? (v) => `$${formatCompactNumber(v)}` : formatCompactNumber,
          color: '#8888a0',
          fontSize: 12
        },
        // Same as the xAxis axisPointer above -- otherwise the crosshair
        // shows a raw number like "17,700,000.00" next to tick labels
        // formatted as "15M".
        axisPointer: {
          label: {
            formatter: (params) => isEarnings ? `$${formatCompactNumber(params.value)}` : formatCompactNumber(params.value),
          },
        },
      },
      series: series
    };

    return { option: chartOption, clusters };
  }, [points, metric, color, isEarnings, events]);

  if (!option) {
    return (
      <EmptyState
        title="Not enough history yet"
        message={isEarnings
          ? 'Earnings estimates need at least two days of view-count history to show a daily figure.'
          : 'Growth charts need at least a couple of days of snapshots to plot.'}
      />
    );
  }

  const onEvents = {
    click: (params) => {
      if (params.seriesType === 'scatter') {
        const cluster = params.data[2];
        const withLink = cluster?.items.find((e) => e.permalink);
        if (withLink) onEventClick?.(withLink);
      }
    }
  };

  return (
    <div className="w-full h-[300px] relative">
      <ReactECharts 
        ref={chartRef}
        option={option} 
        style={{ height: '100%', width: '100%' }} 
        onEvents={onEvents}
        notMerge={true}
      />
      {clusters.length > 0 && (
        <div className="flex items-center gap-4 mt-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: EVENT_COLORS.top_post }} />
            Standout post
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: EVENT_COLORS.milestone }} />
            Follower milestone
          </span>
          <span>· drag bottom handle to zoom, click points for details</span>
        </div>
      )}
    </div>
  );
}
