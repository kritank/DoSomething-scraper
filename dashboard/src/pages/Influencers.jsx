import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PlayCircle, RefreshCw, Power, Trash2, History, ChevronDown, ChevronUp, Pencil, Check, X } from 'lucide-react';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { getDashboardStatus } from '../services/dashboardService';
import {
  getCategories,
  triggerScrape,
  updateCategory,
  deleteCategory,
  updateInfluencerActive,
  updateInfluencerDetails,
  updateInfluencerScrapeSettings,
  deleteInfluencer,
} from '../services/influencerService';
import StatusBadge from '../components/common/StatusBadge';
import Button from '../components/common/Button';
import Input from '../components/common/Input';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import AddCategoryForm from '../components/influencers/AddCategoryForm';
import AddInfluencerForm from '../components/influencers/AddInfluencerForm';
import JobHistoryPanel from '../components/influencers/JobHistoryPanel';

const IN_FLIGHT_STATUSES = new Set(['queued', 'running']);

export default function Influencers() {
  const [categories, setCategories] = useState([]);
  const [statusRows, setStatusRows] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(() => new Set());
  const [expandedHistory, setExpandedHistory] = useState(() => new Set());
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [categoryNameDraft, setCategoryNameDraft] = useState('');
  const [editingInfluencerId, setEditingInfluencerId] = useState(null);
  const [influencerDraft, setInfluencerDraft] = useState({ handle: '', categoryId: '', scrapePostsSince: '' });
  const [savingEdit, setSavingEdit] = useState(false);
  const [search, setSearch] = useState('');

  const toggleHistory = (influencerId) => {
    setExpandedHistory((prev) => {
      const next = new Set(prev);
      next.has(influencerId) ? next.delete(influencerId) : next.add(influencerId);
      return next;
    });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cats, rows] = await Promise.all([getCategories(), getDashboardStatus()]);
      setCategories(cats);
      setStatusRows(rows);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const byCategory = new Map(categories.map((c) => [c.id, { category: c, influencers: [] }]));
    for (const row of statusRows) {
      if (!byCategory.has(row.category_id)) {
        byCategory.set(row.category_id, { category: { id: row.category_id, name: row.category_name }, influencers: [] });
      }
      byCategory.get(row.category_id).influencers.push(row);
    }
    return [...byCategory.values()].sort((a, b) => a.category.name.localeCompare(b.category.name));
  }, [categories, statusRows]);

  const filteredGrouped = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return grouped;
    return grouped
      .map(({ category, influencers }) => ({
        category,
        influencers: influencers.filter((row) => row.handle.toLowerCase().includes(q)),
      }))
      .filter(({ influencers }) => influencers.length > 0);
  }, [grouped, search]);

  const handleScrapeNow = async (row) => {
    setTriggering((prev) => new Set(prev).add(row.influencer_id));
    try {
      await triggerScrape(row.influencer_id);
      toast.success(`Scrape queued for @${row.handle}`);
      // Optimistic update -- avoids waiting on a full refetch to reflect
      // the click, since the actual job may sit behind others in the
      // single-account queue for a while.
      setStatusRows((rows) =>
        rows.map((r) => (r.influencer_id === row.influencer_id ? { ...r, last_job_status: 'queued' } : r)),
      );
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setTriggering((prev) => {
        const next = new Set(prev);
        next.delete(row.influencer_id);
        return next;
      });
    }
  };

  const handleToggleCategoryActive = async (category) => {
    try {
      await updateCategory(category.id, { is_active: !(category.is_active ?? true) });
      toast.success(`"${category.name}" ${category.is_active ? 'deactivated' : 'activated'}`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleDeleteCategory = async (category, influencerCount) => {
    const msg = influencerCount > 0
      ? `Permanently delete category "${category.name}" and its ${influencerCount} influencer(s) -- including ALL their posts, comments, and metrics? This cannot be undone.`
      : `Permanently delete category "${category.name}"? This cannot be undone.`;
    if (!window.confirm(msg)) return;
    try {
      await deleteCategory(category.id);
      toast.success(`"${category.name}" deleted`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleToggleInfluencerActive = async (row) => {
    const next = !row.is_active;
    try {
      await updateInfluencerActive(row.influencer_id, next);
      toast.success(`@${row.handle} ${next ? 'activated' : 'deactivated'}`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleDeleteInfluencer = async (row) => {
    if (!window.confirm(`Permanently delete @${row.handle} -- including ALL its posts, comments, and metrics? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteInfluencer(row.influencer_id);
      toast.success(`@${row.handle} deleted`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const startEditCategory = (category) => {
    setEditingCategoryId(category.id);
    setCategoryNameDraft(category.name);
  };

  const cancelEditCategory = () => {
    setEditingCategoryId(null);
    setCategoryNameDraft('');
  };

  const handleSaveCategory = async (category) => {
    const name = categoryNameDraft.trim();
    if (!name || savingEdit) return;
    if (name === category.name) {
      cancelEditCategory();
      return;
    }
    setSavingEdit(true);
    try {
      await updateCategory(category.id, { name });
      toast.success(`Renamed to "${name}"`);
      cancelEditCategory();
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSavingEdit(false);
    }
  };

  const startEditInfluencer = (row) => {
    setEditingInfluencerId(row.influencer_id);
    setInfluencerDraft({
      handle: row.handle,
      categoryId: row.category_id,
      scrapePostsSince: row.scrape_posts_since || '',
    });
  };

  const cancelEditInfluencer = () => {
    setEditingInfluencerId(null);
    setInfluencerDraft({ handle: '', categoryId: '', scrapePostsSince: '' });
  };

  const handleSaveInfluencer = async (row) => {
    const cleanHandle = influencerDraft.handle.trim().replace(/^@/, '');
    if (!cleanHandle || !influencerDraft.categoryId || savingEdit) return;
    setSavingEdit(true);
    try {
      const detailsChanged = cleanHandle !== row.handle || influencerDraft.categoryId !== row.category_id;
      const scrapeSinceChanged = influencerDraft.scrapePostsSince !== (row.scrape_posts_since || '');
      if (detailsChanged) {
        await updateInfluencerDetails(row.influencer_id, {
          handle: cleanHandle,
          categoryId: influencerDraft.categoryId,
        });
      }
      if (scrapeSinceChanged) {
        await updateInfluencerScrapeSettings(row.influencer_id, influencerDraft.scrapePostsSince);
      }
      toast.success(`@${cleanHandle} updated`);
      cancelEditInfluencer();
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSavingEdit(false);
    }
  };

  if (error) {
    return <ErrorState title="Couldn't load influencers" description={error} onRetry={load} />;
  }

  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Influencers</h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Add categories/influencers and trigger manual scrapes
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      <div className="card p-5 flex flex-col gap-5">
        <AddCategoryForm onCreated={load} />
        <div style={{ borderTop: '1px solid var(--color-border-subtle)' }} />
        <AddInfluencerForm categories={categories} onCreated={load} />
      </div>

      {!loading && grouped.length > 0 && (
        <Input
          placeholder="Search influencers by handle..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      )}

      {loading ? (
        <div className="card p-5 h-64 animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
      ) : grouped.length === 0 ? (
        <EmptyState title="No categories yet" message="Add your first category above to get started." />
      ) : filteredGrouped.length === 0 ? (
        <EmptyState title="No matches" message={`No influencer handles match "${search}".`} />
      ) : (
        <div className="flex flex-col gap-4">
          {filteredGrouped.map(({ category, influencers }) => (
            <div key={category.id} className="card p-5 flex flex-col gap-3 min-w-0">
              <div className="flex items-center justify-between gap-3">
                {editingCategoryId === category.id ? (
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Input
                      value={categoryNameDraft}
                      onChange={(e) => setCategoryNameDraft(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSaveCategory(category)}
                      autoFocus
                    />
                    <Button variant="ghost" size="sm" title="Save" onClick={() => handleSaveCategory(category)} loading={savingEdit}>
                      <Check className="w-3.5 h-3.5" style={{ color: 'var(--color-success)' }} />
                    </Button>
                    <Button variant="ghost" size="sm" title="Cancel" onClick={cancelEditCategory}>
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ) : (
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                    {category.name} <span style={{ color: 'var(--color-text-muted)' }}>({influencers.length})</span>
                    {category.is_active === false && (
                      <span className="ml-2 text-xs font-normal" style={{ color: 'var(--color-text-muted)' }}>(inactive)</span>
                    )}
                  </h3>
                )}
                {editingCategoryId !== category.id && (
                  <div className="flex items-center gap-1 shrink-0">
                    <Button variant="ghost" size="sm" title="Rename category" onClick={() => startEditCategory(category)}>
                      <Pencil className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      title={category.is_active === false ? 'Activate category' : 'Deactivate category'}
                      onClick={() => handleToggleCategoryActive(category)}
                    >
                      <Power className="w-3.5 h-3.5" style={{ color: category.is_active === false ? 'var(--color-success)' : 'var(--color-warning)' }} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Delete category permanently"
                      onClick={() => handleDeleteCategory(category, influencers.length)}
                    >
                      <Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--color-danger)' }} />
                    </Button>
                  </div>
                )}
              </div>

              {influencers.length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>No influencers in this category yet.</p>
              ) : (
                <div className="flex flex-col divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
                  {influencers.map((row) => {
                    const isInFlight = triggering.has(row.influencer_id) || IN_FLIGHT_STATUSES.has(row.last_job_status);
                    const historyOpen = expandedHistory.has(row.influencer_id);
                    const isEditing = editingInfluencerId === row.influencer_id;
                    return (
                      <div key={row.influencer_id} className="py-2.5">
                        {isEditing ? (
                          <div className="flex items-end gap-3 flex-wrap">
                            <div className="min-w-[140px]">
                              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                                Handle
                              </label>
                              <Input
                                value={influencerDraft.handle}
                                onChange={(e) => setInfluencerDraft((d) => ({ ...d, handle: e.target.value }))}
                              />
                            </div>
                            <div className="min-w-[160px]">
                              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                                Category
                              </label>
                              <select
                                value={influencerDraft.categoryId}
                                onChange={(e) => setInfluencerDraft((d) => ({ ...d, categoryId: e.target.value }))}
                                className="w-full px-3.5 py-2.5 rounded-xl text-sm outline-none border"
                                style={{
                                  background: 'var(--color-bg-secondary)',
                                  color: 'var(--color-text-primary)',
                                  borderColor: 'var(--color-border-default)',
                                }}
                              >
                                {categories.map((c) => (
                                  <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                              </select>
                            </div>
                            <div className="min-w-[150px]">
                              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                                Scrape posts since
                              </label>
                              <Input
                                type="date"
                                value={influencerDraft.scrapePostsSince}
                                onChange={(e) => setInfluencerDraft((d) => ({ ...d, scrapePostsSince: e.target.value }))}
                              />
                            </div>
                            <Button size="sm" onClick={() => handleSaveInfluencer(row)} loading={savingEdit}>
                              <Check className="w-3.5 h-3.5" />
                              Save
                            </Button>
                            <Button variant="ghost" size="sm" onClick={cancelEditInfluencer}>
                              <X className="w-3.5 h-3.5" />
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <div
                            className="flex items-center justify-between gap-3 flex-wrap"
                            style={{ borderColor: 'var(--color-border-subtle)' }}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <span className="font-medium text-sm truncate" style={{ color: 'var(--color-text-primary)' }}>
                                @{row.handle}
                              </span>
                              <StatusBadge status={row.last_job_status} />
                              {!row.is_active && (
                                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>(inactive)</span>
                              )}
                            </div>
                            <div className="flex items-center gap-4 shrink-0">
                              <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                                {row.last_job_finished_at
                                  ? `Last scraped ${format(new Date(row.last_job_finished_at), 'MMM d, HH:mm')}`
                                  : 'Never scraped'}
                              </span>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => handleScrapeNow(row)}
                                loading={triggering.has(row.influencer_id)}
                                disabled={isInFlight}
                              >
                                <PlayCircle className="w-3.5 h-3.5" />
                                Scrape now
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                title={historyOpen ? 'Hide run history' : 'Show run history'}
                                onClick={() => toggleHistory(row.influencer_id)}
                              >
                                {historyOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <History className="w-3.5 h-3.5" />}
                              </Button>
                              <Button variant="ghost" size="sm" title="Edit influencer" onClick={() => startEditInfluencer(row)}>
                                <Pencil className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                title={row.is_active ? 'Deactivate' : 'Activate'}
                                onClick={() => handleToggleInfluencerActive(row)}
                              >
                                <Power className="w-3.5 h-3.5" style={{ color: row.is_active ? 'var(--color-warning)' : 'var(--color-success)' }} />
                              </Button>
                              <Button variant="ghost" size="sm" title="Delete permanently" onClick={() => handleDeleteInfluencer(row)}>
                                <Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--color-danger)' }} />
                              </Button>
                            </div>
                          </div>
                        )}
                        {historyOpen && !isEditing && (
                          <div className="mt-2">
                            <JobHistoryPanel influencerId={row.influencer_id} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
