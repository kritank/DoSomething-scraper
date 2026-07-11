import React, { useState } from 'react';
import { ChevronRight, ChevronDown, Table2, Eye } from 'lucide-react';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorState from '../common/ErrorState';

export default function SchemaBrowser({ tables, loading, error, onRetry, onPreviewTable }) {
  const [expanded, setExpanded] = useState(() => new Set());

  const toggle = (name) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="card p-4 flex items-center justify-center h-32">
        <LoadingSpinner size="sm" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-2">
        <ErrorState title="Couldn't load schema" description={error} onRetry={onRetry} />
      </div>
    );
  }

  return (
    <div className="card p-3 flex flex-col gap-0.5 max-h-[22rem] overflow-y-auto">
      <p className="text-xs font-medium px-2 pb-2" style={{ color: 'var(--color-text-secondary)' }}>
        Tables ({tables.length})
      </p>
      {tables.map((table) => {
        const isOpen = expanded.has(table.name);
        return (
          <div key={table.name}>
            <div className="flex items-center gap-1 rounded-lg hover:bg-[var(--color-bg-card-hover)] group">
              <button
                onClick={() => toggle(table.name)}
                className="flex items-center gap-1.5 flex-1 min-w-0 px-2 py-1.5 text-left"
              >
                {isOpen ? (
                  <ChevronDown className="w-3 h-3 shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                ) : (
                  <ChevronRight className="w-3 h-3 shrink-0" style={{ color: 'var(--color-text-muted)' }} />
                )}
                <Table2 className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--color-accent)' }} />
                <span className="text-xs truncate" style={{ color: 'var(--color-text-primary)' }}>{table.name}</span>
              </button>
              <button
                onClick={() => onPreviewTable(table.name)}
                title={`SELECT * FROM ${table.name} LIMIT 100`}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 mr-1 rounded-md shrink-0"
                style={{ color: 'var(--color-text-muted)' }}
              >
                <Eye className="w-3.5 h-3.5" />
              </button>
            </div>
            {isOpen && (
              <div className="ml-6 pl-2 mb-1" style={{ borderLeft: '1px solid var(--color-border-subtle)' }}>
                {table.columns.map((col) => (
                  <div key={col.name} className="flex items-center justify-between gap-2 py-0.5 px-2 text-xs">
                    <span style={{ color: 'var(--color-text-secondary)' }}>{col.name}</span>
                    <span className="shrink-0" style={{ color: 'var(--color-text-muted)' }}>{col.data_type}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
