import React, { useMemo, useState } from 'react';
import { format, parseISO } from 'date-fns';
import Skeleton from '../common/Skeleton';
import EmptyState from '../common/EmptyState';
import { formatCompactNumber, formatSignedCompact, formatUsdRange } from '../../utils/format';

const PAGE_SIZE = 14;

// The vidiq-style "Daily Subscriber Growth & View History" table -- a
// row-per-day complement to the GrowthChart/DailyGrowthChart above it, for
// scanning exact numbers rather than reading them off a line. Zips
// together up to three independently-fetched series (followers always
// present; views/earnings optional -- Instagram profiles have neither) by
// date, most recent first.
export default function DailyGrowthHistoryTable({ followersSeries, viewsSeries, earningsSeries, followersLabel = 'Followers', loading }) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const rows = useMemo(() => {
    const followers = followersSeries ?? [];
    if (followers.length === 0) return [];
    const viewsByDate = new Map((viewsSeries ?? []).map((p) => [p.date, p]));
    const earningsByDate = new Map((earningsSeries ?? []).map((p) => [p.date, p]));
    return [...followers]
      .sort((a, b) => (a.date < b.date ? 1 : -1))
      .map((f) => ({
        date: f.date,
        followers: f.value,
        views: viewsByDate.get(f.date)?.value ?? null,
        viewsDelta: viewsByDate.get(f.date)?.daily_delta ?? null,
        earnings: earningsByDate.get(f.date) ?? null,
      }));
  }, [followersSeries, viewsSeries, earningsSeries]);

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (rows.length === 0) {
    return <EmptyState title="Not enough history yet" message="This table fills in as daily snapshots accumulate." />;
  }

  const shown = rows.slice(0, visibleCount);
  const hasViews = viewsSeries && viewsSeries.length > 0;
  const hasEarnings = earningsSeries && earningsSeries.length > 0;

  return (
    <div className="flex flex-col gap-3 min-w-0">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
              <Th>Date</Th>
              <Th>{followersLabel}</Th>
              {hasViews && <Th>Views</Th>}
              {hasViews && <Th>Views change</Th>}
              {hasEarnings && <Th>Est. earnings</Th>}
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.date} className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                <td className="py-2.5 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-primary)' }}>
                  {format(parseISO(row.date), 'MMM d, yyyy')}
                </td>
                <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                  {row.followers != null ? formatCompactNumber(row.followers) : '—'}
                </td>
                {hasViews && (
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {row.views != null ? formatCompactNumber(row.views) : '—'}
                  </td>
                )}
                {hasViews && (
                  <td
                    className="py-2.5 px-3"
                    style={{ color: row.viewsDelta > 0 ? 'var(--color-success)' : row.viewsDelta < 0 ? 'var(--color-danger)' : 'var(--color-text-muted)' }}
                  >
                    {row.viewsDelta != null ? formatSignedCompact(row.viewsDelta) : '—'}
                  </td>
                )}
                {hasEarnings && (
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {row.earnings?.value_low != null ? formatUsdRange(row.earnings.value_low, row.earnings.value_high) : '—'}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {visibleCount < rows.length && (
        <button
          type="button"
          onClick={() => setVisibleCount((v) => v + PAGE_SIZE)}
          className="self-center text-xs font-medium px-3 py-1.5 rounded-lg hover:underline"
          style={{ color: 'var(--color-accent)' }}
        >
          Show more
        </button>
      )}
    </div>
  );
}

function Th({ children }) {
  return (
    <th className="text-left py-2.5 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
      {children}
    </th>
  );
}
