import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowUpDown, ChevronLeft, ChevronRight, ExternalLink, RefreshCw } from 'lucide-react';
import { format } from 'date-fns';
import { listPosts } from '../services/postsService';
import { getCategories } from '../services/influencerService';
import { getDashboardStatus } from '../services/dashboardService';
import Button from '../components/common/Button';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';

const PAGE_SIZE = 50;

export default function Content() {
  const [posts, setPosts] = useState([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState([]);
  const [influencers, setInfluencers] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const [influencerId, setInfluencerId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [sort, setSort] = useState('posted_at');
  const [sortDir, setSortDir] = useState('desc');
  const [page, setPage] = useState(0);

  const loadFilters = useCallback(async () => {
    const [cats, status] = await Promise.all([getCategories(), getDashboardStatus()]);
    setCategories(cats);
    setInfluencers(status.map((r) => ({ id: r.influencer_id, handle: r.handle })));
  }, []);

  const loadPosts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPosts({
        influencer_id: influencerId || undefined,
        category_id: categoryId || undefined,
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
  }, [influencerId, categoryId, sort, sortDir, page]);

  useEffect(() => {
    loadFilters();
  }, [loadFilters]);

  useEffect(() => {
    loadPosts();
  }, [loadPosts]);

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

      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={influencerId}
          onChange={(e) => { setInfluencerId(e.target.value); setPage(0); }}
          className="px-3 py-2.5 rounded-xl text-sm outline-none border"
          style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)', borderColor: 'var(--color-border-default)' }}
        >
          <option value="">All influencers</option>
          {influencers.map((i) => (
            <option key={i.id} value={i.id}>@{i.handle}</option>
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
      </div>

      <div className="card p-5 flex flex-col gap-4">
        {loading ? (
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
                    <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Caption</th>
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
                    <th className="text-left py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-secondary)' }}>Reposts</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {posts.map((p) => (
                    <tr key={p.id} className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                      <td className="py-2.5 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-primary)' }}>@{p.handle}</td>
                      <td className="py-2.5 px-3 max-w-[320px] truncate" style={{ color: 'var(--color-text-secondary)' }} title={p.caption ?? undefined}>
                        {p.caption || '—'}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                        {format(new Date(p.posted_at), 'MMM d, yyyy')}
                      </td>
                      <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.likes?.toLocaleString() ?? '—'}</td>
                      <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.comments?.toLocaleString() ?? '—'}</td>
                      <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.views?.toLocaleString() ?? '—'}</td>
                      <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{p.reposts?.toLocaleString() ?? '—'}</td>
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
