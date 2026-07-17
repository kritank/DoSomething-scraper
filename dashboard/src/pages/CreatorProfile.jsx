import React, { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ExternalLink, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import {
  getCreatorStats,
  getCreatorGrowth,
  getCreatorPostPerformance,
} from '../services/creatorStatsService';
import PlatformBadge from '../components/common/PlatformBadge';
import EmptyState from '../components/common/EmptyState';
import Button from '../components/common/Button';
import GrowthChart from '../components/charts/GrowthChart';
import { formatHandle, platformLabel, PLATFORM_COLORS } from '../utils/platform';
import { formatCompactNumber, formatSignedCompact, formatUsdRange, formatPercent } from '../utils/format';

const GROWTH_RANGES = [30, 90, 365];

function StatTile({ label, value, delta, deltaLabel, loading }) {
  const deltaPositive = typeof delta === 'number' && delta > 0;
  const deltaNegative = typeof delta === 'number' && delta < 0;
  return (
    <div className="card p-5 flex flex-col gap-2 animate-fade-in">
      <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
      {loading ? (
        <div className="h-7 w-20 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
      ) : (
        <>
          <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
          {delta !== undefined && (
            <div className="flex items-center gap-1 text-xs" style={{
              color: deltaPositive ? 'var(--color-success)' : deltaNegative ? 'var(--color-danger)' : 'var(--color-text-muted)',
            }}>
              {deltaPositive && <TrendingUp className="w-3 h-3" />}
              {deltaNegative && <TrendingDown className="w-3 h-3" />}
              <span>{delta === null ? '—' : formatSignedCompact(delta)} {deltaLabel}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function CreatorProfile() {
  const { influencerId } = useParams();

  const [stats, setStats] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);

  const [growthMetric, setGrowthMetric] = useState('followers');
  const [growthDays, setGrowthDays] = useState(90);
  const [growthPoints, setGrowthPoints] = useState([]);
  const [growthLoading, setGrowthLoading] = useState(true);

  const [posts, setPosts] = useState([]);
  const [postsLoading, setPostsLoading] = useState(true);

  const loadStats = useCallback(async () => {
    setLoading(true);
    setNotFound(false);
    try {
      const data = await getCreatorStats(influencerId);
      setStats(data);
    } catch {
      // apiClient's interceptor discards the HTTP status (see
      // apiClient.js), so -- same convention as Insights.jsx's
      // loadBenchmark -- any failure on this suppressErrorToast call is
      // treated as "not found / no data yet" rather than a hard error.
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [influencerId]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    if (!stats) return;
    let cancelled = false;
    setGrowthLoading(true);
    getCreatorGrowth(influencerId, growthDays, growthMetric)
      .then((data) => { if (!cancelled) setGrowthPoints(data); })
      .finally(() => { if (!cancelled) setGrowthLoading(false); });
    return () => { cancelled = true; };
  }, [influencerId, growthDays, growthMetric, stats]);

  useEffect(() => {
    if (!stats) return;
    let cancelled = false;
    setPostsLoading(true);
    getCreatorPostPerformance(influencerId, 20)
      .then((data) => { if (!cancelled) setPosts(data); })
      .finally(() => { if (!cancelled) setPostsLoading(false); });
    return () => { cancelled = true; };
  }, [influencerId, stats]);

  if (notFound) {
    return <EmptyState title="Influencer not found" message="This influencer may have been deleted." />;
  }

  const s = stats?.summary;
  const isYoutube = s?.platform === 'youtube';
  const followersLabel = isYoutube ? 'Subscribers' : 'Followers';
  const availableMetrics = isYoutube ? ['followers', 'total_views'] : ['followers'];

  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/influencers">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-3.5 h-3.5" />
              Back
            </Button>
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
                {loading ? 'Loading…' : formatHandle(s.handle, s.platform)}
              </h2>
              {!loading && <PlatformBadge platform={s.platform} />}
            </div>
            {!loading && (
              <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                {[s.category_name, s.country, s.account_age_days != null ? `${Math.floor(s.account_age_days / 365)}y old` : null]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            )}
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={loadStats} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      {!loading && s && s.followers === 0 && s.post_count === 0 ? (
        <EmptyState
          title="Data is being collected"
          message="This influencer hasn't completed a scrape yet -- stats will appear here after the first run."
        />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatTile
              label={followersLabel}
              value={loading ? '' : (s.subscribers_hidden ? 'Hidden' : formatCompactNumber(s.followers))}
              delta={loading ? undefined : s.followers_delta_28d}
              deltaLabel={loading ? '' : (s.actual_window_days_28 < 28 ? `over ${s.actual_window_days_28}d (partial)` : 'in 28d')}
              loading={loading}
            />
            <StatTile
              label={isYoutube ? 'Total views' : 'Views (28d)'}
              value={loading ? '' : formatCompactNumber(isYoutube ? s.total_views : s.views_28d)}
              loading={loading}
            />
            <StatTile
              label={isYoutube ? 'Videos' : 'Posts'}
              value={loading ? '' : formatCompactNumber(s.post_count)}
              delta={undefined}
              loading={loading}
            />
            <StatTile
              label="Engagement rate"
              value={loading ? '' : formatPercent(stats.engagement.engagement_rate)}
              loading={loading}
            />
          </div>

          <div className="card p-5 flex flex-col gap-4 min-w-0">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>Growth</h3>
              <div className="flex items-center gap-4 flex-wrap">
                {availableMetrics.length > 1 && (
                  <div className="flex items-center gap-1">
                    {availableMetrics.map((m) => (
                      <button
                        key={m}
                        onClick={() => setGrowthMetric(m)}
                        className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                        style={{
                          background: growthMetric === m ? 'var(--color-accent-dim)' : 'transparent',
                          color: growthMetric === m ? 'var(--color-accent)' : 'var(--color-text-muted)',
                        }}
                      >
                        {m === 'followers' ? followersLabel : 'Total views'}
                      </button>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-1">
                  {GROWTH_RANGES.map((d) => (
                    <button
                      key={d}
                      onClick={() => setGrowthDays(d)}
                      className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                      style={{
                        background: growthDays === d ? 'var(--color-accent-dim)' : 'transparent',
                        color: growthDays === d ? 'var(--color-accent)' : 'var(--color-text-muted)',
                      }}
                    >
                      {d}d
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {growthLoading ? (
              <div className="h-64 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
            ) : (
              <GrowthChart points={growthPoints} metric={growthMetric} color={PLATFORM_COLORS[s?.platform]} />
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="card p-5 flex flex-col gap-2">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>Estimated earnings</h3>
              {loading ? (
                <div className="h-7 w-32 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
              ) : stats.earnings ? (
                <>
                  <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>
                    {formatUsdRange(stats.earnings.low_usd, stats.earnings.high_usd)}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    {stats.earnings.basis === 'monthly_ad_revenue' ? 'Estimated monthly ad revenue' : 'Estimated price per sponsored post'}
                    {' — rough industry-rate estimate, not real revenue data.'}
                  </p>
                </>
              ) : (
                <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Not enough data to estimate yet.</p>
              )}
            </div>

            <div className="card p-5 flex flex-col gap-2">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>Tracked rankings</h3>
              {loading ? (
                <div className="h-7 w-32 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
              ) : (
                <div className="flex flex-col gap-1.5 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  <RankingRow label={`Among tracked ${platformLabel(s.platform)} accounts`} entry={stats.rankings.by_followers_overall} />
                  {s.category_name && (
                    <RankingRow label={`In "${s.category_name}"`} entry={stats.rankings.by_followers_in_category} />
                  )}
                  {stats.rankings.by_views_growth_28d_overall && (
                    <RankingRow label="By 28d view growth" entry={stats.rankings.by_views_growth_28d_overall} />
                  )}
                  <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
                    Ranked only among influencers tracked in this dashboard, not a global/industry rank.
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="card p-5 flex flex-col gap-3 min-w-0">
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>Recent {isYoutube ? 'videos' : 'posts'}</h3>
            {postsLoading ? (
              <div className="h-48 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
            ) : posts.length === 0 ? (
              <EmptyState title="No posts yet" message="Posts will show up here after the next scrape." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                      <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Title</th>
                      <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Posted</th>
                      <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Views</th>
                      <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Likes</th>
                      <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Comments</th>
                      <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Outlier</th>
                      <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Velocity/hr</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {posts.map((p) => (
                      <tr key={p.post_id} className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                        <td className="py-2.5 px-3 max-w-xs truncate" style={{ color: 'var(--color-text-primary)' }} title={p.title ?? ''}>
                          {p.title || '(untitled)'}
                        </td>
                        <td className="py-2.5 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                          {format(parseISO(p.posted_at), 'MMM d, yyyy')}
                        </td>
                        <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.views != null ? formatCompactNumber(p.views) : '—'}</td>
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
                          {p.velocity_per_hour != null ? formatCompactNumber(p.velocity_per_hour) : '—'}
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
        </>
      )}
    </div>
  );
}

function RankingRow({ label, entry }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span style={{ color: 'var(--color-text-muted)' }}>{label}</span>
      <span className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
        {entry ? `#${entry.rank} of ${entry.out_of}` : '—'}
      </span>
    </div>
  );
}
