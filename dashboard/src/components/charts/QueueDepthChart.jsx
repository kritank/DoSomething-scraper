import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';

export default function QueueDepthChart({ buckets }) {
  const data = useMemo(
    () =>
      (buckets ?? [])
        .map((b) => ({
          hour: b.hour,
          avg_main_depth: b.avg_main_depth,
          main_range_max: b.max_main_depth,
          avg_dlq_depth: b.avg_dlq_depth,
        }))
        .sort((a, b) => a.hour.localeCompare(b.hour)),
    [buckets]
  );
  
  const hasDlq = useMemo(() => (buckets ?? []).some((b) => b.avg_dlq_depth != null), [buckets]);

  // Hooks must run in the same order every render -- the empty-state early
  // return has to come after every hook, not before, or React throws
  // "Rendered more hooks than during the previous render" the moment data
  // goes from empty to non-empty (e.g. switching date range) and crashes
  // the whole tree. So `option` guards for the empty case internally
  // instead of skipping its own useMemo.
  const option = useMemo(() => {
    if (data.length === 0) return null;
    const xAxisData = data.map(d => d.hour);
    const series = [];

    // Range area
    series.push({
      name: 'Range Max',
      type: 'line',
      data: data.map(d => d.main_range_max),
      lineStyle: { opacity: 0 },
      stack: 'depth',
      symbol: 'none'
    });
    series.push({
      name: 'Range Min',
      type: 'line',
      data: data.map(d => d.main_range_max - d.avg_main_depth),
      lineStyle: { opacity: 0 },
      areaStyle: { color: 'var(--color-chart-1)', opacity: 0.15 },
      stack: 'depth',
      symbol: 'none'
    });

    // Average depth
    series.push({
      name: 'Queue depth (avg)',
      type: 'line',
      data: data.map(d => d.avg_main_depth),
      itemStyle: { color: 'var(--color-chart-1)' },
      lineStyle: { width: 2 },
      symbol: 'circle',
      symbolSize: 4
    });

    // Live Pulse for the last point
    if (data.length > 0) {
      const lastPoint = data[data.length - 1];
      series.push({
        name: 'Live Pulse',
        type: 'effectScatter',
        coordinateSystem: 'cartesian2d',
        data: [[lastPoint.hour, lastPoint.avg_main_depth]],
        symbolSize: 8,
        showEffectOn: 'render',
        rippleEffect: { brushType: 'stroke', scale: 4 },
        itemStyle: { color: 'var(--color-chart-1)' },
        zlevel: 1
      });
    }

    if (hasDlq) {
      series.push({
        name: 'DLQ depth (avg)',
        type: 'line',
        data: data.map(d => d.avg_dlq_depth),
        itemStyle: { color: 'var(--color-danger)' },
        lineStyle: { width: 2 },
        symbol: 'circle',
        symbolSize: 4
      });
    }

    return {
      grid: { top: 20, right: 20, bottom: 40, left: 40 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: 'rgba(255,255,255,0.1)' } },
        backgroundColor: 'rgba(26, 26, 37, 0.85)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        padding: [10, 14],
        formatter: (params) => {
          let hour = params[0].axisValue;
          let html = `<div style="font-weight: 600; margin-bottom: 6px;">${format(parseISO(hour), 'MMM d, yyyy h:mma')}</div>`;
          
          let avg = data.find(d => d.hour === hour)?.avg_main_depth;
          let max = data.find(d => d.hour === hour)?.main_range_max;
          if (avg != null && max != null) {
            html += `<div style="color: #8888a0">Queue depth range: ${avg.toFixed(1)} – ${max.toFixed(1)}</div>`;
            html += `<div style="color: #8888a0">Queue depth (avg): ${avg.toFixed(1)}</div>`;
          }
          
          let dlq = data.find(d => d.hour === hour)?.avg_dlq_depth;
          if (dlq != null) {
            html += `<div style="color: #ef4444; margin-top: 4px;">DLQ depth: ${dlq.toFixed(1)}</div>`;
          }
          return html;
        }
      },
      legend: {
        bottom: 0,
        textStyle: { color: '#8888a0', fontSize: 11 },
        icon: 'roundRect',
        itemGap: 15,
        data: [
          'Queue depth (avg)',
          ...(hasDlq ? ['DLQ depth (avg)'] : [])
        ]
      },
      xAxis: {
        type: 'category',
        data: xAxisData,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (val) => format(parseISO(val), 'MMM d, ha'),
          color: '#8888a0',
          fontSize: 12
        }
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.05)' } },
        axisLabel: { color: '#8888a0', fontSize: 11 }
      },
      series: series
    };
  }, [data, hasDlq]);

  if (!option) {
    return (
      <EmptyState
        title="No queue depth samples yet"
        message="Collected every 10 minutes by the scheduler -- check back shortly, or widen the date range."
      />
    );
  }

  return (
    <div className="w-full h-56">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
