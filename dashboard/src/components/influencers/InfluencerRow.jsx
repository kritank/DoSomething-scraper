import React from 'react';
import { Link } from 'react-router-dom';
import { PlayCircle, Power, PowerOff, Trash2, History, ChevronUp, Pencil, Check, X, AlertTriangle } from 'lucide-react';
import { format } from 'date-fns';
import StatusBadge from '../common/StatusBadge';
import PlatformBadge from '../common/PlatformBadge';
import AccountTypeBadge from '../common/AccountTypeBadge';
import Button from '../common/Button';
import Input from '../common/Input';
import HeaderPill from '../common/HeaderPill';
import JobHistoryPanel from './JobHistoryPanel';
import { formatHandle } from '../../utils/platform';

// One influencer's row: view mode (handle, badges, last-scraped time, scrape
// now / history / edit / activate / delete actions) or inline edit mode.
// Shared between Influencers.jsx (the flat/grouped list) and
// CategoryProfile.jsx (per-category groups) -- same row, same actions,
// regardless of which page it's rendered from.
export default function InfluencerRow({
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
            <div className="min-w-[140px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Max comments/post <span style={{ color: 'var(--color-text-muted)' }}>(blank = default)</span>
              </label>
              <Input
                type="number"
                min="0"
                placeholder="platform default"
                value={draft.maxCommentsPerPost}
                onChange={(e) => setDraft((d) => ({ ...d, maxCommentsPerPost: e.target.value }))}
              />
            </div>
            <div className="min-w-[160px] flex-1">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Creator <span style={{ color: 'var(--color-text-muted)' }}>(links platforms)</span>
              </label>
              <Input
                list={`creator-name-options-edit-${row.influencer_id}`}
                placeholder="unlinked"
                value={draft.creatorName}
                onChange={(e) => setDraft((d) => ({ ...d, creatorName: e.target.value }))}
              />
              <datalist id={`creator-name-options-edit-${row.influencer_id}`}>
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
                title={
                  row.deactivation_reason === 'handle_not_found'
                    ? "Auto-deactivated: this platform confirmed the handle doesn't exist. Edit the handle (pencil icon) to fix it, then reactivate."
                    : row.paused_by_category
                      ? 'Paused because its category is held -- reactivate the category to resume it, or use the power button to resume just this influencer.'
                      : undefined
                }
              >
                <HeaderPill
                  icon={row.deactivation_reason === 'handle_not_found' ? AlertTriangle : PowerOff}
                  color={row.deactivation_reason === 'handle_not_found' ? 'var(--color-danger)' : undefined}
                >
                  {row.deactivation_reason === 'handle_not_found'
                    ? 'handle not found -- recheck'
                    : row.paused_by_category
                      ? 'held with category'
                      : 'inactive'}
                </HeaderPill>
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
