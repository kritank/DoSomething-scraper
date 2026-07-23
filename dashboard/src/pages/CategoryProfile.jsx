import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ChevronDown, ChevronUp, RefreshCw, Link2, Briefcase, User, Users, PowerOff } from 'lucide-react';
import { toast } from 'sonner';
import {
  getCategories,
  triggerScrape,
  refreshVerified,
  updateInfluencerActive,
  updateInfluencerDetails,
  updateInfluencerScrapeSettings,
  deleteInfluencer,
} from '../services/influencerService';
import { getDashboardStatus } from '../services/dashboardService';
import { getCreators } from '../services/creatorService';
import Button from '../components/common/Button';
import HeaderPill from '../components/common/HeaderPill';
import EmptyState from '../components/common/EmptyState';
import ErrorState from '../components/common/ErrorState';
import Skeleton from '../components/common/Skeleton';
import InfluencerRow from '../components/influencers/InfluencerRow';
import { formatHandle } from '../utils/platform';
import { groupByCreator } from '../utils/groupByCreator';

const TYPE_SECTIONS = [
  { key: 'business', label: 'Business', icon: Briefcase },
  { key: 'individual', label: 'Individual', icon: User },
];

const EMPTY_DRAFT = { handle: '', categoryId: '', scrapePostsSince: '', maxCommentsPerPost: '', creatorName: '', accountType: 'individual' };

