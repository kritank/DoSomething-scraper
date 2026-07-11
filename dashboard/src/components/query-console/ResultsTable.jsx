import React from 'react';
import { Download, AlertCircle } from 'lucide-react';
import Button from '../common/Button';
import EmptyState from '../common/EmptyState';

function toCsv(columns, rows) {
  const escape = (v) => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  const lines = [columns.map(escape).join(',')];
  for (const row of rows) {
    lines.push(columns.map((c) => escape(row[c])).join(','));
  }
  return lines.join('\n');
}

function downloadCsv(columns, rows) {
  const csv = toCsv(columns, rows);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `query-results-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ResultsTable({ result }) {
  if (!result) return null;

  const { columns, rows, row_count, truncated, duration_ms } = result;

  if (row_count === 0) {
    return <EmptyState title="Query returned no rows" message={`Ran in ${duration_ms}ms.`} />;
  }

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {row_count.toLocaleString()} row{row_count === 1 ? '' : 's'} · {duration_ms}ms
          {truncated && (
            <span className="inline-flex items-center gap-1 ml-2" style={{ color: 'var(--color-warning)' }}>
              <AlertCircle className="w-3 h-3" /> truncated at row cap
            </span>
          )}
        </p>
        <Button variant="secondary" size="sm" onClick={() => downloadCsv(columns, rows)}>
          <Download className="w-3.5 h-3.5" />
          Export CSV
        </Button>
      </div>

      <div className="overflow-auto max-h-[28rem]">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
              {columns.map((col) => (
                <th
                  key={col}
                  className="text-left py-2 px-3 font-medium whitespace-nowrap sticky top-0"
                  style={{ color: 'var(--color-text-secondary)', background: 'var(--color-bg-card)' }}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-[var(--color-bg-card-hover)]" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                {columns.map((col) => (
                  <td key={col} className="py-2 px-3 whitespace-nowrap" style={{ color: 'var(--color-text-primary)' }}>
                    {row[col] === null ? (
                      <span style={{ color: 'var(--color-text-muted)' }}>null</span>
                    ) : (
                      String(row[col])
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
