import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import EmptyState from '../common/EmptyState';

const ROW_ORDER = ['long_form', 'short_form'];

function formatDuration(seconds) {
  if (seconds == null) return null;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}

// Time-since-post x content-length heatmap of creator reply speed -- cell
// color/count = how many posts' first creator reply landed in that time
// bucket, for that format (same "count-based heatmap" shape as
// PostingTimeHeatmap, just with time-since-post columns instead of
// hour-of-day); the tooltip also surfaces that cell's actual average
// reply time, not just the bucket's range, since "6m avg" is more
// concrete than "somewhere in 0-15m."
export default function ReplyTimeHeatmap({ heatmap, longFormLabel = 'Long-form', shortFormLabel = 'Short-form' }) {
  const total = heatmap?.total_replies ?? 0;

  const bucketLabels = useMemo(() => heatmap?.bucket_labels ?? [], [heatmap]);
  const rowLabel = useMemo(
    () => ({ long_form: longFormLabel, short_form: shortFormLabel }),
    [longFormLabel, shortFormLabel]
  );

  const { data, maxCount } = useMemo(() => {
    if (!heatmap) return { data: [], maxCount: 0 };
    const out = [];
    let max = 0;
    ROW_ORDER.forEach((fmt, rowIdx) => {
      const stats = heatmap.formats.find((f) => f.format === fmt);
      const counts = stats?.bucket_counts ?? [];
      const avgTimes = stats?.bucket_avg_reply_time_s ?? [];
      const avgComments = stats?.bucket_avg_comments ?? [];
      counts.forEach((count, colIdx) => {
        out.push([colIdx, rowIdx, count, avgTimes[colIdx] ?? null, avgComments[colIdx] ?? null]);
        max = Math.max(max, count);
      });
    });
    return { data: out, maxCount: max };
  }, [heatmap]);

  const option = useMemo(
    () => ({
      grid: { top: 10, right: 12, bottom: 40, left: 76 },
      tooltip: {
        backgroundColor: 'rgba(26, 26, 37, 0.9)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        formatter: (params) => {
          const [colIdx, rowIdx, count, avgTime, avgComments] = params.value;
          const fmt = ROW_ORDER[rowIdx];
          const avgTimeLine = avgTime != null ? `<div>avg reply: ${formatDuration(avgTime)}</div>` : '';
          const avgCommentsLine = avgComments != null
            ? `<div>avg comments/post: ${Math.round(avgComments)}</div>`
            : '';
          return `<div style="font-weight:600;margin-bottom:4px;">${rowLabel[fmt]} · ${bucketLabels[colIdx]}</div><div>${count} post${count === 1 ? '' : 's'}</div>${avgTimeLine}${avgCommentsLine}`;
        },
      },
      xAxis: {
        type: 'category',
        data: bucketLabels,
        splitArea: { show: true, areaStyle: { color: ['transparent', 'rgba(255,255,255,0.015)'] } },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#8888a0', fontSize: 10, rotate: 30 },
      },
      yAxis: {
        type: 'category',
        data: ROW_ORDER.map((fmt) => rowLabel[fmt]),
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
    [data, maxCount, bucketLabels, rowLabel]
  );

  if (total === 0) {
    return (
      <EmptyState
        title="No replies yet"
        message="Response Insights needs posts where the creator has replied to at least one comment in the selected window."
      />
    );
  }

  return (
    <div className="w-full h-56">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
