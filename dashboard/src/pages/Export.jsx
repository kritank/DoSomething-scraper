import React, { useState } from 'react';
import { DatabaseBackup, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { downloadDump } from '../services/exportService';

export default function Export() {
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      const filename = await downloadDump();
      toast.success(`Downloaded ${filename}`);
    } catch {
      // apiClient's interceptor already surfaces a toast with the detail.
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div>
        <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Export</h2>
        <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
          Download a full snapshot of the database to restore locally.
        </p>
      </div>

      <div
        className="max-w-xl rounded-2xl p-6 flex flex-col gap-4"
        style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
      >
        <div className="flex items-start gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'var(--color-accent-dim)', color: 'var(--color-accent)' }}
          >
            <DatabaseBackup className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              Database dump
            </h3>
            <p className="text-sm mt-1" style={{ color: 'var(--color-text-muted)' }}>
              Runs <code>pg_dump</code> against the live database and downloads a compressed,
              custom-format dump (<code>.dump</code>). Every table, no filtering. Restore it locally with:
            </p>
            <pre
              className="text-xs mt-2 px-3 py-2 rounded-lg overflow-x-auto"
              style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }}
            >
              pg_restore --no-owner --no-privileges --clean --if-exists -d &lt;local_db&gt; &lt;file&gt;
            </pre>
          </div>
        </div>

        <button
          onClick={handleDownload}
          disabled={downloading}
          className="self-start flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all disabled:opacity-60"
          style={{ background: 'var(--color-accent)', color: 'var(--color-bg-primary)' }}
        >
          {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <DatabaseBackup className="w-4 h-4" />}
          {downloading ? 'Generating dump…' : 'Download dump'}
        </button>
      </div>
    </div>
  );
}
