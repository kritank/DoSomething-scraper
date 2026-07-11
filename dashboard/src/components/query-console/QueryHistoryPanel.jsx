import React from 'react';
import { History } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import EmptyState from '../common/EmptyState';

export default function QueryHistoryPanel({ onSelect }) {
  const queryHistory = useAppStore((s) => s.queryHistory);

  if (queryHistory.length === 0) {
    return (
      <div className="card p-4">
        <EmptyState
          icon={<History className="w-7 h-7" style={{ color: 'var(--color-accent)' }} />}
          title="No history yet"
          message="Queries you run will show up here."
        />
      </div>
    );
  }

  return (
    <div className="card p-4 flex flex-col gap-1">
      <p className="text-xs font-medium mb-2" style={{ color: 'var(--color-text-secondary)' }}>Recent queries</p>
      {queryHistory.map((sql, i) => (
        <button
          key={i}
          onClick={() => onSelect(sql)}
          className="text-left text-xs p-2.5 rounded-lg truncate transition-colors hover:bg-[var(--color-bg-card-hover)]"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}
          title={sql}
        >
          {sql}
        </button>
      ))}
    </div>
  );
}
