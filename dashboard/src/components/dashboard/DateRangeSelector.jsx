import React, { useState } from 'react';
import { format, subDays } from 'date-fns';
import Input from '../common/Input';
import { cn } from '../../utils/cn';

const PRESETS = [7, 14, 30, 60, 90];

function toIso(d) {
  return format(d, 'yyyy-MM-dd');
}

export default function DateRangeSelector({ startDate, endDate, onChange }) {
  const [customOpen, setCustomOpen] = useState(false);

  // Detect whether the current range matches one of the fixed presets, so
  // the right button stays highlighted even after a page reload/refetch.
  const activePreset = PRESETS.find((days) => {
    const expectedStart = toIso(subDays(new Date(endDate), days - 1));
    return expectedStart === startDate && endDate === toIso(new Date());
  });

  const applyPreset = (days) => {
    setCustomOpen(false);
    const end = new Date();
    const start = subDays(end, days - 1);
    onChange(toIso(start), toIso(end));
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
            onChange={(e) => onChange(e.target.value, endDate)}
            className="w-[150px]"
          />
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>to</span>
          <Input
            type="date"
            value={endDate}
            min={startDate}
            max={toIso(new Date())}
            onChange={(e) => onChange(startDate, e.target.value)}
            className="w-[150px]"
          />
        </div>
      )}
    </div>
  );
}
