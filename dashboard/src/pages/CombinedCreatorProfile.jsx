import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Pencil, Trash2, Check, X, BadgeCheck, Video, Calendar, Clock, RefreshCw, Layers } from 'lucide-react';
import { toast } from 'sonner';
import { getCreator, renameCreator, deleteCreator } from '../services/creatorService';
import {
  getCreatorStats,
  getCreatorGrowth,
  getCreatorKeyEvents,
  getCreatorFormatBreakdown,
  getCreatorPostPerformance,
} from '../services/creatorStatsService';
import { getInfluencerJobs } from '../services/influencerJobsService';
import Avatar from '../components/common/Avatar';
import PlatformIcon from '../components/common/PlatformIcon';
import PlatformVerifiedBadge from '../components/common/PlatformVerifiedBadge';
import ScrapeStatusIndicator from '../components/common/ScrapeStatusIndicator';
import HeaderPill from '../components/common/HeaderPill';
import Button from '../components/common/Button';
import Input from '../components/common/Input';
import EmptyState from '../components/common/EmptyState';
import Skeleton from '../components/common/Skeleton';
import InfoTip from '../components/common/InfoTip';
import GrowthChart from '../components/charts/GrowthChart';
import DailyGrowthChart from '../components/charts/DailyGrowthChart';
import FormatSplitCard from '../components/creator/FormatSplitCard';
import PostsTable from '../components/creator/PostsTable';
import DailyGrowthHistoryTable from '../components/creator/DailyGrowthHistoryTable';
import AboutSection from '../components/creator/AboutSection';
import { formatHandle } from '../utils/platform';
import { formatCompactNumber, formatUsdRange, countryFlagEmoji } from '../utils/format';
import { GROWTH_RANGES } from '../utils/growthRanges';
import { mergeGrowthSeries, mergeEarningsSeries, mergeFormatBreakdowns } from '../utils/mergeSeries';
import { avatarUrl } from '../services/apiClient';

const COMBINED_COLOR = '#8b5cf6';

