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

// ISO 3166-1 alpha-2 ("IN", "US") -> flag emoji, by composing the two
// regional-indicator Unicode code points -- covers every country without
// needing a flag sprite/icon set. YouTube's snippet.country is already
// this format (see youtube_parser.py); anything else (missing, or not a
// clean 2-letter code) returns null so callers can skip the pill entirely.
export function countryFlagEmoji(countryCode) {
  if (!countryCode || countryCode.length !== 2) return null;
  const code = countryCode.toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return null;
  const codePoints = [...code].map((c) => 0x1f1e6 + (c.charCodeAt(0) - 65));
  return String.fromCodePoint(...codePoints);
}

// "4 years" / "8 months" -- coarse account-age pill, matching vidiq's
// header badge. Falls back to months under a year so a brand-new channel
// doesn't just show "0 years".
export function formatAccountAge(days) {
  if (days === null || days === undefined || days < 0) return null;
  const years = Math.floor(days / 365);
  if (years >= 1) return `${years} year${years === 1 ? '' : 's'}`;
  const months = Math.max(1, Math.floor(days / 30));
  return `${months} month${months === 1 ? '' : 's'}`;
}
