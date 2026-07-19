import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PlayCircle, RefreshCw, Power, Trash2, History, ChevronDown, ChevronUp, Pencil, Check, X, Link2 } from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { getDashboardStatus } from '../services/dashboardService';
import { getCreators, renameCreator, deleteCreator } from '../services/creatorService';
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
import PlatformBadge from '../components/common/PlatformBadge';
import AccountTypeBadge from '../components/common/AccountTypeBadge';
import PlatformFilter from '../components/common/PlatformFilter';
import AccountTypeFilter from '../components/common/AccountTypeFilter';
import Button from '../components/common/Button';
import Input from '../components/common/Input';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import AddCategoryForm from '../components/influencers/AddCategoryForm';
import AddInfluencerForm from '../components/influencers/AddInfluencerForm';
import MassImportInfluencersForm from '../components/influencers/MassImportInfluencersForm';
import JobHistoryPanel from '../components/influencers/JobHistoryPanel';
import { useAppStore } from '../store/useAppStore';
import { formatHandle } from '../utils/platform';
import { groupByCreator } from '../utils/groupByCreator';

const IN_FLIGHT_STATUSES = new Set(['queued', 'running']);

export default function Influencers() {
  const enabledPlatforms = useAppStore((s) => s.enabledPlatforms);

  const [categories, setCategories] = useState([]);
  const [statusRows, setStatusRows] = useState([]);
  const [creators, setCreators] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(() => new Set());
  const [expandedHistory, setExpandedHistory] = useState(() => new Set());
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [categoryNameDraft, setCategoryNameDraft] = useState('');
  const [editingCreatorId, setEditingCreatorId] = useState(null);
  const [creatorNameDraft, setCreatorNameDraft] = useState('');
  const [editingInfluencerId, setEditingInfluencerId] = useState(null);
  const [influencerDraft, setInfluencerDraft] = useState({ handle: '', categoryId: '', scrapePostsSince: '', creatorName: '', accountType: 'individual' });
  const [savingEdit, setSavingEdit] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState(enabledPlatforms);
  const [selectedTypes, setSelectedTypes] = useState(['business', 'individual']);

  useEffect(() => {
    setSelectedPlatforms((prev) => prev.filter((p) => enabledPlatforms.includes(p)));
  }, [enabledPlatforms]);

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
      const [cats, rows, creatorList] = await Promise.all([getCategories(), getDashboardStatus(), getCreators()]);
      setCategories(cats);
      setStatusRows(rows);
      setCreators(creatorList);
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
    const rows = statusRows.filter(
      (r) => selectedPlatforms.includes(r.platform) && selectedTypes.includes(r.account_type),
    );
    const byCategory = new Map(categories.map((c) => [c.id, { category: c, influencers: [] }]));
    for (const row of rows) {
      if (!byCategory.has(row.category_id)) {
        byCategory.set(row.category_id, { category: { id: row.category_id, name: row.category_name }, influencers: [] });
      }
      byCategory.get(row.category_id).influencers.push(row);
    }
    return [...byCategory.values()].sort((a, b) => a.category.name.localeCompare(b.category.name));
  }, [categories, statusRows, selectedPlatforms, selectedTypes]);

  const filteredGrouped = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return grouped;
    return grouped
      .map(({ category, influencers }) => ({
        category,
        // A category-name match keeps every influencer in that category
        // (that's the whole point of searching "Beauty") rather than
        // filtering them down to rows whose handle/creator also happens
        // to contain the query.
        influencers: category.name.toLowerCase().includes(q)
          ? influencers
          : influencers.filter(
              (row) => row.handle.toLowerCase().includes(q) || row.creator_name?.toLowerCase().includes(q),
            ),
      }))
      .filter(({ influencers }) => influencers.length > 0);
  }, [grouped, search]);

  const handleScrapeNow = async (row) => {
    setTriggering((prev) => new Set(prev).add(row.influencer_id));
    try {
      await triggerScrape(row.influencer_id);
      toast.success(`Scrape queued for ${formatHandle(row.handle, row.platform)}`);
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

  const handleToggleCategoryActive = async (category, influencers) => {
    const activating = category.is_active === false;
    try {
      await updateCategory(category.id, { is_active: activating });
      // Deactivating pauses every currently-active influencer in the
      // category; reactivating resumes only the ones it paused (a
      // manually-paused influencer stays paused) -- see CategoryRepo.update.
      const affected = activating
        ? influencers.filter((i) => i.paused_by_category).length
        : influencers.filter((i) => i.is_active).length;
      toast.success(
        `"${category.name}" ${activating ? 'activated' : 'deactivated'}` +
          (affected > 0 ? ` -- ${affected} influencer${affected === 1 ? '' : 's'} ${activating ? 'resumed' : 'paused'}` : ''),
      );
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
      toast.success(`${formatHandle(row.handle, row.platform)} ${next ? 'activated' : 'deactivated'}`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleDeleteInfluencer = async (row) => {
    if (!window.confirm(`Permanently delete ${formatHandle(row.handle, row.platform)} -- including ALL its posts, comments, and metrics? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteInfluencer(row.influencer_id);
      toast.success(`${formatHandle(row.handle, row.platform)} deleted`);
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

  const startEditCreator = (creatorId, currentName) => {
    setEditingCreatorId(creatorId);
    setCreatorNameDraft(currentName);
  };

  const cancelEditCreator = () => {
    setEditingCreatorId(null);
    setCreatorNameDraft('');
  };

  const handleSaveCreator = async (creatorId, currentName) => {
    const name = creatorNameDraft.trim();
    if (!name || savingEdit) return;
    if (name === currentName) {
      cancelEditCreator();
      return;
    }
    setSavingEdit(true);
    try {
      await renameCreator(creatorId, name);
      toast.success(`Renamed to "${name}"`);
      cancelEditCreator();
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDeleteCreator = async (creatorId, name, influencerCount) => {
    if (!window.confirm(`Unlink "${name}"'s ${influencerCount} platform accounts from each other? Each account and all its scraped data stays untouched -- this only removes the cross-platform grouping.`)) {
      return;
    }
    try {
      await deleteCreator(creatorId);
      toast.success(`"${name}" unlinked`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const startEditInfluencer = (row) => {
    setEditingInfluencerId(row.influencer_id);
    setInfluencerDraft({
      handle: row.handle,
      categoryId: row.category_id,
      scrapePostsSince: row.scrape_posts_since || '',
      creatorName: row.creator_name || '',
      accountType: row.account_type,
    });
  };

  const cancelEditInfluencer = () => {
    setEditingInfluencerId(null);
    setInfluencerDraft({ handle: '', categoryId: '', scrapePostsSince: '', creatorName: '', accountType: 'individual' });
  };

  const handleSaveInfluencer = async (row) => {
    const cleanHandle = influencerDraft.handle.trim().replace(/^@/, '');
    if (!cleanHandle || !influencerDraft.categoryId || savingEdit) return;
    setSavingEdit(true);
    try {
      // row.handle is already "@name"-prefixed for YouTube rows (see
      // InfluencerRepo.normalize_handle) while cleanHandle above is always
      // bare -- compare against the bare form of the stored handle too, or
      // an unchanged YouTube handle would look "changed" on every save
      // (e.g. "name" !== "@name") and fire a needless update.
      const previousBareHandle = row.handle.replace(/^@/, '');
      const creatorChanged = influencerDraft.creatorName.trim() !== (row.creator_name || '');
      const typeChanged = influencerDraft.accountType !== row.account_type;
      const detailsChanged =
        cleanHandle !== previousBareHandle || influencerDraft.categoryId !== row.category_id || creatorChanged || typeChanged;
      const scrapeSinceChanged = influencerDraft.scrapePostsSince !== (row.scrape_posts_since || '');
      if (detailsChanged) {
        await updateInfluencerDetails(row.influencer_id, {
          handle: cleanHandle,
          categoryId: influencerDraft.categoryId,
          creatorName: creatorChanged ? influencerDraft.creatorName.trim() : undefined,
          accountType: typeChanged ? influencerDraft.accountType : undefined,
        });
      }
      if (scrapeSinceChanged) {
        await updateInfluencerScrapeSettings(row.influencer_id, influencerDraft.scrapePostsSince);
      }
      toast.success(`${formatHandle(cleanHandle, row.platform)} updated`);
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
      <div className="flex items-center justify-between flex-wrap gap-3">
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
        <AddInfluencerForm categories={categories} creators={creators} onCreated={load} />
        <div style={{ borderTop: '1px solid var(--color-border-subtle)' }} />
        <MassImportInfluencersForm onImported={load} />
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        {!loading && grouped.length > 0 && (
          <Input
            placeholder="Search by handle, creator, or category..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
        )}
        <div className="flex items-center gap-3 flex-wrap">
          <AccountTypeFilter value={selectedTypes} onChange={setSelectedTypes} />
          <PlatformFilter value={selectedPlatforms} onChange={setSelectedPlatforms} options={enabledPlatforms} />
        </div>
      </div>

      {loading ? (
        <div className="card p-5 h-64 animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
      ) : selectedPlatforms.length === 0 ? (
        <EmptyState title="No platform selected" message="Select at least one platform above to see influencers." />
      ) : selectedTypes.length === 0 ? (
        <EmptyState title="No type selected" message="Select Business and/or Individual above to see influencers." />
      ) : grouped.length === 0 ? (
        <EmptyState title="No categories yet" message="Add your first category above to get started." />
      ) : filteredGrouped.length === 0 ? (
        <EmptyState title="No matches" message={`No handle, creator, or category matches "${search}".`} />
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
                    <Link to={`/categories/${category.id}`} className="hover:underline">
                      {category.name}
                    </Link>{' '}
                    <span style={{ color: 'var(--color-text-muted)' }}>({influencers.length})</span>
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
                      onClick={() => handleToggleCategoryActive(category, influencers)}
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
                <div className="flex flex-col gap-2">
                  {groupByCreator(influencers).map((group) =>
                    group.creatorId ? (
                      <div
                        key={group.key}
                        className="rounded-xl p-3 flex flex-col gap-1"
                        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}
                      >
                        <div className="flex items-center gap-1.5 px-1 pb-1">
                          <Link2 className="w-3 h-3 shrink-0" style={{ color: 'var(--color-accent)' }} />
                          {editingCreatorId === group.rows[0].creator_id ? (
                            <div className="flex items-center gap-1.5 flex-1 min-w-0">
                              <Input
                                value={creatorNameDraft}
                                onChange={(e) => setCreatorNameDraft(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSaveCreator(group.rows[0].creator_id, group.creatorName)}
                                autoFocus
                                className="h-7 text-xs"
                              />
                              <Button variant="ghost" size="sm" title="Save" onClick={() => handleSaveCreator(group.rows[0].creator_id, group.creatorName)} loading={savingEdit}>
                                <Check className="w-3.5 h-3.5" style={{ color: 'var(--color-success)' }} />
                              </Button>
                              <Button variant="ghost" size="sm" title="Cancel" onClick={cancelEditCreator}>
                                <X className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          ) : (
                            <>
                              <Link
                                to={`/creators/${group.rows[0].creator_id}`}
                                className="text-xs font-semibold hover:underline"
                                style={{ color: 'var(--color-accent)' }}
                              >
                                {group.creatorName}
                              </Link>
                              <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                                — linked across {group.rows.length} platform{group.rows.length === 1 ? '' : 's'}
                              </span>
                              <div className="flex items-center gap-0.5 ml-auto">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  title="Rename creator"
                                  onClick={() => startEditCreator(group.rows[0].creator_id, group.creatorName)}
                                >
                                  <Pencil className="w-3 h-3" style={{ color: 'var(--color-text-muted)' }} />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  title="Unlink creator (keeps both accounts)"
                                  onClick={() => handleDeleteCreator(group.rows[0].creator_id, group.creatorName, group.rows.length)}
                                >
                                  <Trash2 className="w-3 h-3" style={{ color: 'var(--color-danger)' }} />
                                </Button>
                              </div>
                            </>
                          )}
                        </div>
                        <div className="flex flex-col divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
                          {group.rows.map((row) => (
                            <InfluencerRow
                              key={row.influencer_id}
                              row={row}
                              categories={categories}
                              creators={creators}
                              isEditing={editingInfluencerId === row.influencer_id}
                              draft={influencerDraft}
                              setDraft={setInfluencerDraft}
                              savingEdit={savingEdit}
                              onStartEdit={() => startEditInfluencer(row)}
                              onCancelEdit={cancelEditInfluencer}
                              onSave={() => handleSaveInfluencer(row)}
                              isInFlight={triggering.has(row.influencer_id) || IN_FLIGHT_STATUSES.has(row.last_job_status)}
                              triggeringThis={triggering.has(row.influencer_id)}
                              historyOpen={expandedHistory.has(row.influencer_id)}
                              onToggleHistory={() => toggleHistory(row.influencer_id)}
                              onScrapeNow={() => handleScrapeNow(row)}
                              onToggleActive={() => handleToggleInfluencerActive(row)}
                              onDelete={() => handleDeleteInfluencer(row)}
                            />
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div key={group.key} className="flex flex-col divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
                        <InfluencerRow
                          row={group.rows[0]}
                          categories={categories}
                          creators={creators}
                          isEditing={editingInfluencerId === group.rows[0].influencer_id}
                          draft={influencerDraft}
                          setDraft={setInfluencerDraft}
                          savingEdit={savingEdit}
                          onStartEdit={() => startEditInfluencer(group.rows[0])}
                          onCancelEdit={cancelEditInfluencer}
                          onSave={() => handleSaveInfluencer(group.rows[0])}
                          isInFlight={triggering.has(group.rows[0].influencer_id) || IN_FLIGHT_STATUSES.has(group.rows[0].last_job_status)}
                          triggeringThis={triggering.has(group.rows[0].influencer_id)}
                          historyOpen={expandedHistory.has(group.rows[0].influencer_id)}
                          onToggleHistory={() => toggleHistory(group.rows[0].influencer_id)}
                          onScrapeNow={() => handleScrapeNow(group.rows[0])}
                          onToggleActive={() => handleToggleInfluencerActive(group.rows[0])}
                          onDelete={() => handleDeleteInfluencer(group.rows[0])}
                        />
                      </div>
                    ),
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function InfluencerRow({
  row, categories, creators, isEditing, draft, setDraft, savingEdit,
  onStartEdit, onCancelEdit, onSave, isInFlight, triggeringThis,
  historyOpen, onToggleHistory, onScrapeNow, onToggleActive, onDelete,
}) {
  return (
    <div className="py-2.5">
      {isEditing ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-end gap-3 flex-wrap">
            <div className="min-w-[140px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Handle
              </label>
              <Input
                value={draft.handle}
                onChange={(e) => setDraft((d) => ({ ...d, handle: e.target.value }))}
              />
            </div>
            <div className="min-w-[160px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Category
              </label>
              <select
                value={draft.categoryId}
                onChange={(e) => setDraft((d) => ({ ...d, categoryId: e.target.value }))}
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
            <div className="min-w-[140px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Type
              </label>
              <select
                value={draft.accountType}
                onChange={(e) => setDraft((d) => ({ ...d, accountType: e.target.value }))}
                className="w-full px-3.5 py-2.5 rounded-xl text-sm outline-none border"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text-primary)',
                  borderColor: 'var(--color-border-default)',
                }}
              >
                <option value="individual">Individual</option>
                <option value="business">Business</option>
              </select>
            </div>
            <div className="min-w-[150px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Scrape posts since
              </label>
              <Input
                type="date"
                value={draft.scrapePostsSince}
                onChange={(e) => setDraft((d) => ({ ...d, scrapePostsSince: e.target.value }))}
              />
            </div>
            <div className="min-w-[160px] flex-1">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Creator <span style={{ color: 'var(--color-text-muted)' }}>(links platforms)</span>
              </label>
              <Input
                list="creator-name-options-edit"
                placeholder="unlinked"
                value={draft.creatorName}
                onChange={(e) => setDraft((d) => ({ ...d, creatorName: e.target.value }))}
              />
              <datalist id="creator-name-options-edit">
                {creators.map((c) => (
                  <option key={c.id} value={c.name} />
                ))}
              </datalist>
            </div>
            <Button size="sm" onClick={onSave} loading={savingEdit}>
              <Check className="w-3.5 h-3.5" />
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancelEdit}>
              <X className="w-3.5 h-3.5" />
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              to={`/influencers/${row.influencer_id}`}
              className="font-medium text-sm truncate hover:underline"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {formatHandle(row.handle, row.platform)}
            </Link>
            <PlatformBadge platform={row.platform} handle={row.handle} />
            <AccountTypeBadge accountType={row.account_type} />
            <StatusBadge status={row.last_job_status} />
            {!row.is_active && (
              <span
                className="text-xs"
                style={{ color: row.deactivation_reason === 'handle_not_found' ? 'var(--color-danger)' : 'var(--color-text-muted)' }}
                title={
                  row.deactivation_reason === 'handle_not_found'
                    ? "Auto-deactivated: this platform confirmed the handle doesn't exist. Edit the handle (pencil icon) to fix it, then reactivate."
                    : row.paused_by_category
                      ? 'Paused because its category is held -- reactivate the category to resume it, or use the power button to resume just this influencer.'
                      : undefined
                }
              >
                {row.deactivation_reason === 'handle_not_found'
                  ? '(handle not found -- recheck)'
                  : row.paused_by_category
                    ? '(held with category)'
                    : '(inactive)'}
              </span>
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
              onClick={onScrapeNow}
              loading={triggeringThis}
              disabled={isInFlight}
            >
              <PlayCircle className="w-3.5 h-3.5" />
              Scrape now
            </Button>
            <Button
              variant="ghost"
              size="sm"
              title={historyOpen ? 'Hide run history' : 'Show run history'}
              onClick={onToggleHistory}
            >
              {historyOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <History className="w-3.5 h-3.5" />}
            </Button>
            <Button variant="ghost" size="sm" title="Edit influencer" onClick={onStartEdit}>
              <Pencil className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              title={row.is_active ? 'Deactivate' : 'Activate'}
              onClick={onToggleActive}
            >
              <Power className="w-3.5 h-3.5" style={{ color: row.is_active ? 'var(--color-warning)' : 'var(--color-success)' }} />
            </Button>
            <Button variant="ghost" size="sm" title="Delete permanently" onClick={onDelete}>
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
}
