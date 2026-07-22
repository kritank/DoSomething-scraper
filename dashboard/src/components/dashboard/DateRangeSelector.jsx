import React, { useState } from 'react';
import Input from '../common/Input';
import { cn } from '../../utils/cn';

const PRESETS = [1, 7, 14, 30, 60, 90];
const DAY_MS = 24 * 60 * 60 * 1000;

// The backend buckets every date range as a UTC calendar day (see
// scrape_job_repo.get_daily_metrics / queue_depth_repo -- both do
// `datetime.combine(date, ...).replace(tzinfo=timezone.utc)`). date-fns'
// plain format()/subDays()/`new Date()` all operate in the BROWSER's local
// timezone, so a non-UTC user picking "Today" or "7d" got a range that
// didn't line up with the backend's UTC day boundaries -- most visibly for
// a user ahead of UTC (e.g. IST) in the first few hours of their local day,
// where "today" locally is still "yesterday" in UTC, silently requesting
// a UTC day that hadn't started yet and showing a truncated/empty chart.
// toISOString() is always UTC, so building the range from that instead of
// date-fns keeps the picker's dates in the same calendar the backend uses.
function toUtcIso(d) {
  return d.toISOString().slice(0, 10);
}

function subUtcDays(d, days) {
  return new Date(d.getTime() - days * DAY_MS);
}

export default function DateRangeSelector({ startDate, endDate, onChange }) {
  const [customOpen, setCustomOpen] = useState(false);

  // Detect whether the current range matches one of the fixed presets, so
  // the right button stays highlighted even after a page reload/refetch.
  const activePreset = PRESETS.find((days) => {
    const expectedStart = toUtcIso(subUtcDays(new Date(`${endDate}T00:00:00Z`), days - 1));
    return expectedStart === startDate && endDate === toUtcIso(new Date());
  });

  const applyPreset = (days) => {
    setCustomOpen(false);
    const end = new Date();
    const start = subUtcDays(end, days - 1);
    onChange(toUtcIso(start), toUtcIso(end));
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {PRESETS.map((days) => (
        <button
          key={days}
          onClick={() => applyPreset(days)}
          className={cn('px-3 py-1.5 rounded-lg text-xs font-medium transition-all')}
          style={{
            background: activePreset === days && !customOpen ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
            color: activePreset === days && !customOpen ? 'white' : 'var(--color-text-secondary)',
            border: '1px solid ' + (activePreset === days && !customOpen ? 'var(--color-accent)' : 'var(--color-border-default)'),
          }}
        >
          {days}d
        </button>
      ))}
      <button
        onClick={() => setCustomOpen((o) => !o)}
        className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
        style={{
          background: customOpen ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
          color: customOpen ? 'white' : 'var(--color-text-secondary)',
          border: '1px solid ' + (customOpen ? 'var(--color-accent)' : 'var(--color-border-default)'),
        }}
      >
        Custom
      </button>

      {customOpen && (
        <div className="flex items-center gap-2">
          <Input
            type="date"
            value={startDate}
            max={endDate}
            onChange={(e) => {
              // A native date input fires onChange with an empty string
              // while the user is still mid-typing (e.g. only the month
              // segment filled in) -- propagating that immediately set
              // startDate to '' and fired a fetch with an invalid date
              // before the user had finished picking one at all. Only
              // forward a complete value.
              if (e.target.value) onChange(e.target.value, endDate);
            }}
            className="w-[150px]"
          />
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>to</span>
          <Input
            type="date"
            value={endDate}
            min={startDate}
            max={toUtcIso(new Date())}
            onChange={(e) => {
              if (e.target.value) onChange(startDate, e.target.value);
            }}
            className="w-[150px]"
          />
        </div>
      )}
    </div>
  );
}
