import React, { useRef, useState } from 'react';
import { Upload, Download, ChevronDown, ChevronUp, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import Button from '../common/Button';
import { bulkImportInfluencers, downloadBulkImportTemplate } from '../../services/influencerService';

const STATUS_ICON = {
  created: { Icon: CheckCircle2, color: 'var(--color-success)' },
  partial: { Icon: AlertTriangle, color: 'var(--color-warning)' },
  error: { Icon: XCircle, color: 'var(--color-danger)' },
};

// Collapsed by default -- this is a bulk/power-user action, not the
// everyday single-add flow (AddInfluencerForm), so it shouldn't compete
// for attention on a page that's opened constantly.
export default function MassImportInfluencersForm({ onImported }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    setFile(e.target.files?.[0] ?? null);
    setResult(null);
  };

  const handleSubmit = async () => {
    if (!file || submitting) return;
    setSubmitting(true);
    setResult(null);
    try {
      const data = await bulkImportInfluencers(file);
      setResult(data);
      if (data.created_count > 0) {
        toast.success(`${data.created_count} of ${data.total_rows} row(s) created`);
        onImported();
      } else {
        toast.error(`All ${data.total_rows} row(s) failed -- see details below`);
      }
    } catch {
      // apiClient's interceptor already toasts the error detail.
    } finally {
      setSubmitting(false);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      await downloadBulkImportTemplate();
    } catch {
      toast.error('Could not download the template.');
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-sm font-medium self-start"
        style={{ color: 'var(--color-accent)' }}
      >
        <Upload className="w-3.5 h-3.5" />
        Mass insert from Excel
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>

      {open && (
        <div className="flex flex-col gap-3 p-3.5 rounded-xl" style={{ background: 'var(--color-bg-secondary)' }}>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-muted)' }}>
            Upload an <code>.xlsx</code> file with columns <code>creator_name</code>, <code>category</code>,{' '}
            <code>type</code> (individual/business), <code>instagram_handle</code> (optional), and{' '}
            <code>youtube_handle</code> (optional) -- at least one handle is required per row, and every{' '}
            <code>category</code> value must already exist. Rows with both handles link the two accounts
            under the same creator, same as the single-add form above.
          </p>

          <div className="flex items-center gap-3 flex-wrap">
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xlsm"
              onChange={handleFileChange}
              className="text-xs"
              style={{ color: 'var(--color-text-secondary)' }}
            />
            <Button size="sm" onClick={handleSubmit} loading={submitting} disabled={!file}>
              <Upload className="w-3.5 h-3.5" />
              Upload &amp; import
            </Button>
            <Button variant="ghost" size="sm" onClick={handleDownloadTemplate}>
              <Download className="w-3.5 h-3.5" />
              Download template
            </Button>
          </div>

          {result && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                {result.created_count} of {result.total_rows} row{result.total_rows === 1 ? '' : 's'} created
                {result.error_count > 0 && `, ${result.error_count} failed`}.
              </p>
              <div
                className="flex flex-col divide-y max-h-64 overflow-y-auto rounded-lg border"
                style={{ borderColor: 'var(--color-border-subtle)' }}
              >
                {result.rows.map((row) => {
                  const { Icon, color } = STATUS_ICON[row.status];
                  return (
                    <div key={row.row} className="flex items-start gap-2 px-3 py-2 text-xs">
                      <Icon className="w-3.5 h-3.5 shrink-0 mt-0.5" style={{ color }} />
                      <div className="min-w-0">
                        <span className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
                          Row {row.row}{row.creator_name ? ` — ${row.creator_name}` : ''}
                        </span>
                        <span className="ml-1.5" style={{ color: 'var(--color-text-muted)' }}>{row.message}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
