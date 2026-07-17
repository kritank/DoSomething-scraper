import { format as formatDateFns, parseISO } from 'date-fns';

// Shared date formatting for chart tooltips/axes across the creator-stats
// page -- one place to keep the "MMM d, yyyy" convention consistent.
export function formatDate(isoDateOrDatetime) {
  if (!isoDateOrDatetime) return '—';
  return formatDateFns(parseISO(isoDateOrDatetime), 'MMM d, yyyy');
}

// Compact display for large counts (subscribers, views) -- "34.1M", "11.5B" --
// matching the style vidiq/Social Blade-type stats pages use, so headline
// numbers stay readable at a glance instead of wrapping as "34123456".
export function formatCompactNumber(value) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

// Signed compact delta, e.g. "+1.2K" / "-340" -- for growth chips.
export function formatSignedCompact(value) {
  if (value === null || value === undefined) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${formatCompactNumber(value)}`;
}

export function formatUsdRange(low, high) {
  const fmt = (v) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);
  return `${fmt(low)} – ${fmt(high)}`;
}

export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}