export default function CategoryProfile() {
  const { categoryId } = useParams();

  const [category, setCategory] = useState(null);
  const [allCategories, setAllCategories] = useState([]);
  const [creators, setCreators] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(null);
  // Presence means expanded -- both default empty so every type-section
  // and creator group starts collapsed, same convention as Influencers.jsx.
  const [expandedSections, setExpandedSections] = useState(() => new Set());
  const [expandedGroups, setExpandedGroups] = useState(() => new Set());

  // Same row-level interaction state as Influencers.jsx -- InfluencerRow
  // is the identical shared component, so it needs the identical props.
  const [triggering, setTriggering] = useState(() => new Set());
  const [verifying, setVerifying] = useState(() => new Set());
  const [expandedHistory, setExpandedHistory] = useState(() => new Set());
  const [editingInfluencerId, setEditingInfluencerId] = useState(null);
  const [influencerDraft, setInfluencerDraft] = useState(EMPTY_DRAFT);
  const [savingEdit, setSavingEdit] = useState(false);

  const toggleSectionExpanded = (key) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const toggleGroupExpanded = (key) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

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
    setNotFound(false);
    try {
      const [categories, status, creatorList] = await Promise.all([getCategories(), getDashboardStatus(), getCreators()]);
      const found = categories.find((c) => c.id === categoryId);
      if (!found) {
        setNotFound(true);
        return;
      }
      setCategory(found);
      setAllCategories(categories);
      setCreators(creatorList);
      setRows(status.filter((r) => r.category_id === categoryId));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [categoryId]);

  useEffect(() => {
    load();
  }, [load]);

  const byType = useMemo(() => {
    const grouped = { business: [], individual: [] };
    for (const row of rows) {
      (grouped[row.account_type] ?? grouped.individual).push(row);
    }
    return grouped;
  }, [rows]);

  const handleScrapeNow = async (row) => {
    setTriggering((prev) => new Set(prev).add(row.influencer_id));
    try {
      await triggerScrape(row.influencer_id);
      toast.success(`Scrape queued for ${formatHandle(row.handle, row.platform)}`);
      setRows((prev) =>
        prev.map((r) => (r.influencer_id === row.influencer_id ? { ...r, last_job_status: 'queued' } : r)),
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

  const handleRefreshVerified = async (row) => {
    setVerifying((prev) => new Set(prev).add(row.influencer_id));
    try {
      await refreshVerified(row.influencer_id);
      toast.success(`Verified-badge refresh queued for ${formatHandle(row.handle, row.platform)}`);
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setVerifying((prev) => {
        const next = new Set(prev);
        next.delete(row.influencer_id);
        return next;
      });
    }
  };

  const startEditInfluencer = (row) => {
    setEditingInfluencerId(row.influencer_id);
    setInfluencerDraft({
      handle: row.handle,
      categoryId: row.category_id,
      scrapePostsSince: row.scrape_posts_since || '',
      maxCommentsPerPost: row.max_comments_per_post ?? '',
      creatorName: row.creator_name || '',
      accountType: row.account_type,
    });
  };

  const cancelEditInfluencer = () => {
    setEditingInfluencerId(null);
    setInfluencerDraft(EMPTY_DRAFT);
  };

  const handleSaveInfluencer = async (row) => {
    const cleanHandle = influencerDraft.handle.trim().replace(/^@/, '');
    if (!cleanHandle || !influencerDraft.categoryId || savingEdit) return;
    setSavingEdit(true);
    try {
      const previousBareHandle = row.handle.replace(/^@/, '');
      const creatorChanged = influencerDraft.creatorName.trim() !== (row.creator_name || '');
      const typeChanged = influencerDraft.accountType !== row.account_type;
      const detailsChanged =
        cleanHandle !== previousBareHandle || influencerDraft.categoryId !== row.category_id || creatorChanged || typeChanged;
      const scrapeSinceChanged = influencerDraft.scrapePostsSince !== (row.scrape_posts_since || '');
      const maxCommentsChanged =
        String(influencerDraft.maxCommentsPerPost) !== String(row.max_comments_per_post ?? '');
      if (detailsChanged) {
        await updateInfluencerDetails(row.influencer_id, {
          handle: cleanHandle,
          categoryId: influencerDraft.categoryId,
          creatorName: creatorChanged ? influencerDraft.creatorName.trim() : undefined,
          accountType: typeChanged ? influencerDraft.accountType : undefined,
        });
      }
      if (scrapeSinceChanged || maxCommentsChanged) {
        await updateInfluencerScrapeSettings(row.influencer_id, {
          scrapePostsSince: scrapeSinceChanged ? influencerDraft.scrapePostsSince : undefined,
          maxCommentsPerPost: maxCommentsChanged ? influencerDraft.maxCommentsPerPost : undefined,
        });
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

  if (notFound) {
    return <EmptyState title="Category not found" message="This category may have been deleted." />;
  }
  if (error) {
    return <ErrorState title="Couldn't load category" description={error} onRetry={load} />;
  }

  const rowProps = {
    categories: allCategories,
    creators,
    savingEdit,
    onSave: handleSaveInfluencer,
    onCancelEdit: cancelEditInfluencer,
    onToggleActive: handleToggleInfluencerActive,
    onDelete: handleDeleteInfluencer,
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
          <div className="min-w-0">
            <h2 className="text-xl font-semibold truncate" style={{ color: 'var(--color-text-primary)' }}>
              {loading ? 'Loading…' : category?.name}
            </h2>
            {!loading && category && (
              <div className="flex items-center flex-wrap gap-1.5 mt-1.5">
                <HeaderPill icon={Users}>{rows.length} account{rows.length === 1 ? '' : 's'}</HeaderPill>
                <HeaderPill icon={Briefcase}>{byType.business.length} business</HeaderPill>
                <HeaderPill icon={User}>{byType.individual.length} individual</HeaderPill>
                {category.is_active === false && (
                  <HeaderPill icon={PowerOff}>inactive</HeaderPill>
                )}
              </div>
            )}
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState title="No accounts yet" message="This category has no scraped accounts." />
      ) : (
        <div className="flex flex-col gap-6">
          {TYPE_SECTIONS.map(({ key, label, icon: Icon }) => (
            <div key={key} className="card p-5 flex flex-col gap-3 min-w-0">
              <button
                onClick={() => toggleSectionExpanded(key)}
                className="flex items-center gap-1.5 text-left"
              >
                <Icon className="w-4 h-4" style={{ color: 'var(--color-text-muted)' }} />
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                  {label} <span style={{ color: 'var(--color-text-muted)' }}>({byType[key].length})</span>
                </h3>
                {expandedSections.has(key) ? (
                  <ChevronUp className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5" style={{ color: 'var(--color-text-muted)' }} />
                )}
              </button>
              {byType[key].length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>None in this category.</p>
              ) : !expandedSections.has(key) ? null : (
                <div className="flex flex-col gap-2">
                  {groupByCreator(byType[key]).map((group) => (
                    <CategoryAccountGroup
                      key={group.key}
                      group={group}
                      expanded={expandedGroups.has(group.key)}
                      onToggleExpanded={() => toggleGroupExpanded(group.key)}
                      rowProps={rowProps}
                      editingInfluencerId={editingInfluencerId}
                      influencerDraft={influencerDraft}
                      setInfluencerDraft={setInfluencerDraft}
                      onStartEdit={startEditInfluencer}
                      triggering={triggering}
                      onScrapeNow={handleScrapeNow}
                      verifying={verifying}
                      onRefreshVerified={handleRefreshVerified}
                      expandedHistory={expandedHistory}
                      onToggleHistory={toggleHistory}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryAccountGroup({
  group, expanded, onToggleExpanded, rowProps, editingInfluencerId, influencerDraft, setInfluencerDraft,
  onStartEdit, triggering, onScrapeNow, verifying, onRefreshVerified, expandedHistory, onToggleHistory,
}) {
  // Solo (unlinked) groups are a single row with no header of their own --
  // nothing to collapse, so they always render their row directly.
  const collapsible = Boolean(group.creatorId);
  return (
    <div
      className="rounded-xl p-3 flex flex-col gap-1.5"
      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}
    >
      {group.creatorId && (
        <button onClick={onToggleExpanded} className="flex items-center gap-1.5 px-1 text-left">
          <Link2 className="w-3 h-3 shrink-0" style={{ color: 'var(--color-accent)' }} />
          <Link
            to={`/creators/${group.creatorId}`}
            onClick={(e) => e.stopPropagation()}
            className="text-xs font-semibold hover:underline"
            style={{ color: 'var(--color-accent)' }}
          >
            {group.creatorName}
          </Link>
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            — linked across {group.rows.length} platform{group.rows.length === 1 ? '' : 's'}
          </span>
          {expanded ? (
            <ChevronUp className="w-3 h-3 ml-auto" style={{ color: 'var(--color-text-muted)' }} />
          ) : (
            <ChevronDown className="w-3 h-3 ml-auto" style={{ color: 'var(--color-text-muted)' }} />
          )}
        </button>
      )}
      {(!collapsible || expanded) && (
        <div className="flex flex-col divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
          {group.rows.map((row) => (
            <InfluencerRow
              key={row.influencer_id}
              row={row}
              {...rowProps}
              isEditing={editingInfluencerId === row.influencer_id}
              draft={influencerDraft}
              setDraft={setInfluencerDraft}
              onStartEdit={() => onStartEdit(row)}
              isInFlight={triggering.has(row.influencer_id)}
              triggeringThis={triggering.has(row.influencer_id)}
              onScrapeNow={() => onScrapeNow(row)}
              verifyingThis={verifying.has(row.influencer_id)}
              onRefreshVerified={() => onRefreshVerified(row)}
              historyOpen={expandedHistory.has(row.influencer_id)}
              onToggleHistory={() => onToggleHistory(row.influencer_id)}
              onSave={() => rowProps.onSave(row)}
              onToggleActive={() => rowProps.onToggleActive(row)}
              onDelete={() => rowProps.onDelete(row)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
