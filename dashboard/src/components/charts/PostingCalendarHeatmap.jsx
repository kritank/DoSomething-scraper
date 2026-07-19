import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { format, parseISO, subDays } from 'date-fns';
import EmptyState from '../common/EmptyState';

const LEGEND_COLORS = ['rgba(99,102,241,0.08)', 'rgba(99,102,241,0.3)', 'rgba(99,102,241,0.55)', 'rgba(99,102,241,0.8)', '#6366f1'];

// GitHub-contributions-style calendar heatmap -- the standard visualization
// for "one value per day over months" (posting frequency, activity streaks).
// Unlike a bar chart, its footprint is fixed regardless of the data's
// magnitude, so a quiet account doesn't leave a mostly-empty chart the way
// a bar chart with a handful of tall spikes does.
export default function PostingCalendarHeatmap({ points, days }) {
  const byDate = useMemo(() => {
    const map = new Map();
    for (const p of points ?? []) map.set(p.date, p.post_count);
    return map;
  }, [points]);

  const { start, end, maxCount, totalPosts, activeDays } = useMemo(() => {
    const end = new Date();
    const start = subDays(end, days - 1);
    let max = 0;
    let total = 0;
    for (const v of byDate.values()) {
      max = Math.max(max, v);
      total += v;
    }
    return {
      start: format(start, 'yyyy-MM-dd'),
      end: format(end, 'yyyy-MM-dd'),
      maxCount: max,
      totalPosts: total,
      activeDays: byDate.size,
    };
  }, [byDate, days]);

  const data = useMemo(
    () => Array.from(byDate.entries()).map(([date, count]) => [date, count]),
    [byDate]
  );

  // Sized so cellSize * 9 + 30 (the wrapper height below) lands close to
  // PostingTimeHeatmap's fixed h-56 (224px) -- these two charts sit side
  // by side in the same grid row, and the old 11/15px cells made this one
  // look tiny and empty next to its full-height sibling.
  const cellSize = days > 200 ? 14 : 20;
  // Side-by-side with the weekday/hour heatmap (see PostingFrequencyCard),
  // this chart's column often has less width than the calendar's natural
  // footprint at longer ranges -- rather than letting ECharts stretch or
  // clip cells to fit, the wrapper below sizes to this exact content width
  // and scrolls horizontally when the column is narrower than that.
  const numWeekColumns = Math.ceil(days / 7) + 2;
  const contentWidth = 40 + numWeekColumns * cellSize + 10;

  const option = useMemo(
    () => ({
      tooltip: {
        backgroundColor: 'rgba(26, 26, 37, 0.9)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#f0f0f5', fontSize: 12 },
        formatter: (params) => {
          const [date, count] = params.data ?? [params.value?.[0], 0];
          const label = format(parseISO(date), 'EEE, MMM d, yyyy');
          return `<div style="font-weight:600;margin-bottom:4px;">${label}</div><div>${count || 0} post${count === 1 ? '' : 's'}</div>`;
        },
      },
      visualMap: {
        show: false,
        min: 0,
        max: Math.max(maxCount, 1),
        inRange: { color: LEGEND_COLORS },
      },
      calendar: {
        range: [start, end],
        // A fixed pixel offset (not 'center', and never paired with
        // `right` -- that combination makes ECharts stretch cell width to
        // fill the available space instead of respecting cellSize) because
        // the wrapper div below is already sized to this chart's exact
        // content width, so there's no extra room to center within.
        left: 40,
        top: 26,
        cellSize: [cellSize, cellSize],
        yearLabel: { show: false },
        monthLabel: { color: '#8888a0', fontSize: 11, nameMap: 'en' },
        dayLabel: { color: '#8888a0', fontSize: 10, firstDay: 1, nameMap: ['S', 'M', 'T', 'W', 'T', 'F', 'S'] },
        itemStyle: {
          borderWidth: 3,
          borderColor: 'transparent',
          color: 'rgba(255,255,255,0.03)',
        },
        splitLine: { show: false },
      },
      series: [
        {
          type: 'heatmap',
          coordinateSystem: 'calendar',
          data,
        },
      ],
    }),
    [data, start, end, maxCount, cellSize]
  );

  if (data.length === 0) {
    return (
      <div className="h-full flex flex-col justify-center">
        <EmptyState
          title="No posts in this window"
          message="Posting activity will show up here once posts land in the selected window."
        />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col justify-center gap-2">
      <div className="flex items-center justify-between px-1">
        <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <span className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>{totalPosts}</span> post{totalPosts === 1 ? '' : 's'} across{' '}
          <span className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>{activeDays}</span> active day{activeDays === 1 ? '' : 's'}
        </span>
        <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          Less
          {LEGEND_COLORS.map((color, i) => (
            <span key={i} className="w-2.5 h-2.5 rounded-sm" style={{ background: color === LEGEND_COLORS[0] ? 'rgba(255,255,255,0.08)' : color }} />
          ))}
          More
        </span>
      </div>
      <div className="w-full overflow-x-auto">
        <div className="mx-auto" style={{ width: contentWidth, height: cellSize * 9 + 30 }}>
          <ReactECharts option={option} style={{ height: '100%', width: '100%' }} notMerge={true} />
        </div>
      </div>
    </div>
  );
}
