import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowUpDown, ChevronLeft, ChevronRight, ExternalLink, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';
import { listPosts } from '../services/postsService';
import { getCategories } from '../services/influencerService';
import { getDashboardStatus } from '../services/dashboardService';
import Button from '../components/common/Button';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import InfoTip from '../components/common/InfoTip';
import PlatformBadge from '../components/common/PlatformBadge';
import PlatformFilter from '../components/common/PlatformFilter';
import { useAppStore } from '../store/useAppStore';
import { formatHandle } from '../utils/platform';

const PAGE_SIZE = 50;

const OUTLIER_TOOLTIP =
  "A post's views (or likes) vs its own creator's median over their previous 30 posts, blended with current momentum and engagement. 2x+ = a real outlier. Compares each post only to that creator's own history, across tracked creators -- never a platform-wide rank.";

export default function Content() {
  const enabledPlatforms = useAppStore((s) => s.enabledPlatforms);

  const [posts, setPosts] = useState([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState([]);
  const [influencers, setInfluencers] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const [influencerId, setInfluencerId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [accountType, setAccountType] = useState('');
  // Local, further-narrowing scope within whatever the Header's global
  // filter allows -- see PlatformFilter's docstring. Re-clamped to the
  // global set below whenever it changes, so this page never holds a
  // selection the user just turned off app-wide.
  const [selectedPlatforms, setSelectedPlatforms] = useState(enabledPlatforms);
  const [sort, setSort] = useState('posted_at');
  const [sortDir, setSortDir] = useState('desc');
  const [page, setPage] = useState(0);
  // Cross-creator outliers feed (docs/OUTLIERS_PLAN.md Phase 3) -- 2x+
  // matches the badge threshold PostsTable already uses on profile pages.
  const [outliersOnly, setOutliersOnly] = useState(false);

  useEffect(() => {
    setSelectedPlatforms((prev) => prev.filter((p) => enabledPlatforms.includes(p)));
  }, [enabledPlatforms]);

  const loadFilters = useCallback(async () => {
    const [cats, status] = await Promise.all([getCategories(), getDashboardStatus()]);
    setCategories(cats);
    setInfluencers(status.map((r) => ({ id: r.influencer_id, handle: r.handle, platform: r.platform })));
  }, []);

  const loadPosts = useCallback(async () => {
    if (selectedPlatforms.length === 0) {
      setPosts([]);
      setTotal(0);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await listPosts({
        influencer_id: influencerId || undefined,
        category_id: categoryId || undefined,
        account_type: accountType || undefined,
        platforms: selectedPlatforms,
        min_score: outliersOnly ? 2.0 : undefined,
        sort,
        sort_dir: sortDir,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setPosts(data.posts);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [influencerId, categoryId, accountType, selectedPlatforms, outliersOnly, sort, sortDir, page]);

  useEffect(() => {
    loadFilters();
  }, [loadFilters]);

  useEffect(() => {
    loadPosts();
  }, [loadPosts]);

  const handlePlatformChange = (next) => {
    setSelectedPlatforms(next);
    setPage(0);
  };

  const toggleSort = (key) => {
    if (sort === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(key);
      setSortDir('desc');
    }
    setPage(0);
  };

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  if (error) {
    return <ErrorState title="Couldn't load posts" description={error} onRetry={loadPosts} />;
  }

  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Content</h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Every scraped post, browsable and sortable
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={loadPosts} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      <div className="flex items-center gap-3 flex-wrap justify-between">
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={influencerId}
            onChange={(e) => { setInfluencerId(e.target.value); setPage(0); }}
            className="px-3 py-2.5 rounded-xl text-sm outline-none border"
            style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', borderColor: 'var(--color-border-default)' }}
          >
            <option value="">All influencers</option>
            {influencers.map((i) => (
              <option key={i.id} value={i.id}>{formatHandle(i.handle, i.platform)}</option>
            ))}
          </select>
          <select
            value={categoryId}
            onChange={(e) => { setCategoryId(e.target.value); setPage(0); }}
            className="px-3 py-2.5 rounded-xl text-sm outline-none border"
            style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', borderColor: 'var(--color-border-default)' }}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <select
            value={accountType}
            onChange={(e) => { setAccountType(e.target.value); setPage(0); }}
            className="px-3 py-2.5 rounded-xl text-sm outline-none border"
            style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', borderColor: 'var(--color-border-default)' }}
          >
            <option value="">All types</option>
            <option value="business">Business</option>
            <option value="individual">Individual</option>
          </select>
          <div
            className="pl-3 pr-2 py-2.5 rounded-xl text-sm font-medium border inline-flex items-center gap-1.5"
            style={{
              background: outliersOnly ? 'var(--color-success-muted)' : 'var(--color-bg-secondary)',
              color: outliersOnly ? 'var(--color-success)' : 'var(--color-text-secondary)',
              borderColor: outliersOnly ? 'var(--color-success)' : 'var(--color-border-default)',
            }}
          >
            <button
              onClick={() => { setOutliersOnly((v) => !v); setPage(0); }}
              className="transition-colors"
            >
              2×+ outliers only
            </button>
            <InfoTip text={OUTLIER_TOOLTIP} side="bottom" />
          </div>
        </div>
        <PlatformFilter value={selectedPlatforms} onChange={handlePlatformChange} options={enabledPlatforms} />
      </div>

      <div className="card p-5 flex flex-col gap-4">
        {selectedPlatforms.length === 0 ? (
          <EmptyState title="No platform selected" message="Select at least one platform above to see its content." />
        ) : loading ? (
          <div className="h-64 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
        ) : posts.length === 0 ? (
          <EmptyState title="No posts found" message="Try clearing your filters, or wait for scrapes to run." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Influencer</th>
                    <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Platform</th>
                    <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Title / Caption</th>
                    {[
                      { key: 'posted_at', label: 'Posted' },
                      { key: 'likes', label: 'Likes' },
                      { key: 'comments', label: 'Comments' },
                    ].map((col) => (
                      <th
                        key={col.key}
                        onClick={() => toggleSort(col.key)}
                        className="text-left py-2.5 px-3 font-medium cursor-pointer select-none whitespace-nowrap"
                        style={{ color: 'var(--color-text-secondary)' }}
                      >
                        <span className="inline-flex items-center gap-1">{col.label}<ArrowUpDown className="w-3 h-3 opacity-50" /></span>
                      </th>
                    ))}
                    <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Views</th>
                    <th
                      className="text-left py-2.5 px-3 font-medium cursor-help"
                      style={{ color: 'var(--color-text-secondary)' }}
                      title="Instagram only -- YouTube's public API exposes no share/repost count for any video, so this is always blank there, not a bug."
                    >
                      Reposts
                    </th>
                    <th
                      onClick={() => toggleSort('outlier_score')}
                      className="text-left py-2.5 px-3 font-medium cursor-pointer select-none whitespace-nowrap"
                      style={{ color: 'var(--color-text-secondary)' }}
                    >
                      <span className="inline-flex items-center gap-1">
                        Outlier<ArrowUpDown className="w-3 h-3 opacity-50" />
                        <InfoTip text={OUTLIER_TOOLTIP} side="bottom" />
                      </span>
                    </th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {posts.map((p) => (
                    <tr key={p.id} className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                      <td className="py-2.5 px-3 whitespace-nowrap font-medium" style={{ color: 'var(--color-text-primary)' }}>
                        {formatHandle(p.handle, p.platform)}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <PlatformBadge platform={p.platform} handle={p.handle} />
                      </td>
                      <td
                        className="py-2.5 px-3 max-w-[320px] truncate"
                        style={{ color: 'var(--color-text-secondary)' }}
                        title={p.title ? `${p.title}\n\n${p.caption ?? ''}` : (p.caption ?? undefined)}
                      >
                        {p.permalink ? (
                          <a href={p.permalink} target="_blank" rel="noreferrer" className="hover:underline">
                            {p.title || p.caption || '—'}
                          </a>
                        ) : (
                          p.title || p.caption || '—'
                        )}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                        {format(new Date(p.posted_at), 'MMM d, yyyy')}
                      </td>
                      <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.likes?.toLocaleString() ?? '—'}</td>
                      <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.comments?.toLocaleString() ?? '—'}</td>
                      <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.views?.toLocaleString() ?? '—'}</td>
                      <td
                        className="py-2.5 px-3"
                        style={{ color: 'var(--color-text-secondary)' }}
                        title={p.reposts == null ? "Not publicly available on YouTube" : undefined}
                      >
                        {p.reposts?.toLocaleString() ?? '—'}
                      </td>
                      <td className="py-2.5 px-3">
                        {p.baseline_multiple != null ? (
                          <span
                            className="px-2 py-0.5 rounded-full text-xs font-semibold"
                            style={{
                              background: p.baseline_multiple >= 2 ? 'var(--color-success-muted)' : 'var(--color-bg-card-hover)',
                              color: p.baseline_multiple >= 2 ? 'var(--color-success)' : 'var(--color-text-muted)',
                            }}
                          >
                            {p.baseline_multiple.toFixed(1)}×
                          </span>
                        ) : '—'}
                      </td>
                      <td className="py-2.5 px-3">
                        {p.permalink && (
                          <a href={p.permalink} target="_blank" rel="noreferrer">
                            <ExternalLink className="w-3.5 h-3.5" style={{ color: 'var(--color-accent)' }} />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between">
              <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                {total.toLocaleString()} post{total === 1 ? '' : 's'} · page {page + 1} of {totalPages}
              </p>
              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
                  <ChevronLeft className="w-3.5 h-3.5" />
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>
                  <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
