import React from 'react';
import { ExternalLink } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import Skeleton from '../common/Skeleton';
import EmptyState from '../common/EmptyState';
import InfoTip from '../common/InfoTip';
import PlatformIcon from '../common/PlatformIcon';
import { formatCompactNumber } from '../../utils/format';

const TOOLTIPS = {
  outlier: "This post's views (or likes) vs the account's median over its previous 30 posts. 2× = twice the typical post.",
  velocity: "Current views (or likes) gained per hour, from the two most recent scrapes -- not restricted to recently-published posts. Shows the lifetime average instead for posts scraped only once so far.",
};

// Shared "top videos / latest videos" table -- used by both the
// single-platform creator profile and the combined cross-platform profile
// (which passes posts merged from every linked account, with
// showPlatformColumn=true so each row's origin is visible at a glance).
export default function PostsTable({
  posts,
  loading,
  sortMode,
  onSortModeChange,
  formatFilter,
  onFormatFilterChange,
  longFormLabel,
  shortFormLabel,
  showPlatformColumn = false,
}) {
  return (
    <div className="flex flex-col gap-3 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1 rounded-lg p-0.5" style={{ background: 'var(--color-bg-card-hover)' }}>
          {[
            { value: 'top', label: 'Top videos' },
            { value: 'latest', label: 'Latest videos' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => onSortModeChange(opt.value)}
              className="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
              style={{
                background: sortMode === opt.value ? 'var(--color-accent)' : 'transparent',
                color: sortMode === opt.value ? '#fff' : 'var(--color-text-muted)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {[
            { value: 'all', label: 'All' },
            { value: 'long_form', label: longFormLabel },
            { value: 'short_form', label: shortFormLabel },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => onFormatFilterChange(opt.value)}
              className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
              style={{
                background: formatFilter === opt.value ? 'var(--color-accent-dim)' : 'transparent',
                color: formatFilter === opt.value ? 'var(--color-accent)' : 'var(--color-text-muted)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : posts.length === 0 ? (
        <EmptyState title="No posts yet" message="Posts will show up here after the next scrape." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                {showPlatformColumn && <th className="w-8"></th>}
                <Th>Title</Th>
                <Th>Type</Th>
                <Th>Posted</Th>
                <Th>Views</Th>
                <Th>Likes</Th>
                <Th>Comments</Th>
                <Th infoTip={TOOLTIPS.outlier}>Outlier</Th>
                <Th infoTip={TOOLTIPS.velocity}>Velocity/hr</Th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {posts.map((p) => (
                <tr key={`${p.platform ?? ''}-${p.post_id}`} className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                  {showPlatformColumn && (
                    <td className="py-2.5 px-3">
                      <PlatformIcon platform={p.platform} className="w-5 h-5 rounded-[5px]" handle={p.handle} />
                    </td>
                  )}
                  <td className="py-2.5 px-3 max-w-xs truncate" style={{ color: 'var(--color-text-primary)' }} title={p.title ?? ''}>
                    {p.permalink ? (
                      <a href={p.permalink} target="_blank" rel="noreferrer" className="hover:underline">
                        {p.title || '(untitled)'}
                      </a>
                    ) : (
                      p.title || '(untitled)'
                    )}
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    <span
                      className="px-2 py-0.5 rounded-full text-xs"
                      style={{
                        background: p.format === 'short_form' ? 'rgba(6,182,212,0.12)' : 'var(--color-accent-dim)',
                        color: p.format === 'short_form' ? 'var(--color-chart-2)' : 'var(--color-accent)',
                      }}
                    >
                      {p.format === 'short_form' ? shortFormLabel.replace(/s$/, '') : longFormLabel.replace(/s$/, '')}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                    {format(parseISO(p.posted_at), 'MMM d, yyyy')}
                  </td>
                  {/* Falsy check (not != null) is deliberate: Instagram
                      photo/carousel posts come back with views=0 (not a
                      real NULL) since they have no public view metric. */}
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.views ? formatCompactNumber(p.views) : '—'}</td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.likes != null ? formatCompactNumber(p.likes) : '—'}</td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.comments != null ? formatCompactNumber(p.comments) : '—'}</td>
                  <td className="py-2.5 px-3">
                    {p.outlier_score != null ? (
                      <span
                        className="px-2 py-0.5 rounded-full text-xs font-semibold"
                        style={{
                          background: p.outlier_score >= 2 ? 'var(--color-success-muted)' : 'var(--color-bg-card-hover)',
                          color: p.outlier_score >= 2 ? 'var(--color-success)' : 'var(--color-text-muted)',
                        }}
                      >
                        {p.outlier_score.toFixed(1)}×
                      </span>
                    ) : '—'}
                  </td>
                  <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {p.velocity_per_hour != null ? (
                      formatCompactNumber(p.velocity_per_hour)
                    ) : (
                      <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Not enough data yet</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3">
                    {p.permalink && (
                      <a href={p.permalink} target="_blank" rel="noreferrer">
                        <ExternalLink className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Th({ children, infoTip }) {
  return (
    <th className="text-left py-2.5 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
      <span className="inline-flex items-center gap-1">
        {children}
        {infoTip && <InfoTip text={infoTip} side="bottom" />}
      </span>
    </th>
  );
}
