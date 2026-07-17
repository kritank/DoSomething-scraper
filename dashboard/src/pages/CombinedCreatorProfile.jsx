import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Pencil, Trash2, Check, X, BadgeCheck } from 'lucide-react';
import { toast } from 'sonner';
import { getCreator, renameCreator, deleteCreator } from '../services/creatorService';
import { getCreatorStats, getCreatorGrowth } from '../services/creatorStatsService';
import Avatar from '../components/common/Avatar';
import PlatformBadge from '../components/common/PlatformBadge';
import Button from '../components/common/Button';
import Input from '../components/common/Input';
import EmptyState from '../components/common/EmptyState';
import Skeleton from '../components/common/Skeleton';
import GrowthChart from '../components/charts/GrowthChart';
import { formatHandle, platformLabel } from '../utils/platform';
import { formatCompactNumber } from '../utils/format';

// One combined creator can carry stats for each linked platform account --
// each fetched independently through the exact same per-influencer
// endpoints the single-platform profile page uses (getCreatorStats et al.),
// so "accurately mapped" falls out of reusing that already-correct data
// source rather than this page re-deriving anything itself.
async function loadPlatformStats(influencerId) {
  const [stats, growth] = await Promise.all([
    getCreatorStats(influencerId),
    getCreatorGrowth(influencerId, 90, 'followers').catch(() => []),
  ]);
  return { stats, growth };
}

function CombinedStat({ label, value }) {
  return (
    <div className="card p-5 flex flex-col gap-1">
      <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
      <p className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div>
      <div className="text-lg font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>{value}</div>
      <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{label}</div>
    </div>
  );
}

function PlatformCard({ influencerRef, data }) {
  const s = data?.stats?.summary;
  const about = data?.stats?.about;
  return (
    <div className="card p-5 flex flex-col gap-4 min-w-0">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <Avatar src={s?.profile_pic_url} handle={influencerRef.handle} size={36} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h4 className="text-sm font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
                {formatHandle(influencerRef.handle, influencerRef.platform)}
              </h4>
              {about?.is_verified && (
                <BadgeCheck className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--color-accent)' }} aria-label="Verified" />
              )}
            </div>
            <PlatformBadge platform={influencerRef.platform} />
          </div>
        </div>
        <Link
          to={`/influencers/${influencerRef.influencer_id}`}
          className="flex items-center gap-1 text-xs font-medium hover:underline shrink-0"
          style={{ color: 'var(--color-accent)' }}
        >
          Full profile
          <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      {!s ? (
        <EmptyState title="No data yet" message="This account hasn't completed a scrape yet." />
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MiniStat label="Followers" value={formatCompactNumber(s.followers)} />
            <MiniStat label="Views (28d)" value={s.views_28d != null ? formatCompactNumber(s.views_28d) : '—'} />
            <MiniStat label="Posts" value={formatCompactNumber(s.post_count)} />
            <MiniStat
              label="Engagement"
              value={data.stats.engagement?.engagement_rate != null ? `${(data.stats.engagement.engagement_rate * 100).toFixed(2)}%` : '—'}
            />
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--color-text-muted)' }}>
              Followers, last 90 days
            </p>
            {data.growth?.length > 0 ? (
              <GrowthChart points={data.growth} metric="followers" color={influencerRef.platform === 'youtube' ? '#ef4444' : '#e1306c'} />
            ) : (
              <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Not enough history yet.</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function CombinedCreatorProfile() {
  const { creatorId } = useParams();
  const navigate = useNavigate();

  const [creator, setCreator] = useState(null);
  const [platformData, setPlatformData] = useState({});
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setNotFound(false);
    try {
      const data = await getCreator(creatorId);
      setCreator(data);
      const entries = await Promise.all(
        data.influencers.map(async (ref) => [ref.influencer_id, await loadPlatformStats(ref.influencer_id)]),
      );
      setPlatformData(Object.fromEntries(entries));
    } catch {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [creatorId]);

  useEffect(() => {
    load();
  }, [load]);

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

  const totals = creator
    ? creator.influencers.reduce(
        (acc, ref) => {
          const s = platformData[ref.influencer_id]?.stats?.summary;
          if (!s) return acc;
          acc.followers += s.followers ?? 0;
          acc.views28d += s.views_28d ?? 0;
          acc.posts += s.post_count ?? 0;
          return acc;
        },
        { followers: 0, views28d: 0, posts: 0 },
      )
    : null;

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
              <h2 className="text-xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
                {loading ? 'Loading…' : creator?.name}
              </h2>
              {!loading && creator && (
                <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                  Linked across {creator.influencers.length} platform{creator.influencers.length === 1 ? '' : 's'}
                </p>
              )}
            </div>
          )}
        </div>
        {!loading && creator && !editingName && (
          <div className="flex items-center gap-1 shrink-0">
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
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <CombinedStat label="Combined followers" value={formatCompactNumber(totals.followers)} />
            <CombinedStat label="Combined views (28d)" value={formatCompactNumber(totals.views28d)} />
            <CombinedStat label="Combined posts" value={formatCompactNumber(totals.posts)} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 min-w-0">
            {creator.influencers.map((ref) => (
              <PlatformCard key={ref.influencer_id} influencerRef={ref} data={platformData[ref.influencer_id]} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
