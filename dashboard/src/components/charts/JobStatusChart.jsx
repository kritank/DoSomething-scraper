import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO } from 'date-fns';
import EmptyState from '../common/EmptyState';
import { platformLabel } from '../../utils/platform';

const STATUS_COLORS = {
  completed: 'var(--color-chart-3)',
  failed: 'var(--color-chart-5)',
  running: 'var(--color-chart-1)',
  queued: 'var(--color-chart-4)',
  retry_pending: 'var(--color-chart-2)',
};

function pivotByDate(buckets) {
  const byDate = new Map();
  for (const b of buckets) {
    if (!byDate.has(b.date)) byDate.set(b.date, { date: b.date });
    byDate.get(b.date)[`${b.platform}_${b.status}`] = b.job_count;
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export default function JobStatusChart({ buckets }) {
  const data = useMemo(() => pivotByDate(buckets ?? []), [buckets]);
  const statuses = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.status))],
    [buckets]
  );
  const platforms = useMemo(
    () => [...new Set((buckets ?? []).map((b) => b.platform))],
    [buckets]
  );

  // Hooks must run in the same order every render -- see QueueDepthChart.jsx
  // for why the empty-state check lives inside this useMemo rather than as
  // an early return before it.
  const option = useMemo(() => {
    if (data.length === 0) return null;
    const xAxisData = data.map(d => d.date);
    const series = [];

    platforms.forEach(platform => {
      statuses.forEach(status => {
        series.push({
          name: `${platformLabel(platform)} · ${status.replaceAll('_', ' ')}`,
          type: 'bar',
          stack: platform,
          data: data.map(d => d[`${platform}_${status}`]),
          itemStyle: { color: STATUS_COLORS[status] ?? 'var(--color-text-muted)' },
          barMaxWidth: 24,
          emphasis: { focus: 'series' }
        });
      });
    });

    return {
      grid: { top: 20, right: 20, bottom: 40, left: 40 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: 'rgba(26, 26, 37, 0.85)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        padding: [10, 14],
        formatter: (params) => {
          let date = params[0].axisValue;
          let html = `<div style="font-weight: 600; margin-bottom: 6px;">${format(parseISO(date), 'MMM d, yyyy')}</div>`;
          
          params.forEach(param => {
            if (!param.value) return;
            html += `<div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px; gap: 12px;">
              <div style="display: flex; align-items: center; gap: 6px; color: var(--color-text-secondary)">
                <span style="width: 8px; height: 8px; border-radius: 2px; background: ${param.color}"></span>
                ${param.seriesName}
              </div>
              <div style="font-weight: 500; color: var(--color-text-primary)">${param.value}</div>
            </div>`;
          });
          return html;
        }
      },
      legend: {
        bottom: 0,
        textStyle: { color: '#8888a0', fontSize: 11 },
        icon: 'roundRect',
        itemGap: 15,
        data: statuses.map(s => {
          // Creating custom legend items since series names are platform-specific
          return {
            name: s.replaceAll('_', ' '),
            icon: 'roundRect',
            itemStyle: { color: STATUS_COLORS[s] }
          };
        })
      },
      xAxis: {
        type: 'category',
        data: xAxisData,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          formatter: (val) => format(parseISO(val), 'MMM d'),
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
  }, [data, statuses, platforms]);

  if (!option) {
    return <EmptyState title="No scrape jobs yet" message="Once jobs run, daily counts show up here." />;
  }

  return (
    <div className="w-full h-64 flex flex-col gap-1">
      <div className="flex-1 min-h-0">
        <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
      </div>
      {platforms.length > 1 && (
        <p className="text-xs text-center mt-2" style={{ color: 'var(--color-text-muted)' }}>
          Each day is grouped into one bar cluster per platform ({platforms.map(platformLabel).join(', ')}), stacked by status.
        </p>
      )}
    </div>
  );
}
