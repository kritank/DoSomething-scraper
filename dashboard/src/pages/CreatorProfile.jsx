import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, TrendingDown, RefreshCw, BadgeCheck, Video, Calendar, Clock } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import {
  getCreatorStats,
  getCreatorGrowth,
  getCreatorPostPerformance,
  getCreatorFormatBreakdown,
  getCreatorKeyEvents,
} from '../services/creatorStatsService';
import PlatformBadge from '../components/common/PlatformBadge';
import ScrapeStatusIndicator from '../components/common/ScrapeStatusIndicator';
import { getInfluencerJobs } from '../services/influencerJobsService';
import Avatar from '../components/common/Avatar';
import EmptyState from '../components/common/EmptyState';
import Button from '../components/common/Button';
import Skeleton from '../components/common/Skeleton';
import InfoTip from '../components/common/InfoTip';
import Banner from '../components/common/Banner';
import GrowthChart from '../components/charts/GrowthChart';
import DailyGrowthChart from '../components/charts/DailyGrowthChart';
import FormatSplitCard from '../components/creator/FormatSplitCard';
import AboutSection from '../components/creator/AboutSection';
import PostsTable from '../components/creator/PostsTable';
import DailyGrowthHistoryTable from '../components/creator/DailyGrowthHistoryTable';
import HeaderPill from '../components/common/HeaderPill';
import { avatarUrl } from '../services/apiClient';
import { formatHandle, platformLabel, PLATFORM_COLORS } from '../utils/platform';
import { formatCompactNumber, formatSignedCompact, formatUsdRange, formatPercent, countryFlagEmoji, formatAccountAge } from '../utils/format';
import { GROWTH_RANGES } from '../utils/growthRanges';

// A leading 0-value point in the followers series is a broken/seed
// snapshot, not "tracking started at zero" -- no tracked account actually
// has 0 followers. Left as-is it draws a vertical cliff on GrowthChart and
// turns into a misleadingly huge first bar on DailyGrowthChart. Strip any
// leading zero(s) followed by a >=10x jump, and clear the new first
// point's daily_delta since it no longer has a real "previous day" to
// diff against -- DailyGrowthChart already drops null-delta points.
function stripPhantomZeroLead(points) {
  if (!points || points.length < 2) return points ?? [];
  let start = 0;
  while (
    start < points.length - 1 &&
    points[start].value === 0 &&
    points[start + 1].value >= 1000
  ) {
    start++;
  }
  if (start === 0) return points;
  const rest = points.slice(start);
  return [{ ...rest[0], daily_delta: null }, ...rest.slice(1)];
}

const TOOLTIPS = {
  followersYoutube: 'Latest scraped count. YouTube rounds subscriber counts to 3 significant figures, so large channels move in visible steps.',
  followersInstagram: 'Latest scraped follower count — exact, updated on each daily scrape.',
  delta28d: "Change vs the closest snapshot ~28 days ago. Shows '(partial)' when we've been tracking this account for less time.",
  viewsYoutube: 'Lifetime channel views reported by YouTube.',
  viewsInstagram: 'Views gained across posts in the last 28 days, reconstructed from per-post daily snapshots. Undercounts right after an account is first backfilled.',
  engagementRate: 'Average likes + comments on the last 12 posts, divided by current followers. Posts with hidden like counts are excluded.',
  earningsYoutube: 'Rough industry-rate estimate (not real revenue): monthly views × typical ad RPM for the channel’s country.',
  earningsInstagram: 'Estimated price for one sponsored post: follower count × typical rate, adjusted by engagement rate.',
  rank: 'Rank among the accounts tracked in this dashboard only — not a global or industry rank.',
  formatSplitYoutube: 'Shorts are videos of 3 minutes or less, as classified by YouTube.',
  formatSplitInstagram: 'Reels vs regular posts (photos, carousels).',
  dailyGrowth: 'Day-over-day change between consecutive daily snapshots. Gaps mean no snapshot was captured that day.',
  keyEvents: 'Markers show standout posts (2×+ outliers) and follower milestones. Hover a marker for details.',
};

