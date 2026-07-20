import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  RefreshCw, ChevronDown, ChevronUp, Power, Trash2,
  Users, ShieldCheck, AlertTriangle, Wifi, KeyRound, Gauge,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { getAccounts, updateAccountStatus, deleteAccount } from '../services/accountsService';
import { getYoutubeKeys, updateYoutubeKeyStatus, deleteYoutubeKey } from '../services/youtubeKeysService';
import {
  getInstagramGraphTokens,
  updateInstagramGraphTokenStatus,
  deleteInstagramGraphToken,
} from '../services/instagramGraphTokensService';
import StatusBadge from '../components/common/StatusBadge';
import PlatformIcon from '../components/common/PlatformIcon';
import KPICard from '../components/common/KPICard';
import Button from '../components/common/Button';
import Input from '../components/common/Input';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import AddAccountForm from '../components/accounts/AddAccountForm';
import InstagramBackendToggle from '../components/accounts/InstagramBackendToggle';
import AddYoutubeKeyForm from '../components/youtube/AddYoutubeKeyForm';
import AddInstagramGraphTokenForm from '../components/instagram/AddInstagramGraphTokenForm';
import { cn } from '../utils/cn';

const NEEDS_MANUAL_RESOLUTION = new Set(['checkpoint_required', 'login_failed']);
const NEEDS_ROTATION = new Set(['invalid']);

const PLATFORMS = [
  { id: 'instagram', label: 'Instagram', unitLabel: 'accounts' },
  { id: 'youtube', label: 'YouTube', unitLabel: 'API keys' },
];

function relative(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const isFuture = d > new Date();
  return `${isFuture ? 'in ' : ''}${formatDistanceToNow(d)}${isFuture ? '' : ' ago'}`;
}

