import React, { useState } from 'react';
import { runQuery } from '../services/queryConsoleService';
import { useAppStore } from '../store/useAppStore';
import SqlEditor from '../components/query-console/SqlEditor';
import ResultsTable from '../components/query-console/ResultsTable';
import QueryHistoryPanel from '../components/query-console/QueryHistoryPanel';

export default function QueryConsole() {
  const [sql, setSql] = useState('SELECT * FROM influencers LIMIT 50');
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const pushQueryHistory = useAppStore((s) => s.pushQueryHistory);

  const handleRun = async () => {
    if (!sql.trim() || running) return;
    setRunning(true);
    try {
      const data = await runQuery(sql);
      setResult(data);
      pushQueryHistory(sql.trim());
    } catch {
      // apiClient's interceptor already surfaces a toast with the detail
      // (e.g. "Only SELECT/WITH statements are allowed.") -- nothing more
      // to do here.
      setResult(null);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Query Console</h2>
        <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
          Ad-hoc read-only SQL against the scraper's tables — categories, influencers, scrape_jobs,
          posts, comments, instagram_accounts, and more.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4 items-start">
        <div className="flex flex-col gap-4">
          <SqlEditor value={sql} onChange={setSql} onRun={handleRun} running={running} />
          <ResultsTable result={result} />
        </div>
        <QueryHistoryPanel onSelect={setSql} />
      </div>
    </div>
  );
}
