import React, { useCallback, useEffect, useState } from 'react';
import { runQuery } from '../services/queryConsoleService';
import { getSchema } from '../services/schemaService';
import { useAppStore } from '../store/useAppStore';
import SqlEditor from '../components/query-console/SqlEditor';
import ResultsTable from '../components/query-console/ResultsTable';
import QueryHistoryPanel from '../components/query-console/QueryHistoryPanel';
import SchemaBrowser from '../components/query-console/SchemaBrowser';

export default function QueryConsole() {
  const [sql, setSql] = useState('SELECT * FROM influencers LIMIT 50');
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const pushQueryHistory = useAppStore((s) => s.pushQueryHistory);

  const [tables, setTables] = useState([]);
  const [schemaLoading, setSchemaLoading] = useState(true);
  const [schemaError, setSchemaError] = useState(null);

  const loadSchema = useCallback(async () => {
    setSchemaLoading(true);
    setSchemaError(null);
    try {
      setTables(await getSchema());
    } catch (err) {
      setSchemaError(err.message);
    } finally {
      setSchemaLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSchema();
  }, [loadSchema]);

  const runSql = useCallback(
    async (sqlToRun) => {
      if (!sqlToRun.trim() || running) return;
      setRunning(true);
      try {
        const data = await runQuery(sqlToRun);
        setResult(data);
        pushQueryHistory(sqlToRun.trim());
      } catch {
        // apiClient's interceptor already surfaces a toast with the detail.
        setResult(null);
      } finally {
        setRunning(false);
      }
    },
    [running, pushQueryHistory],
  );

  const handlePreviewTable = (tableName) => {
    const query = `SELECT * FROM ${tableName} LIMIT 100`;
    setSql(query);
    runSql(query);
  };

  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div>
        <h2 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>Query Console</h2>
        <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
          Ad-hoc read-only SQL against the engine's tables. Click a table on the left to preview it.
        </p>
      </div>

      {/* minmax(0,1fr) instead of 1fr -- a plain 1fr track won't shrink
          below its content's intrinsic width, so a wide results table
          blows out the whole page's horizontal scroll instead of
          scrolling within its own card. */}
      <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)] gap-4 items-start min-w-0">
        <div className="flex flex-col gap-4 min-w-0">
          <SchemaBrowser
            tables={tables}
            loading={schemaLoading}
            error={schemaError}
            onRetry={loadSchema}
            onPreviewTable={handlePreviewTable}
          />
          <QueryHistoryPanel onSelect={setSql} />
        </div>
        <div className="flex flex-col gap-4 min-w-0">
          <SqlEditor value={sql} onChange={setSql} onRun={() => runSql(sql)} running={running} />
          <ResultsTable result={result} />
        </div>
      </div>
    </div>
  );
}
