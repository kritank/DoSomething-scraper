// Combines growth series from multiple linked platform accounts into one
// "Combined" line. There's no backend endpoint for this (each platform's
// snapshots live on independent schedules/dates) -- see CreatorDetailOut's
// schema comment -- so the merge happens here, client-side, from the same
// per-influencer /growth responses the single-platform profile page uses.
//
// Strategy: build the union of every date any series has a point on, then
// forward-fill each series across gaps (a platform's last known value
// holds until its next snapshot) so every date has a value for every
// series before summing. Forward-fill, not interpolation -- a snapshot
// value is a real observed count, and holding it flat until the next
// observation is a more honest gap-fill than inventing intermediate
// values. Dates before a series' first point are treated as 0 (that
// platform's account didn't have tracked history yet).
function forwardFill(points, dates) {
  const byDate = new Map(points.map((p) => [p.date, p.value]));
  const firstDate = points[0]?.date;
  let last = null;
  const filled = new Map();
  for (const d of dates) {
    if (byDate.has(d)) last = byDate.get(d) ?? last;
    // Before this series' first observed point, there's nothing to hold
    // flat -- leave it null (excluded from the sum) rather than 0, so a
    // platform linked later doesn't drag the combined total down before
    // it had any tracked history.
    filled.set(d, firstDate && d >= firstDate ? last : null);
  }
  return filled;
}

// Merges N GrowthPoint[] series (each already sorted ascending by date,
// value = cumulative count, e.g. followers or total_views) into one
// combined series with the same shape, `value` = sum across series,
// `daily_delta` recomputed from the combined value (not a sum of the
// individual daily_deltas -- that would double-count/misrepresent gaps
// where a series was forward-filled rather than freshly observed).
export function mergeGrowthSeries(seriesList) {
  const nonEmpty = seriesList.filter((s) => s && s.length > 0);
  if (nonEmpty.length === 0) return [];

  const allDates = [...new Set(nonEmpty.flatMap((s) => s.map((p) => p.date)))].sort();
  const filledPerSeries = nonEmpty.map((s) => forwardFill(s, allDates));

  let prevValue = null;
  return allDates.map((date) => {
    const values = filledPerSeries.map((f) => f.get(date));
    const anyKnown = values.some((v) => v !== null);
    const value = anyKnown ? values.reduce((sum, v) => sum + (v ?? 0), 0) : null;
    const daily_delta = value !== null && prevValue !== null ? value - prevValue : null;
    if (value !== null) prevValue = value;
    return { date, value, daily_delta };
  });
}

// Same idea for the earnings metric, which is a low/high band per point
// (value_low/value_high) rather than a single value.
export function mergeEarningsSeries(seriesList) {
  const nonEmpty = seriesList.filter((s) => s && s.length > 0);
  if (nonEmpty.length === 0) return [];

  const allDates = [...new Set(nonEmpty.flatMap((s) => s.map((p) => p.date)))].sort();

  const fillBand = (points) => {
    const byDate = new Map(points.map((p) => [p.date, [p.value_low, p.value_high]]));
    const firstDate = points[0]?.date;
    let last = [null, null];
    const filled = new Map();
    for (const d of allDates) {
      if (byDate.has(d)) last = byDate.get(d).map((v) => v ?? 0);
      filled.set(d, firstDate && d >= firstDate ? last : [null, null]);
    }
    return filled;
  };

  const filledPerSeries = nonEmpty.map((s) => fillBand(s));

  return allDates.map((date) => {
    const bands = filledPerSeries.map((f) => f.get(date));
    const known = bands.filter(([low]) => low !== null);
    if (known.length === 0) return { date, value_low: null, value_high: null };
    return {
      date,
      value_low: known.reduce((sum, [low]) => sum + low, 0),
      value_high: known.reduce((sum, [, high]) => sum + high, 0),
    };
  });
}

// Merges FormatBreakdownOut objects (one per linked platform) into a single
// combined breakdown, summing per-format counts/views and recomputing
// views_share from the combined totals.
export function mergeFormatBreakdowns(breakdowns) {
  const valid = breakdowns.filter(Boolean);
  if (valid.length === 0) return null;

  const byFormat = { long_form: null, short_form: null };
  for (const b of valid) {
    for (const f of b.formats) {
      if (!byFormat[f.format]) {
        byFormat[f.format] = { format: f.format, post_count: 0, total_views: 0, total_likes: 0, total_comments: 0, avg_views_sum: 0, avg_views_n: 0 };
      }
      const acc = byFormat[f.format];
      acc.post_count += f.post_count;
      acc.total_views += f.total_views;
      acc.total_likes += f.total_likes;
      acc.total_comments += f.total_comments;
      if (f.avg_views != null) {
        acc.avg_views_sum += f.avg_views * f.post_count;
        acc.avg_views_n += f.post_count;
      }
    }
  }

  const totalViews = Object.values(byFormat).reduce((sum, f) => sum + (f?.total_views ?? 0), 0);
  const formats = Object.values(byFormat)
    .filter(Boolean)
    .map((f) => ({
      format: f.format,
      post_count: f.post_count,
      total_views: f.total_views,
      total_likes: f.total_likes,
      total_comments: f.total_comments,
      avg_views: f.avg_views_n > 0 ? f.avg_views_sum / f.avg_views_n : null,
      views_share: totalViews > 0 ? f.total_views / totalViews : 0,
    }));

  return {
    window_days: valid[0].window_days,
    total_views: totalViews,
    formats,
  };
}