export default function Accounts() {
  const [platform, setPlatform] = useState('instagram');
  const [accounts, setAccounts] = useState(null);
  const [keys, setKeys] = useState(null);
  const [tokens, setTokens] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addPanelOpen, setAddPanelOpen] = useState(false);
  const [tokenPanelOpen, setTokenPanelOpen] = useState(false);
  const [expandedRowId, setExpandedRowId] = useState(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [a, k, t] = await Promise.all([getAccounts(), getYoutubeKeys(), getInstagramGraphTokens()]);
      setAccounts(a);
      setKeys(k);
      setTokens(t);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const switchPlatform = (id) => {
    if (id === platform) return;
    setPlatform(id);
    setAddPanelOpen(false);
    setTokenPanelOpen(false);
    setExpandedRowId(null);
    setSearch('');
  };

  const igStats = useMemo(() => {
    if (!accounts) return null;
    return {
      total: accounts.length,
      active: accounts.filter((a) => a.status === 'active').length,
      needsAttention: accounts.filter((a) => NEEDS_MANUAL_RESOLUTION.has(a.status)).length,
      proxied: accounts.filter((a) => a.has_proxy).length,
    };
  }, [accounts]);

  const ytStats = useMemo(() => {
    if (!keys) return null;
    return {
      total: keys.length,
      active: keys.filter((k) => k.status === 'active').length,
      needsAttention: keys.filter((k) => NEEDS_ROTATION.has(k.status)).length,
      quotaUsedToday: keys.reduce((sum, k) => sum + k.quota_used_today, 0),
    };
  }, [keys]);

  const igTokenStats = useMemo(() => {
    if (!tokens) return null;
    return {
      total: tokens.length,
      active: tokens.filter((t) => t.status === 'active').length,
      needsAttention: tokens.filter((t) => ['invalid', 'disabled'].includes(t.status)).length,
    };
  }, [tokens]);

  const handleToggleAccountStatus = async (account) => {
    const next = account.status === 'disabled' ? 'active' : 'disabled';
    try {
      await updateAccountStatus(account.id, next);
      toast.success(`@${account.username} ${next === 'disabled' ? 'disabled' : 're-enabled'}`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleDeleteAccount = async (account) => {
    if (!window.confirm(`Permanently delete @${account.username}? This removes its stored session/credentials and cannot be undone.`)) {
      return;
    }
    try {
      await deleteAccount(account.id);
      toast.success(`@${account.username} deleted`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleToggleKeyStatus = async (key) => {
    const next = key.status === 'disabled' ? 'active' : 'disabled';
    try {
      await updateYoutubeKeyStatus(key.id, next);
      toast.success(`"${key.label}" ${next === 'disabled' ? 'disabled' : 're-enabled'}`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleDeleteKey = async (key) => {
    if (!window.confirm(`Permanently delete "${key.label}"? This removes its stored key and cannot be undone.`)) {
      return;
    }
    try {
      await deleteYoutubeKey(key.id);
      toast.success(`"${key.label}" deleted`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleToggleTokenStatus = async (token) => {
    const next = token.status === 'disabled' ? 'active' : 'disabled';
    try {
      await updateInstagramGraphTokenStatus(token.id, next);
      toast.success(`"${token.label}" ${next === 'disabled' ? 'disabled' : 're-enabled'}`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleDeleteToken = async (token) => {
    if (!window.confirm(`Permanently delete "${token.label}"? This removes its stored token and cannot be undone.`)) {
      return;
    }
    try {
      await deleteInstagramGraphToken(token.id);
      toast.success(`"${token.label}" deleted`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  if (error) {
    return <ErrorState title="Couldn't load accounts" description={error} onRetry={load} />;
  }

  const filteredAccounts = accounts
    ? accounts.filter((a) => a.username.toLowerCase().includes(search.trim().toLowerCase()))
    : accounts;
  const filteredKeys = keys
    ? keys.filter((k) => k.label.toLowerCase().includes(search.trim().toLowerCase()))
    : keys;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Accounts</h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Pool health for every scraping credential — why a scrape did or didn't run
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} loading={loading}>
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {PLATFORMS.map((p) => {
          const isActive = platform === p.id;
          const stats = p.id === 'instagram' ? igStats : ytStats;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => switchPlatform(p.id)}
              className={cn(
                'relative flex items-center gap-3 px-5 py-4 rounded-2xl text-left transition-all duration-200',
                !isActive && 'opacity-70 hover:opacity-100',
              )}
              style={{
                background: isActive ? 'var(--color-bg-card-hover)' : 'var(--color-bg-card)',
                border: '1px solid ' + (isActive ? 'var(--color-accent)' : 'var(--color-border-subtle)'),
                boxShadow: isActive ? 'var(--shadow-accent)' : 'var(--shadow-card)',
              }}
            >
              <PlatformIcon platform={p.id} className="w-10 h-10 rounded-xl shrink-0" />
              <div className="flex flex-col min-w-0">
                <span className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{p.label}</span>
                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  {stats == null ? 'Loading…' : `${stats.total} ${p.unitLabel}`}
                </span>
              </div>
              {stats?.needsAttention > 0 && (
                <span
                  className="ml-auto flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium shrink-0"
                  style={{ background: 'var(--color-danger-muted)', color: 'var(--color-danger)' }}
                  title={`${stats.needsAttention} need attention`}
                >
                  <AlertTriangle className="w-3 h-3" />
                  {stats.needsAttention}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {platform === 'instagram' && <InstagramBackendToggle />}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {platform === 'instagram' ? (
          <>
            <KPICard label="Total accounts" value={igStats?.total ?? '—'} icon={<Users className="w-4 h-4" />} loading={!igStats} />
            <KPICard label="Active" value={igStats?.active ?? '—'} icon={<ShieldCheck className="w-4 h-4" />} color="var(--color-success)" loading={!igStats} />
            <KPICard
              label="Needs attention"
              value={igStats?.needsAttention ?? '—'}
              icon={<AlertTriangle className="w-4 h-4" />}
              color={igStats?.needsAttention > 0 ? 'var(--color-danger)' : undefined}
              loading={!igStats}
            />
            <KPICard label="Proxied" value={igStats ? `${igStats.proxied} / ${igStats.total}` : '—'} icon={<Wifi className="w-4 h-4" />} loading={!igStats} />
          </>
        ) : (
          <>
            <KPICard label="Total keys" value={ytStats?.total ?? '—'} icon={<KeyRound className="w-4 h-4" />} loading={!ytStats} />
            <KPICard label="Active" value={ytStats?.active ?? '—'} icon={<ShieldCheck className="w-4 h-4" />} color="var(--color-success)" loading={!ytStats} />
            <KPICard
              label="Needs attention"
              value={ytStats?.needsAttention ?? '—'}
              icon={<AlertTriangle className="w-4 h-4" />}
              color={ytStats?.needsAttention > 0 ? 'var(--color-danger)' : undefined}
              loading={!ytStats}
            />
            <KPICard label="Quota used today" value={ytStats ? ytStats.quotaUsedToday.toLocaleString() : '—'} icon={<Gauge className="w-4 h-4" />} loading={!ytStats} />
          </>
        )}
      </div>

      {platform === 'instagram' && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KPICard label="Graph tokens" value={igTokenStats?.total ?? '—'} icon={<KeyRound className="w-4 h-4" />} loading={!igTokenStats} />
          <KPICard label="Active tokens" value={igTokenStats?.active ?? '—'} icon={<ShieldCheck className="w-4 h-4" />} color="var(--color-success)" loading={!igTokenStats} />
          <KPICard
            label="Needs attention"
            value={igTokenStats?.needsAttention ?? '—'}
            icon={<AlertTriangle className="w-4 h-4" />}
            color={igTokenStats?.needsAttention > 0 ? 'var(--color-danger)' : undefined}
            loading={!igTokenStats}
          />
        </div>
      )}

      <div className="flex items-center justify-between gap-3 flex-wrap">
        {!loading && (platform === 'instagram' ? accounts?.length : keys?.length) > 0 && (
          <Input
            placeholder={platform === 'instagram' ? 'Search accounts by username...' : 'Search keys by label...'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
        )}
        <Button variant="secondary" size="sm" onClick={() => setAddPanelOpen((o) => !o)} className="ml-auto">
          {addPanelOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          {platform === 'instagram' ? 'Add account' : 'Add key'}
        </Button>
      </div>

      {addPanelOpen && (
        <div className="card p-5 animate-fade-in">
          {platform === 'instagram' ? (
            <AddAccountForm onRegistered={() => { setAddPanelOpen(false); load(); }} />
          ) : (
            <AddYoutubeKeyForm onRegistered={() => { setAddPanelOpen(false); load(); }} />
          )}
        </div>
      )}

      <div className="card p-5 animate-fade-in" key={platform}>
        {platform === 'instagram' ? (
          loading ? (
            <div className="h-48 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
          ) : accounts.length === 0 ? (
            <EmptyState
              title="No Instagram accounts registered"
              message="Register one via scripts/register_instagram_account.py, or add one above, before scraping Instagram influencers."
            />
          ) : filteredAccounts.length === 0 ? (
            <EmptyState title="No matches" message={`No account usernames match "${search}".`} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    {['Username', 'Status', 'Method', 'Proxy', 'Failures', 'Cooldown until', 'Last used', 'Last success', 'Last failure', 'Note', 'Actions'].map((h) => (
                      <th key={h} className="text-left py-2.5 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredAccounts.map((a) => {
                    const refreshOpen = expandedRowId === a.id;
                    return (
                      <React.Fragment key={a.id}>
                        <tr className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: refreshOpen ? 'none' : '1px solid var(--color-border-subtle)' }}>
                          <td className="py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-primary)' }}>@{a.username}</td>
                          <td className="py-2.5 px-3"><StatusBadge status={a.status} /></td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{a.auth_method}</td>
                          <td className="py-2.5 px-3" style={{ color: a.has_proxy ? 'var(--color-success)' : 'var(--color-warning)' }}
                              title={a.has_proxy ? 'Egress pinned to a proxy' : 'No proxy — scraping from the host IP risks Instagram checkpoints'}>
                            {a.has_proxy ? 'proxied' : 'direct'}
                          </td>
                          <td className="py-2.5 px-3" style={{ color: a.failure_count > 0 ? 'var(--color-warning)' : 'var(--color-text-secondary)' }}>
                            {a.failure_count}
                          </td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(a.cooldown_until)}</td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(a.last_used_at)}</td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(a.last_success_at)}</td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(a.last_failure_at)}</td>
                          <td className="py-2.5 px-3 text-xs max-w-[220px]" style={{ color: 'var(--color-text-muted)' }} title={a.error_message ?? undefined}>
                            <div className="truncate">{a.error_message ?? '—'}</div>
                            {NEEDS_MANUAL_RESOLUTION.has(a.status) && (
                              <div className="mt-0.5" style={{ color: 'var(--color-warning)' }}>
                                Needs manual resolution over SSH
                              </div>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                title="Refresh cookies (fix an expired session / checkpoint_required)"
                                onClick={() => setExpandedRowId(refreshOpen ? null : a.id)}
                              >
                                <RefreshCw className="w-3.5 h-3.5" style={{ color: refreshOpen ? 'var(--color-accent)' : 'var(--color-text-muted)' }} />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                title={a.status === 'disabled' ? 'Re-enable' : 'Disable'}
                                onClick={() => handleToggleAccountStatus(a)}
                              >
                                <Power className="w-3.5 h-3.5" style={{ color: a.status === 'disabled' ? 'var(--color-success)' : 'var(--color-warning)' }} />
                              </Button>
                              <Button variant="ghost" size="sm" title="Delete permanently" onClick={() => handleDeleteAccount(a)}>
                                <Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--color-danger)' }} />
                              </Button>
                            </div>
                          </td>
                        </tr>
                        {refreshOpen && (
                          <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                            <td colSpan={11} className="px-3 pb-4">
                              <div className="card p-4" style={{ background: 'var(--color-bg-secondary)' }}>
                                <AddAccountForm
                                  initialUsername={a.username}
                                  lockUsername
                                  onRegistered={() => { setExpandedRowId(null); load(); }}
                                />
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        ) : (
          loading ? (
            <div className="h-48 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
          ) : keys.length === 0 ? (
            <EmptyState
              title="No YouTube API keys registered"
              message="Register one via scripts/register_youtube_api_key.py, or add one above, before scraping YouTube influencers."
            />
          ) : filteredKeys.length === 0 ? (
            <EmptyState title="No matches" message={`No key labels match "${search}".`} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    {['Label', 'Status', 'Quota used today', 'Quota resets', 'Failures', 'Last used', 'Last success', 'Last failure', 'Note', 'Actions'].map((h) => (
                      <th key={h} className="text-left py-2.5 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredKeys.map((k) => {
                    const rotateOpen = expandedRowId === k.id;
                    return (
                      <React.Fragment key={k.id}>
                        <tr className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: rotateOpen ? 'none' : '1px solid var(--color-border-subtle)' }}>
                          <td className="py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-primary)' }}>{k.label}</td>
                          <td className="py-2.5 px-3"><StatusBadge status={k.status} /></td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                            {k.quota_used_today.toLocaleString()} / 10,000 units
                          </td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(k.quota_reset_at)}</td>
                          <td className="py-2.5 px-3" style={{ color: k.failure_count > 0 ? 'var(--color-warning)' : 'var(--color-text-secondary)' }}>
                            {k.failure_count}
                          </td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(k.last_used_at)}</td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(k.last_success_at)}</td>
                          <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(k.last_failure_at)}</td>
                          <td className="py-2.5 px-3 text-xs max-w-[220px]" style={{ color: 'var(--color-text-muted)' }} title={k.error_message ?? undefined}>
                            <div className="truncate">{k.error_message ?? '—'}</div>
                            {NEEDS_ROTATION.has(k.status) && (
                              <div className="mt-0.5" style={{ color: 'var(--color-danger)' }}>
                                Rotate this key -- Google rejected it
                              </div>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                title="Rotate key (replace an expired/invalid one)"
                                onClick={() => setExpandedRowId(rotateOpen ? null : k.id)}
                              >
                                <RefreshCw className="w-3.5 h-3.5" style={{ color: rotateOpen ? 'var(--color-accent)' : 'var(--color-text-muted)' }} />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                title={k.status === 'disabled' ? 'Re-enable' : 'Disable'}
                                onClick={() => handleToggleKeyStatus(k)}
                              >
                                <Power className="w-3.5 h-3.5" style={{ color: k.status === 'disabled' ? 'var(--color-success)' : 'var(--color-warning)' }} />
                              </Button>
                              <Button variant="ghost" size="sm" title="Delete permanently" onClick={() => handleDeleteKey(k)}>
                                <Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--color-danger)' }} />
                              </Button>
                            </div>
                          </td>
                        </tr>
                        {rotateOpen && (
                          <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                            <td colSpan={10} className="px-3 pb-4">
                              <div className="card p-4" style={{ background: 'var(--color-bg-secondary)' }}>
                                <AddYoutubeKeyForm
                                  initialLabel={k.label}
                                  lockLabel
                                  onRegistered={() => { setExpandedRowId(null); load(); }}
                                />
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {platform === 'instagram' && (
        <div className="card p-5 animate-fade-in">
          <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
            <div>
              <h3 className="text-base font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                Instagram Graph API tokens
              </h3>
              <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                Add the Meta tokens the hybrid scraper can fall back to when the session pool is exhausted.
              </p>
            </div>
            <Button variant="secondary" size="sm" onClick={() => setTokenPanelOpen((o) => !o)}>
              {tokenPanelOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              Add token
            </Button>
          </div>

          {tokenPanelOpen && (
            <div className="mt-4 card p-4" style={{ background: 'var(--color-bg-secondary)' }}>
              <AddInstagramGraphTokenForm onRegistered={() => { setTokenPanelOpen(false); load(); }} />
            </div>
          )}
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                  {['Label', 'Status', 'Cooldown', 'Failures', 'Last success', 'Last failure', 'Note', 'Actions'].map((h) => (
                    <th key={h} className="text-left py-2.5 px-3 font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(tokens ?? []).map((token) => (
                  <tr key={token.id} className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td className="py-2.5 px-3 font-medium" style={{ color: 'var(--color-text-primary)' }}>{token.label}</td>
                    <td className="py-2.5 px-3"><StatusBadge status={token.status} /></td>
                    <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(token.cooldown_until)}</td>
                    <td className="py-2.5 px-3" style={{ color: token.failure_count > 0 ? 'var(--color-warning)' : 'var(--color-text-secondary)' }}>
                      {token.failure_count}
                    </td>
                    <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(token.last_success_at)}</td>
                    <td className="py-2.5 px-3" style={{ color: 'var(--color-text-secondary)' }}>{relative(token.last_failure_at)}</td>
                    <td className="py-2.5 px-3 text-xs max-w-[220px]" style={{ color: 'var(--color-text-muted)' }} title={token.error_message ?? undefined}>
                      <div className="truncate">{token.error_message ?? '—'}</div>
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          title={token.status === 'disabled' ? 'Re-enable' : 'Disable'}
                          onClick={() => handleToggleTokenStatus(token)}
                        >
                          <Power className="w-3.5 h-3.5" style={{ color: token.status === 'disabled' ? 'var(--color-success)' : 'var(--color-warning)' }} />
                        </Button>
                        <Button variant="ghost" size="sm" title="Delete permanently" onClick={() => handleDeleteToken(token)}>
                          <Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--color-danger)' }} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