function StatTile({ label, value, delta, deltaLabel, loading, infoTip }) {
  const deltaPositive = typeof delta === 'number' && delta > 0;
  const deltaNegative = typeof delta === 'number' && delta < 0;
  return (
    <div className="card p-5 flex flex-col gap-2 animate-fade-in">
      <div className="flex items-center gap-1.5">
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
        {infoTip && <InfoTip text={infoTip} />}
      </div>
      {loading ? (
        <Skeleton className="h-7 w-20" />
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

function SectionHeading({ children, infoTip }) {
  return (
    <div className="flex items-center gap-1.5">
      <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{children}</h3>
      {infoTip && <InfoTip text={infoTip} />}
    </div>
  );
}

export default function CreatorProfile() {
  const { influencerId } = useParams();

  const [stats, setStats] = useState(null);
  const [latestJob, setLatestJob] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);

  const [growthMetric, setGrowthMetric] = useState('followers');
  const [growthDays, setGrowthDays] = useState(28);
  const [growthPoints, setGrowthPoints] = useState([]);
  const [growthLoading, setGrowthLoading] = useState(true);
  const [events, setEvents] = useState([]);

  const [formatDays, setFormatDays] = useState(28);
  const [formatBreakdown, setFormatBreakdown] = useState(null);
  const [formatLoading, setFormatLoading] = useState(true);

  const [postsFilter, setPostsFilter] = useState('all');
  const [postsSort, setPostsSort] = useState('top');
  const [posts, setPosts] = useState([]);
  const [postsLoading, setPostsLoading] = useState(true);

  const [historyFollowers, setHistoryFollowers] = useState([]);
  const [historyViews, setHistoryViews] = useState([]);
  const [historyEarnings, setHistoryEarnings] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  const overviewRef = useRef(null);
  const contentRef = useRef(null);
  const growthRef = useRef(null);
  const aboutRef = useRef(null);

  const loadStats = useCallback(async () => {
    setLoading(true);
    setNotFound(false);
    try {
      const data = await getCreatorStats(influencerId);
      setStats(data);
      try {
        const jobs = await getInfluencerJobs(influencerId, 1);
        setLatestJob(jobs[0] ?? null);
      } catch {
        // Non-fatal -- the scrape-status dot just stays "never scraped"
        // rather than taking down the whole profile page over it.
        setLatestJob(null);
      }
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
    Promise.all([
      getCreatorGrowth(influencerId, growthDays, growthMetric),
      getCreatorKeyEvents(influencerId, growthDays),
    ])
      .then(([growthData, eventsData]) => {
        if (cancelled) return;
        setGrowthPoints(growthMetric === 'followers' ? stripPhantomZeroLead(growthData) : growthData);
        setEvents(eventsData);
      })
      .finally(() => { if (!cancelled) setGrowthLoading(false); });
    return () => { cancelled = true; };
  }, [influencerId, growthDays, growthMetric, stats]);

  useEffect(() => {
    if (!stats) return;
    let cancelled = false;
    setFormatLoading(true);
    getCreatorFormatBreakdown(influencerId, formatDays)
      .then((data) => { if (!cancelled) setFormatBreakdown(data); })
      .finally(() => { if (!cancelled) setFormatLoading(false); });
    return () => { cancelled = true; };
  }, [influencerId, formatDays, stats]);

  useEffect(() => {
    if (!stats) return;
    let cancelled = false;
    setPostsLoading(true);
    getCreatorPostPerformance(influencerId, 20, postsFilter === 'all' ? undefined : postsFilter, postsSort)
      .then((data) => { if (!cancelled) setPosts(data); })
      .finally(() => { if (!cancelled) setPostsLoading(false); });
    return () => { cancelled = true; };
  }, [influencerId, postsFilter, postsSort, stats]);

  // Independent of growthMetric (that only drives the chart above) --
  // the Daily Growth History table always wants followers + views +
  // earnings side by side, regardless of which single metric is charted.
  // views/earnings are YouTube-only (see CreatorSummary.total_views
  // docstring), so they're skipped for Instagram rather than firing
  // requests that would just come back empty.
  useEffect(() => {
    if (!stats) return;
    const isYt = stats.summary.platform === 'youtube';
    let cancelled = false;
    setHistoryLoading(true);
    Promise.all([
      getCreatorGrowth(influencerId, growthDays, 'followers'),
      isYt ? getCreatorGrowth(influencerId, growthDays, 'total_views') : Promise.resolve([]),
      isYt ? getCreatorGrowth(influencerId, growthDays, 'earnings') : Promise.resolve([]),
    ])
      .then(([followers, views, earnings]) => {
        if (cancelled) return;
        setHistoryFollowers(stripPhantomZeroLead(followers));
        setHistoryViews(views);
        setHistoryEarnings(earnings);
      })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [influencerId, growthDays, stats]);

  const scrollTo = (ref) => ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const handleEventClick = (event) => {
    if (event.permalink) window.open(event.permalink, '_blank', 'noreferrer');
  };

  const s = stats?.summary;
  const isYoutube = s?.platform === 'youtube';
  const followersLabel = isYoutube ? 'Subscribers' : 'Followers';
  const longFormLabel = isYoutube ? 'Videos' : 'Posts';
  const shortFormLabel = isYoutube ? 'Shorts' : 'Reels';
  // Hooks must run unconditionally on every render -- this stays above
  // the `notFound` early return below, even though its result is unused
  // in that branch.
  const growthMetricOptions = useMemo(() => {
    if (!isYoutube) return [{ value: 'followers', label: followersLabel }];
    return [
      { value: 'followers', label: followersLabel },
      { value: 'total_views', label: 'Views' },
      { value: 'earnings', label: 'Earnings' },
    ];
  }, [isYoutube, followersLabel]);

  if (notFound) {
    return <EmptyState title="Influencer not found" message="This influencer may have been deleted." />;
  }

  return (
    // gap-10 (40px), not gap-6 (24px) -- the sticky in-page nav below
    // renders ~44px tall, taller than the old gap. Since it's
    // position: sticky, it visually sits wherever the current section
    // boundary happens to be scrolled to, not just below its own DOM
    // position -- so with a 24px gap it was cutting into the tail end
    // of whichever section preceded the one you just jumped to via the
    // nav. 40px comfortably clears the bar's height at every boundary.
    <div className="flex flex-col gap-10 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/influencers">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-3.5 h-3.5" />
              Back
            </Button>
          </Link>
          {!loading && <Avatar src={s.profile_pic_url ? avatarUrl(influencerId) : null} handle={s.handle} />}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
                {loading ? 'Loading…' : formatHandle(s.handle, s.platform)}
              </h2>
              {!loading && stats?.about?.is_verified && (
                <BadgeCheck
                  className="w-4 h-4 shrink-0"
                  style={{ color: 'var(--color-accent)' }}
                  aria-label="Verified"
                />
              )}
              {!loading && (
                <span className="inline-flex items-center gap-1.5">
                  <PlatformBadge platform={s.platform} handle={s.handle} />
                  <ScrapeStatusIndicator status={latestJob?.status} />
                </span>
              )}
            </div>
            {!loading && (
              <div className="flex items-center flex-wrap gap-1.5 mt-1.5">
                {s.category_name && <HeaderPill>{s.category_name}</HeaderPill>}
                <HeaderPill icon={Video}>{formatCompactNumber(s.post_count)} {longFormLabel.toLowerCase()}</HeaderPill>
                {formatAccountAge(s.account_age_days) && (
                  <HeaderPill icon={Calendar}>{formatAccountAge(s.account_age_days)}</HeaderPill>
                )}
                {countryFlagEmoji(s.country) && (
                  <HeaderPill>
                    <span>{countryFlagEmoji(s.country)}</span> {s.country}
                  </HeaderPill>
                )}
                {s.updated_at && (
                  <HeaderPill icon={Clock}>Updated {format(parseISO(s.updated_at), 'MMM d, yyyy')}</HeaderPill>
                )}
              </div>
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
          <Banner variant="estimate" dismissible>
            All figures below are derived from public data scraped daily. Earnings figures are rough estimates, not real revenue.
          </Banner>

          {/* Sticky in-page section nav */}
          <div
            className="sticky top-0 z-10 flex items-center gap-1 -mx-1 px-1 py-2"
            style={{ background: 'var(--color-bg-primary)' }}
          >
            {[
              ['Overview', overviewRef],
              ['Content', contentRef],
              ['Growth', growthRef],
              ['About', aboutRef],
            ].map(([label, ref]) => (
              <button
                key={label}
                onClick={() => scrollTo(ref)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                style={{ color: 'var(--color-text-secondary)' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-bg-card-hover)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
              >
                {label}
              </button>
            ))}
          </div>

          {/* ── Overview ─────────────────────────────────────────────── */}
          <div ref={overviewRef} className="flex flex-col gap-4 scroll-mt-24">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatTile
                label={followersLabel}
                value={loading ? '' : (s.subscribers_hidden ? 'Hidden' : formatCompactNumber(s.followers))}
                delta={loading ? undefined : s.followers_delta_28d}
                deltaLabel={loading ? '' : (s.actual_window_days_28 < 28 ? `over ${s.actual_window_days_28}d (partial)` : 'in 28d')}
                loading={loading}
                infoTip={isYoutube ? TOOLTIPS.followersYoutube : TOOLTIPS.followersInstagram}
              />
              <StatTile
                label={isYoutube ? 'Total views' : 'Views (28d)'}
                value={loading ? '' : formatCompactNumber(isYoutube ? s.total_views : s.views_28d)}
                loading={loading}
                infoTip={isYoutube ? TOOLTIPS.viewsYoutube : TOOLTIPS.viewsInstagram}
              />
              <StatTile
                label={longFormLabel}
                value={loading ? '' : formatCompactNumber(s.post_count)}
                loading={loading}
              />
              <StatTile
                label="Engagement rate"
                value={loading ? '' : formatPercent(stats.engagement.engagement_rate)}
                loading={loading}
                infoTip={TOOLTIPS.engagementRate}
              />
            </div>

            <FormatSplitCard
              breakdown={formatBreakdown}
              loading={formatLoading}
              days={formatDays}
              onDaysChange={setFormatDays}
              longFormLabel={longFormLabel}
              shortFormLabel={shortFormLabel}
              infoTip={isYoutube ? TOOLTIPS.formatSplitYoutube : TOOLTIPS.formatSplitInstagram}
            />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="card p-5 flex flex-col gap-2">
                <SectionHeading infoTip={isYoutube ? TOOLTIPS.earningsYoutube : TOOLTIPS.earningsInstagram}>
                  Estimated earnings
                </SectionHeading>
                {loading ? (
                  <Skeleton className="h-7 w-32" />
                ) : stats.earnings ? (
                  <>
                    <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>
                      {formatUsdRange(stats.earnings.low_usd, stats.earnings.high_usd)}
                    </p>
                    <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      {stats.earnings.basis === 'monthly_ad_revenue' ? 'Estimated monthly ad revenue' : 'Estimated price per sponsored post'}
                    </p>
                  </>
                ) : (
                  <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Not enough data to estimate yet.</p>
                )}
              </div>

              <div className="card p-5 flex flex-col gap-2">
                <SectionHeading infoTip={TOOLTIPS.rank}>Tracked rankings</SectionHeading>
                {loading ? (
                  <Skeleton className="h-7 w-32" />
                ) : (
                  <div className="flex flex-col gap-1.5 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    <RankingRow label={`Among tracked ${platformLabel(s.platform)} accounts`} entry={stats.rankings.by_followers_overall} />
                    {s.category_name && (
                      <RankingRow label={`In "${s.category_name}"`} entry={stats.rankings.by_followers_in_category} />
                    )}
                    {stats.rankings.by_views_growth_28d_overall && (
                      <RankingRow label="By 28d view growth" entry={stats.rankings.by_views_growth_28d_overall} />
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ── Content ──────────────────────────────────────────────── */}
          <div ref={contentRef} className="card p-5 flex flex-col gap-3 min-w-0 scroll-mt-24">
            <SectionHeading>{isYoutube ? 'Videos' : 'Posts'}</SectionHeading>
            <PostsTable
              posts={posts}
              loading={postsLoading}
              sortMode={postsSort}
              onSortModeChange={setPostsSort}
              formatFilter={postsFilter}
              onFormatFilterChange={setPostsFilter}
              longFormLabel={longFormLabel}
              shortFormLabel={shortFormLabel}
            />
          </div>

          {/* ── Growth ───────────────────────────────────────────────── */}
          <div ref={growthRef} className="card p-5 flex flex-col gap-4 min-w-0 scroll-mt-24">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <SectionHeading infoTip={TOOLTIPS.keyEvents}>Growth</SectionHeading>
              <div className="flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-1">
                  {growthMetricOptions.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setGrowthMetric(opt.value)}
                      className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                      style={{
                        background: growthMetric === opt.value ? 'var(--color-accent-dim)' : 'transparent',
                        color: growthMetric === opt.value ? 'var(--color-accent)' : 'var(--color-text-muted)',
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1">
                  {GROWTH_RANGES.map((r) => (
                    <button
                      key={r.days}
                      onClick={() => setGrowthDays(r.days)}
                      className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                      style={{
                        background: growthDays === r.days ? 'var(--color-accent-dim)' : 'transparent',
                        color: growthDays === r.days ? 'var(--color-accent)' : 'var(--color-text-muted)',
                      }}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {growthLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : growthPoints.length > 0 && growthPoints.length < growthDays * 0.5 ? (
              <>
                <Banner variant="warning">
                  Tracking began {format(parseISO(growthPoints[0].date), 'MMM d, yyyy')} — showing {growthPoints.length} day(s) of data.
                </Banner>
                <GrowthChart points={growthPoints} metric={growthMetric} color={PLATFORM_COLORS[s?.platform]} events={events} onEventClick={handleEventClick} />
              </>
            ) : (
              <GrowthChart points={growthPoints} metric={growthMetric} color={PLATFORM_COLORS[s?.platform]} events={events} onEventClick={handleEventClick} />
            )}

            {growthMetric !== 'earnings' && (
              <>
                <div className="flex items-center gap-1.5 pt-2" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
                  <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>
                    Daily change
                  </h4>
                  <InfoTip text={TOOLTIPS.dailyGrowth} />
                </div>
                {growthLoading ? (
                  <Skeleton className="h-48 w-full" />
                ) : (
                  <DailyGrowthChart points={growthPoints} label={growthMetricOptions.find((o) => o.value === growthMetric)?.label} />
                )}
              </>
            )}

            <div className="flex items-center gap-1.5 pt-2" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
              <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>
                Daily {followersLabel.toLowerCase()} growth & view history
              </h4>
            </div>
            <DailyGrowthHistoryTable
              followersSeries={historyFollowers}
              viewsSeries={historyViews}
              earningsSeries={historyEarnings}
              followersLabel={followersLabel}
              loading={historyLoading}
            />
          </div>

          {/* ── About ────────────────────────────────────────────────── */}
          <div ref={aboutRef} className="flex flex-col gap-2 scroll-mt-24">
            <SectionHeading>About</SectionHeading>
            <AboutSection about={stats?.about} loading={loading} isYoutube={isYoutube} />
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
