import React, { useState } from 'react';
import { Radio, KeyRound } from 'lucide-react';
import axios from 'axios';
import { useAppStore } from '../../store/useAppStore';
import Button from './Button';
import Input from './Input';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export default function ApiKeyGate({ children }) {
  const apiKey = useAppStore((s) => s.apiKey);
  const setApiKey = useAppStore((s) => s.setApiKey);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);

  if (apiKey) return children;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!draft.trim()) return;
    setChecking(true);
    setError('');
    try {
      // Validate against a real endpoint before persisting -- a stored-but-
      // wrong key would otherwise bounce the user around 401s silently.
      await axios.get(`${BASE_URL}/admin/categories`, { headers: { 'X-API-Key': draft } });
      setApiKey(draft);
    } catch (err) {
      setError(err.response?.status === 401 ? 'Invalid API key.' : 'Could not reach the API.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div
      className="flex items-center justify-center min-h-screen p-6"
      style={{ background: 'var(--color-bg-primary)' }}
    >
      <form
        onSubmit={handleSubmit}
        className="card w-full max-w-sm p-8 flex flex-col gap-5 animate-fade-in"
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center"
            style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)' }}
          >
            <Radio className="w-6 h-6" />
          </div>
          <div>
            <h1 className="font-semibold text-base" style={{ color: 'var(--color-text-primary)' }}>
              Scraper Ops Dashboard
            </h1>
            <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
              Enter the admin API key to continue.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div className="relative">
            <KeyRound
              className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--color-text-muted)' }}
            />
            <Input
              type="password"
              autoFocus
              className="pl-9"
              placeholder="API key"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              error={!!error}
            />
          </div>
          {error && <p className="text-xs" style={{ color: 'var(--color-danger)' }}>{error}</p>}
        </div>

        <Button type="submit" loading={checking} disabled={!draft.trim()}>
          Connect
        </Button>
      </form>
    </div>
  );
}