function CombinedStat({ label, value, loading }) {
  return (
    <div className="card p-5 flex flex-col gap-1">
      <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
      {loading ? <Skeleton className="h-7 w-24" /> : (
        <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
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

function SegmentedControl({ options, value, onChange }) {
  return (
    <div className="flex items-center gap-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
          style={{
            background: value === opt.value ? 'var(--color-accent-dim)' : 'transparent',
            color: value === opt.value ? 'var(--color-accent)' : 'var(--color-text-muted)',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function PlatformMiniHeader({ influencerRef, verified }) {
  return (
    <div className="flex items-center gap-2">
      <PlatformIcon platform={influencerRef.platform} className="w-6 h-6 rounded-md" handle={influencerRef.handle} />
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-sm font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
          {formatHandle(influencerRef.handle, influencerRef.platform)}
        </span>
        {verified && <BadgeCheck className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--color-accent)' }} aria-label="Verified" />}
      </div>
      <Link
        to={`/influencers/${influencerRef.influencer_id}`}
        className="flex items-center gap-1 text-xs font-medium hover:underline shrink-0 ml-auto"
        style={{ color: 'var(--color-accent)' }}
      >
        Full profile
        <ArrowRight className="w-3 h-3" />
      </Link>
    </div>
  );
}

export default function CombinedCreatorProfile() {
  const { creatorId } = useParams();
  const navigate = useNavigate();

  const [creator, setCreator] = useState(null);
  const [statsByInfluencer, setStatsByInfluencer] = useState({});
  const [latestJobByInfluencer, setLatestJobByInfluencer] = useState({});
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [saving, setSaving] = useState(false);

  const [viewMode, setViewMode] = useState('combined'); // 'combined' | 'byPlatform'
  const [growthMetric, setGrowthMetric] = useState('followers');
  const [growthDays, setGrowthDays] = useState(28);
  const [growthByInfluencer, setGrowthByInfluencer] = useState({});
  const [eventsByInfluencer, setEventsByInfluencer] = useState({});
  const [growthLoading, setGrowthLoading] = useState(true);

  const [formatDays, setFormatDays] = useState(28);
  const [formatByInfluencer, setFormatByInfluencer] = useState({});
  const [formatLoading, setFormatLoading] = useState(true);

  const [postsSort, setPostsSort] = useState('top');
  const [postsFilter, setPostsFilter] = useState('all');
  const [postsByInfluencer, setPostsByInfluencer] = useState({});
  const [postsLoading, setPostsLoading] = useState(true);

  const [historyByInfluencer, setHistoryByInfluencer] = useState({});
  const [historyLoading, setHistoryLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setNotFound(false);
    try {
      const data = await getCreator(creatorId);
      setCreator(data);
      const entries = await Promise.all(
        data.influencers.map(async (ref) => [ref.influencer_id, await getCreatorStats(ref.influencer_id)]),
      );
      setStatsByInfluencer(Object.fromEntries(entries));
      try {
        const jobEntries = await Promise.all(
          data.influencers.map(async (ref) => {
            const jobs = await getInfluencerJobs(ref.influencer_id, 1);
            return [ref.influencer_id, jobs[0] ?? null];
          }),
        );
        setLatestJobByInfluencer(Object.fromEntries(jobEntries));
      } catch {
        // Non-fatal -- the scrape-status dots just stay "never scraped"
        // rather than taking down the whole profile page over it.
        setLatestJobByInfluencer({});
      }
    } catch {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [creatorId]);

  useEffect(() => {
    load();
  }, [load]);

  const hasYoutube = creator?.influencers.some((ref) => ref.platform === 'youtube') ?? false;

  const growthMetricOptions = useMemo(() => {
    const opts = [{ value: 'followers', label: 'Followers' }];
    if (hasYoutube) opts.push({ value: 'total_views', label: 'Views' }, { value: 'earnings', label: 'Earnings' });
    return opts;
  }, [hasYoutube]);

  // Growth + key events, per linked account, for the currently selected
  // metric/range -- total_views/earnings only exist for YouTube (see
  // CreatorSummary.total_views docstring), so non-YouTube accounts are
  // skipped for those metrics rather than firing a request that would
  // just come back empty.
  useEffect(() => {
    if (!creator) return;
    let cancelled = false;
    setGrowthLoading(true);
    Promise.all(
      creator.influencers.map(async (ref) => {
        const supported = growthMetric === 'followers' || ref.platform === 'youtube';
        const [growth, events] = await Promise.all([
          supported ? getCreatorGrowth(ref.influencer_id, growthDays, growthMetric) : Promise.resolve([]),
          getCreatorKeyEvents(ref.influencer_id, growthDays),
        ]);
        return [ref.influencer_id, growth, events];
      }),
    )
      .then((results) => {
        if (cancelled) return;
        setGrowthByInfluencer(Object.fromEntries(results.map(([id, growth]) => [id, growth])));
        setEventsByInfluencer(Object.fromEntries(results.map(([id, , events]) => [id, events])));
      })
      .finally(() => { if (!cancelled) setGrowthLoading(false); });
    return () => { cancelled = true; };
  }, [creator, growthDays, growthMetric]);

  useEffect(() => {
    if (!creator) return;
    let cancelled = false;
    setFormatLoading(true);
    Promise.all(
      creator.influencers.map(async (ref) => [ref.influencer_id, await getCreatorFormatBreakdown(ref.influencer_id, formatDays)]),
    )
      .then((results) => { if (!cancelled) setFormatByInfluencer(Object.fromEntries(results)); })
      .finally(() => { if (!cancelled) setFormatLoading(false); });
    return () => { cancelled = true; };
  }, [creator, formatDays]);

  useEffect(() => {
    if (!creator) return;
    let cancelled = false;
    setPostsLoading(true);
    Promise.all(
      creator.influencers.map(async (ref) => {
        const posts = await getCreatorPostPerformance(
          ref.influencer_id, 20, postsFilter === 'all' ? undefined : postsFilter, postsSort,
        );
        return posts.map((p) => ({ ...p, platform: ref.platform, handle: ref.handle }));
      }),
    )
      .then((results) => { if (!cancelled) setPostsByInfluencer(Object.fromEntries(creator.influencers.map((ref, i) => [ref.influencer_id, results[i]]))); })
      .finally(() => { if (!cancelled) setPostsLoading(false); });
    return () => { cancelled = true; };
  }, [creator, postsFilter, postsSort]);

  useEffect(() => {
    if (!creator) return;
    let cancelled = false;
    setHistoryLoading(true);
    Promise.all(
      creator.influencers.map(async (ref) => {
        const isYt = ref.platform === 'youtube';
        const [followers, views, earnings] = await Promise.all([
          getCreatorGrowth(ref.influencer_id, growthDays, 'followers'),
          isYt ? getCreatorGrowth(ref.influencer_id, growthDays, 'total_views') : Promise.resolve([]),
          isYt ? getCreatorGrowth(ref.influencer_id, growthDays, 'earnings') : Promise.resolve([]),
        ]);
        return [ref.influencer_id, { followers, views, earnings }];
      }),
    )
      .then((results) => { if (!cancelled) setHistoryByInfluencer(Object.fromEntries(results)); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [creator, growthDays]);

  // Hooks must run unconditionally on every render -- these stay above the
  // `notFound` early return below, even though their results are unused
  // in that branch (see CreatorProfile.jsx's growthMetricOptions for the
  // same pattern).
  const combinedGrowth = useMemo(() => mergeGrowthSeries(Object.values(growthByInfluencer)), [growthByInfluencer]);
  const combinedEvents = useMemo(() => Object.values(eventsByInfluencer).flat().sort((a, b) => (a.date < b.date ? -1 : 1)), [eventsByInfluencer]);
  const combinedFormat = useMemo(() => mergeFormatBreakdowns(Object.values(formatByInfluencer)), [formatByInfluencer]);
  const combinedPosts = useMemo(() => {
    const all = Object.values(postsByInfluencer).flat();
    const sorted = postsSort === 'top'
      ? [...all].sort((a, b) => (b.outlier_score ?? -1) - (a.outlier_score ?? -1) || (b.views ?? b.likes ?? 0) - (a.views ?? a.likes ?? 0))
      : [...all].sort((a, b) => (a.posted_at < b.posted_at ? 1 : -1));
    return sorted.slice(0, 20);
  }, [postsByInfluencer, postsSort]);
  const combinedHistory = useMemo(() => {
    const entries = Object.values(historyByInfluencer);
    return {
      followers: mergeGrowthSeries(entries.map((e) => e.followers)),
      views: mergeGrowthSeries(entries.map((e) => e.views)),
      earnings: mergeEarningsSeries(entries.map((e) => e.earnings)),
    };
  }, [historyByInfluencer]);

  const handleSaveName = async () => {
    const name = nameDraft.trim();
    if (!name || saving || !creator) return;
    if (name === creator.name) {
      setEditingName(false);
      return;
    }
    setSaving(true);
    try {
      await renameCreator(creatorId, name);
      toast.success(`Renamed to "${name}"`);
      setEditingName(false);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!creator) return;
    if (
      !window.confirm(
        `Unlink "${creator.name}"'s ${creator.influencers.length} platform accounts from each other? Each account and all its scraped data stays untouched -- this only removes the cross-platform grouping.`,
      )
    ) {
      return;
    }
    try {
      await deleteCreator(creatorId);
      toast.success(`"${creator.name}" unlinked`);
      navigate('/influencers');
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  if (notFound) {
    return <EmptyState title="Creator not found" message="This creator may have been unlinked or deleted." />;
  }

  const statsList = creator ? creator.influencers.map((ref) => statsByInfluencer[ref.influencer_id]).filter(Boolean) : [];

  const totals = statsList.reduce(
    (acc, data) => {
      const s = data.summary;
      acc.followers += s.followers ?? 0;
      acc.views28d += s.views_28d ?? 0;
      acc.posts += s.post_count ?? 0;
      if (data.earnings) {
        acc.earningsLow += data.earnings.low_usd;
        acc.earningsHigh += data.earnings.high_usd;
        acc.hasEarnings = true;
      }
      return acc;
    },
    { followers: 0, views28d: 0, posts: 0, earningsLow: 0, earningsHigh: 0, hasEarnings: false },
  );

  const joinedDates = statsList.map((d) => d.about?.created_at_platform).filter(Boolean).sort();
  const earliestJoined = joinedDates[0];
  const countries = [...new Set(statsList.map((d) => d.about?.country || d.summary?.country).filter(Boolean))];
  const updatedDates = statsList.map((d) => d.summary?.updated_at).filter(Boolean).sort();
  const latestUpdated = updatedDates[updatedDates.length - 1];
  const primaryAvatarInfluencerId = statsList.find((d) => d.summary?.profile_pic_url)?.summary?.influencer_id;
  const primaryAvatar = avatarUrl(primaryAvatarInfluencerId);

  const handleEventClick = (event) => {
    if (event.permalink) window.open(event.permalink, '_blank', 'noreferrer');
  };

  return (
    <div className="flex flex-col gap-8 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/influencers">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-3.5 h-3.5" />
              Back
            </Button>
          </Link>
          {!loading && <Avatar src={primaryAvatar} handle={creator?.name} />}
          {editingName ? (
            <div className="flex items-center gap-2 min-w-0">
              <Input
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveName()}
                autoFocus
              />
              <Button variant="ghost" size="sm" title="Save" onClick={handleSaveName} loading={saving}>
                <Check className="w-3.5 h-3.5" style={{ color: 'var(--color-success)' }} />
              </Button>
              <Button variant="ghost" size="sm" title="Cancel" onClick={() => setEditingName(false)}>
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>
          ) : (
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
                  {loading ? 'Loading…' : creator?.name}
                </h2>
                {!loading && creator?.influencers.map((ref) => (
                  <span key={ref.influencer_id} className="inline-flex items-center gap-1">
                    <PlatformVerifiedBadge
                      platform={ref.platform}
                      verified={statsByInfluencer[ref.influencer_id]?.about?.is_verified}
                      handle={ref.handle}
                    />
                    <ScrapeStatusIndicator status={latestJobByInfluencer[ref.influencer_id]?.status} />
                  </span>
                ))}
              </div>
              {!loading && creator && (
                <div className="flex items-center flex-wrap gap-1.5 mt-1.5">
                  <HeaderPill icon={Video}>{formatCompactNumber(totals.posts)} posts</HeaderPill>
                  {earliestJoined && (
                    <HeaderPill icon={Calendar}>
                      Joined {new Date(earliestJoined).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
                    </HeaderPill>
                  )}
                  {countries.map((c) => countryFlagEmoji(c) && (
                    <HeaderPill key={c}><span>{countryFlagEmoji(c)}</span> {c}</HeaderPill>
                  ))}
                  {latestUpdated && (
                    <HeaderPill icon={Clock}>
                      Updated {new Date(latestUpdated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </HeaderPill>
                  )}
                  <HeaderPill icon={Layers}>Linked across {creator.influencers.length} platform{creator.influencers.length === 1 ? '' : 's'}</HeaderPill>
                </div>
              )}
            </div>
          )}
        </div>
        {!loading && creator && !editingName && (
          <div className="flex items-center gap-1 shrink-0">
            <Button variant="secondary" size="sm" onClick={load} loading={loading}>
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </Button>
            <Button
              variant="ghost"
              size="sm"
              title="Rename creator"
              onClick={() => {
                setNameDraft(creator.name);
                setEditingName(true);
              }}
            >
              <Pencil className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
            </Button>
            <Button variant="ghost" size="sm" title="Unlink creator (keeps both accounts)" onClick={handleDelete}>
              <Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--color-danger)' }} />
            </Button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <CombinedStat label="Combined followers" value={formatCompactNumber(totals.followers)} />
            <CombinedStat label="Combined views (28d)" value={formatCompactNumber(totals.views28d)} />
            <CombinedStat label="Combined posts" value={formatCompactNumber(totals.posts)} />
            <CombinedStat
              label="Combined est. earnings"
              value={totals.hasEarnings ? formatUsdRange(totals.earningsLow, totals.earningsHigh) : '—'}
            />
          </div>

          {/* ── Growth ───────────────────────────────────────────────── */}
          <div className="card p-5 flex flex-col gap-4 min-w-0">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <SectionHeading infoTip="Markers show standout posts (2×+ outliers) and follower milestones, merged across every linked platform. Hover a marker for details.">
                Growth
              </SectionHeading>
              <div className="flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-1 rounded-lg p-0.5" style={{ background: 'var(--color-bg-card-hover)' }}>
                  {[{ value: 'combined', label: 'Combined' }, { value: 'byPlatform', label: 'By platform' }].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setViewMode(opt.value)}
                      className="px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
                      style={{
                        background: viewMode === opt.value ? 'var(--color-accent)' : 'transparent',
                        color: viewMode === opt.value ? '#fff' : 'var(--color-text-muted)',
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                <SegmentedControl options={growthMetricOptions} value={growthMetric} onChange={setGrowthMetric} />
                <SegmentedControl options={GROWTH_RANGES.map((r) => ({ value: r.days, label: r.label }))} value={growthDays} onChange={setGrowthDays} />
              </div>
            </div>

            {growthLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : viewMode === 'combined' ? (
              <>
                <GrowthChart points={combinedGrowth} metric={growthMetric} color={COMBINED_COLOR} events={combinedEvents} onEventClick={handleEventClick} />
                {growthMetric !== 'earnings' && (
                  <>
                    <div className="flex items-center gap-1.5 pt-2" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
                      <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>
                        Combined daily change
                      </h4>
                    </div>
                    <DailyGrowthChart points={combinedGrowth} label={growthMetricOptions.find((o) => o.value === growthMetric)?.label} />
                  </>
                )}
              </>
            ) : (
              <div className="flex flex-col gap-6">
                {creator.influencers.map((ref) => {
                  const points = growthByInfluencer[ref.influencer_id] ?? [];
                  const about = statsByInfluencer[ref.influencer_id]?.about;
                  if (points.length === 0) return null;
                  return (
                    <div key={ref.influencer_id} className="flex flex-col gap-2">
                      <PlatformMiniHeader influencerRef={ref} verified={about?.is_verified} />
                      <GrowthChart
                        points={points}
                        metric={growthMetric}
                        color={ref.platform === 'youtube' ? '#ff0000' : '#d62976'}
                        events={eventsByInfluencer[ref.influencer_id] ?? []}
                        onEventClick={handleEventClick}
                      />
                    </div>
                  );
                })}
                {creator.influencers.every((ref) => (growthByInfluencer[ref.influencer_id] ?? []).length === 0) && (
                  <EmptyState title="Not enough history yet" message="Growth charts need at least a couple of days of snapshots to plot." />
                )}
              </div>
            )}
          </div>

          {/* ── Format split ─────────────────────────────────────────── */}
          <FormatSplitCard
            breakdown={combinedFormat}
            loading={formatLoading}
            days={formatDays}
            onDaysChange={setFormatDays}
            longFormLabel="Long-form"
            shortFormLabel="Shorts/Reels"
            infoTip="Combined across every linked platform. YouTube Shorts and Instagram Reels both count as short-form; regular videos and feed posts count as long-form."
          />

          {creator.influencers.length > 1 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {creator.influencers.map((ref) => (
                <div key={ref.influencer_id} className="card p-5 flex flex-col gap-3">
                  <PlatformMiniHeader influencerRef={ref} verified={statsByInfluencer[ref.influencer_id]?.about?.is_verified} />
                  <FormatSplitCard
                    breakdown={formatByInfluencer[ref.influencer_id]}
                    loading={formatLoading}
                    days={formatDays}
                    onDaysChange={setFormatDays}
                    longFormLabel={ref.platform === 'youtube' ? 'Videos' : 'Posts'}
                    shortFormLabel={ref.platform === 'youtube' ? 'Shorts' : 'Reels'}
                  />
                </div>
              ))}
            </div>
          )}

          {/* ── Videos ───────────────────────────────────────────────── */}
          <div className="card p-5 flex flex-col gap-3 min-w-0">
            <SectionHeading>Videos</SectionHeading>
            <PostsTable
              posts={combinedPosts}
              loading={postsLoading}
              sortMode={postsSort}
              onSortModeChange={setPostsSort}
              formatFilter={postsFilter}
              onFormatFilterChange={setPostsFilter}
              longFormLabel="Long-form"
              shortFormLabel="Shorts/Reels"
              showPlatformColumn
            />
          </div>

          {/* ── Daily growth history ────────────────────────────────── */}
          <div className="card p-5 flex flex-col gap-3 min-w-0">
            <SectionHeading>Daily growth & view history</SectionHeading>
            <DailyGrowthHistoryTable
              followersSeries={combinedHistory.followers}
              viewsSeries={combinedHistory.views}
              earningsSeries={combinedHistory.earnings}
              followersLabel="Combined followers"
              loading={historyLoading}
            />
          </div>

          {/* ── About ────────────────────────────────────────────────── */}
          <div className="flex flex-col gap-4">
            <SectionHeading>About</SectionHeading>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-w-0">
              {creator.influencers.map((ref) => {
                const data = statsByInfluencer[ref.influencer_id];
                return (
                  <div key={ref.influencer_id} className="flex flex-col gap-2 min-w-0">
                    <PlatformMiniHeader influencerRef={ref} verified={data?.about?.is_verified} />
                    <AboutSection about={data?.about} loading={loading} isYoutube={ref.platform === 'youtube'} />
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
