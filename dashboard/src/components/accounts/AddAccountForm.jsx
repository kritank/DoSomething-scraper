import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import Input from '../common/Input';
import Button from '../common/Button';
import { cn } from '../../utils/cn';
import { registerAccountViaCookies, registerAccountViaLogin } from '../../services/accountsService';

const METHODS = [
  { id: 'cookies', label: 'Session cookies' },
  { id: 'login', label: 'Username / password' },
];

export default function AddAccountForm({ onRegistered, initialUsername, lockUsername = false }) {
  const [method, setMethod] = useState('cookies');
  const [submitting, setSubmitting] = useState(false);

  const [username, setUsername] = useState(initialUsername ?? '');
  const [sessionid, setSessionid] = useState('');
  const [csrftoken, setCsrftoken] = useState('');
  const [dsUserId, setDsUserId] = useState('');
  const [igDid, setIgDid] = useState('');
  const [password, setPassword] = useState('');
  const [proxy, setProxy] = useState('');

  const reset = () => {
    setUsername(''); setSessionid(''); setCsrftoken(''); setDsUserId(''); setIgDid(''); setPassword(''); setProxy('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    const cleanUsername = username.trim().replace(/^@/, '');
    if (!cleanUsername) return;

    setSubmitting(true);
    try {
      const cleanProxy = proxy.trim() || undefined;
      if (method === 'cookies') {
        if (!sessionid.trim() || !csrftoken.trim() || !dsUserId.trim()) return;
        await registerAccountViaCookies({
          username: cleanUsername,
          sessionid: sessionid.trim(),
          csrftoken: csrftoken.trim(),
          ds_user_id: dsUserId.trim(),
          ig_did: igDid.trim() || undefined,
          proxy: cleanProxy,
        });
        toast.success(lockUsername ? `@${cleanUsername} cookies refreshed` : `@${cleanUsername} added and active`);
      } else {
        if (!password) return;
        await registerAccountViaLogin({ username: cleanUsername, password, proxy: cleanProxy });
        toast.success(
          lockUsername
            ? `@${cleanUsername} refresh queued -- processing in the background`
            : `@${cleanUsername} queued -- processing in the background (checkpoint_required means it needs manual 2FA resolution over SSH)`,
        );
      }
      reset();
      onRegistered();
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = username.trim() && (
    method === 'cookies'
      ? sessionid.trim() && csrftoken.trim() && dsUserId.trim()
      : password
  );

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex gap-2">
        {METHODS.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMethod(m.id)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              method === m.id ? 'text-white' : '',
            )}
            style={{
              background: method === m.id ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
              color: method === m.id ? 'white' : 'var(--color-text-secondary)',
              border: '1px solid ' + (method === m.id ? 'var(--color-accent)' : 'var(--color-border-default)'),
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="flex items-end gap-3 flex-wrap">
        <div className="min-w-[160px]">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Instagram username
          </label>
          <Input
            placeholder="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={lockUsername}
          />
        </div>

        {method === 'cookies' ? (
          <>
            <div className="min-w-[220px] flex-1">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>sessionid</label>
              <Input type="password" value={sessionid} onChange={(e) => setSessionid(e.target.value)} />
            </div>
            <div className="min-w-[180px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>csrftoken</label>
              <Input type="password" value={csrftoken} onChange={(e) => setCsrftoken(e.target.value)} />
            </div>
            <div className="min-w-[160px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>ds_user_id</label>
              <Input type="password" value={dsUserId} onChange={(e) => setDsUserId(e.target.value)} />
            </div>
            <div className="min-w-[140px]">
              <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                ig_did <span style={{ color: 'var(--color-text-muted)' }}>(optional)</span>
              </label>
              <Input type="password" value={igDid} onChange={(e) => setIgDid(e.target.value)} />
            </div>
          </>
        ) : (
          <div className="min-w-[200px]">
            <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Password</label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
        )}

        <div className="min-w-[240px] flex-1">
          <label className="text-xs font-medium block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Proxy <span style={{ color: 'var(--color-text-muted)' }}>(recommended)</span>
          </label>
          <Input
            type="password"
            placeholder="scheme://user:pass@host:port"
            value={proxy}
            onChange={(e) => setProxy(e.target.value)}
          />
        </div>

        <Button type="submit" size="md" loading={submitting} disabled={!canSubmit}>
          <Plus className="w-3.5 h-3.5" />
          {lockUsername ? 'Refresh' : 'Add account'}
        </Button>
      </div>

      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {lockUsername
          ? 'Re-registering this username updates its session/status in place (upsert-by-username) -- this does not create a second account. Leave proxy blank to keep the current one.'
          : method === 'cookies'
            ? 'Cookies are encrypted at rest and used immediately -- the account is active as soon as this submits.'
            : 'Login runs in the background (real browser automation, ~10-40s) and may hit a 2FA/checkpoint that needs manual resolution over SSH. Password is encrypted at rest the same way cookies are.'}
      </p>
      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        Pin a sticky residential/mobile proxy so login and all scraping share one IP.
        A datacenter IP (or an IP mismatch between login and scraping) is what triggers
        Instagram's checkpoint/"email may not be secure" lockouts. Stored encrypted at rest.
      </p>
    </form>
  );
}
