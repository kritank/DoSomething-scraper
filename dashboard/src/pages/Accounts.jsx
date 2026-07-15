import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp, Power, Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { getAccounts, updateAccountStatus, deleteAccount } from '../services/accountsService';
import StatusBadge from '../components/common/StatusBadge';
import Button from '../components/common/Button';
import Input from '../components/common/Input';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import AddAccountForm from '../components/accounts/AddAccountForm';

const NEEDS_MANUAL_RESOLUTION = new Set(['checkpoint_required', 'login_failed']);

function relative(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  const isFuture = d > new Date();
  return `${isFuture ? 'in ' : ''}${formatDistanceToNow(d)}${isFuture ? '' : ' ago'}`;
}

export default function Accounts() {
  const [accounts, setAccounts] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [addPanelOpen, setAddPanelOpen] = useState(false);
  const [refreshingAccountId, setRefreshingAccountId] = useState(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setAccounts(await getAccounts());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleToggleStatus = async (account) => {
    const next = account.status === 'disabled' ? 'active' : 'disabled';
    try {
      await updateAccountStatus(account.id, next);
      toast.success(`@${account.username} ${next === 'disabled' ? 'disabled' : 're-enabled'}`);
      load();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    }
  };

  const handleDelete = async (account) => {
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

  if (error) {
    return <ErrorState title="Couldn't load accounts" description={error} onRetry={load} />;
  }

  const filteredAccounts = accounts
    ? accounts.filter((a) => a.username.toLowerCase().includes(search.trim().toLowerCase()))
    : accounts;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Instagram Accounts</h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Pool health — why a scrape did or didn't run
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => setAddPanelOpen((o) => !o)}>
            {addPanelOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            Add account
          </Button>
          <Button variant="secondary" size="sm" onClick={load} loading={loading}>
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {addPanelOpen && (
        <div className="card p-5">
          <AddAccountForm onRegistered={() => { setAddPanelOpen(false); load(); }} />
        </div>
      )}

      {!loading && accounts?.length > 0 && (
        <Input
          placeholder="Search accounts by username..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      )}

      <div className="card p-5">
        {loading ? (
          <div className="h-48 rounded-lg animate-shimmer" style={{ background: 'var(--color-bg-card-hover)' }} />
        ) : accounts.length === 0 ? (
          <EmptyState
            title="No accounts registered"
            message="Register one via scripts/register_instagram_account.py before scraping."
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
                  const refreshOpen = refreshingAccountId === a.id;
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
                          onClick={() => setRefreshingAccountId(refreshOpen ? null : a.id)}
                        >
                          <RefreshCw className="w-3.5 h-3.5" style={{ color: refreshOpen ? 'var(--color-accent)' : 'var(--color-text-muted)' }} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          title={a.status === 'disabled' ? 'Re-enable' : 'Disable'}
                          onClick={() => handleToggleStatus(a)}
                        >
                          <Power className="w-3.5 h-3.5" style={{ color: a.status === 'disabled' ? 'var(--color-success)' : 'var(--color-warning)' }} />
                        </Button>
                        <Button variant="ghost" size="sm" title="Delete permanently" onClick={() => handleDelete(a)}>
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
                            onRegistered={() => { setRefreshingAccountId(null); load(); }}
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
        )}
      </div>
    </div>
  );
}
