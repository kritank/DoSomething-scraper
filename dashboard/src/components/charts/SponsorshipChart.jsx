import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import EmptyState from '../common/EmptyState';
import { formatCompactNumber } from '../../utils/format';

const ORGANIC_COLOR = '#6366f1';
const SPONSORED_COLOR = '#f59e0b';

const CATEGORY_LABELS = ['Overall', 'Long-form', 'Short-form'];

// Grouped bar chart -- organic vs. officially-disclosed-sponsored avg
// views, for the overall window and each format. Post counts/mix live in
// the stat cards above this chart (see SponsorshipCard); this stays
// focused on the performance question. Bars for a bucket with zero posts
// are omitted rather than drawn as a misleading 0-height bar.
export default function SponsorshipChart({ breakdown }) {
  const buckets = useMemo(() => {
    if (!breakdown) return [];
    const longForm = breakdown.formats.find((f) => f.format === 'long_form');
    const shortForm = breakdown.formats.find((f) => f.format === 'short_form');
    return [
      { label: CATEGORY_LABELS[0], organic: breakdown.organic, sponsored: breakdown.sponsored },
      { label: CATEGORY_LABELS[1], organic: longForm?.organic, sponsored: longForm?.sponsored },
      { label: CATEGORY_LABELS[2], organic: shortForm?.organic, sponsored: shortForm?.sponsored },
    ];
  }, [breakdown]);

  const option = useMemo(() => {
    const mkSeries = (key, name, color) => ({
      name,
      type: 'bar',
      barMaxWidth: 46,
      data: buckets.map((b) => {
        const stats = b[key];
        if (!stats || !stats.post_count || stats.avg_views == null) return { value: 0, itemStyle: { opacity: 0 } };
        return { value: stats.avg_views, postCount: stats.post_count };
      }),
      itemStyle: { color, borderRadius: [4, 4, 0, 0] },
      emphasis: { itemStyle: { color } },
    });

    return {
      grid: { top: 44, right: 16, bottom: 30, left: 74 },
      legend: {
        top: 0,
        right: 0,
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: '#8888a0', fontSize: 12 },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: 'rgba(26, 26, 37, 0.9)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        padding: [10, 14],
        formatter: (params) => {
          const lines = params
            .filter((p) => p.data && p.data.postCount)
            .map((p) => {
              const d = p.data;
              return `<div style="margin-top:4px;"><span style="color:${p.color};font-weight:600;">${p.seriesName}</span> — ${d.postCount} post${d.postCount === 1 ? '' : 's'}<br/>
                ${formatCompactNumber(d.value)} avg views</div>`;
            });
          if (lines.length === 0) return '';
          return `<div style="font-weight:600;margin-bottom:2px;">${params[0].axisValue}</div>${lines.join('')}`;
        },
      },
      yAxis: {
        type: 'category',
        data: buckets.map((b) => b.label),
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
        axisTick: { show: false },
        axisLabel: { color: '#8888a0', fontSize: 12 },
      },
      xAxis: {
        type: 'value',
        splitLine: { lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.05)' } },
        axisLabel: { formatter: (v) => formatCompactNumber(v), color: '#8888a0', fontSize: 11 },
      },
      series: [
        mkSeries('organic', 'Organic', ORGANIC_COLOR),
        mkSeries('sponsored', 'Sponsored', SPONSORED_COLOR),
      ],
    };
  }, [buckets]);

  const hasSponsoredData = breakdown && breakdown.sponsored.post_count > 0;

  if (!hasSponsoredData) {
    return (
      <EmptyState
        title="No tagged sponsored posts in this window"
        message="No posts here were marked with the platform's official paid-partnership/paid-promotion disclosure in this window. Try a wider date range."
      />
    );
  }

  return (
    <div className="w-full h-56">
      <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
    </div>
  );
}
