import React from 'react';
import { Play } from 'lucide-react';
import Button from '../common/Button';

export default function SqlEditor({ value, onChange, onRun, running }) {
  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      onRun();
    }
  };

  return (
    <div className="card flex flex-col overflow-hidden">
      {/* Toolbar pinned above the editor -- always visible, never requires
          scrolling past the textarea/results to reach Run. */}
      <div
        className="flex items-center justify-between px-4 py-2.5 shrink-0"
        style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
      >
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          SELECT / WITH only · single statement · read-only role
        </p>
        <Button size="sm" onClick={onRun} loading={running} disabled={!value.trim()}>
          <Play className="w-3.5 h-3.5" />
          Run <span className="opacity-60 ml-1">⌘⏎</span>
        </Button>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        spellCheck={false}
        placeholder="SELECT * FROM influencers LIMIT 50"
        rows={6}
        className="w-full resize-y outline-none text-sm p-4"
        style={{
          fontFamily: 'var(--font-mono)',
          background: 'var(--color-bg-secondary)',
          color: 'var(--color-text-primary)',
        }}
      />
    </div>
  );
}
