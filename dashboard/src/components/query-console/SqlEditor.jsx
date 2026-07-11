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
    <div className="card p-4 flex flex-col gap-3">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        spellCheck={false}
        placeholder="SELECT * FROM influencers LIMIT 50"
        rows={8}
        className="w-full resize-y outline-none text-sm p-3 rounded-xl"
        style={{
          fontFamily: 'var(--font-mono)',
          background: 'var(--color-bg-secondary)',
          color: 'var(--color-text-primary)',
          border: '1px solid var(--color-border-default)',
        }}
      />
      <div className="flex items-center justify-between">
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          SELECT / WITH only · single statement · read-only role
        </p>
        <Button size="sm" onClick={onRun} loading={running} disabled={!value.trim()}>
          <Play className="w-3.5 h-3.5" />
          Run <span className="opacity-60 ml-1">⌘⏎</span>
        </Button>
      </div>
    </div>
  );
}
