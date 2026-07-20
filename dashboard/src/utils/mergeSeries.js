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

// Merges SponsorshipBreakdownOut objects (one per linked platform) into
// one, re-deriving avg_views/avg_likes/avg_comments as post_count-weighted
// averages -- same simplification mergeFormatBreakdowns already makes
// (weighting by post_count rather than the backend's internal
// usable-values count, which isn't exposed to the frontend).
export function mergeSponsorshipBreakdowns(breakdowns) {
  const valid = breakdowns.filter(Boolean);
  if (valid.length === 0) return null;

  const mergeStats = (statsList) => {
    let post_count = 0, likesSum = 0, commentsSum = 0, viewsSum = 0, viewsN = 0;
    for (const s of statsList) {
      if (!s) continue;
      post_count += s.post_count;
      if (s.avg_likes != null) likesSum += s.avg_likes * s.post_count;
      if (s.avg_comments != null) commentsSum += s.avg_comments * s.post_count;
      if (s.avg_views != null) { viewsSum += s.avg_views * s.post_count; viewsN += s.post_count; }
    }
    return {
      post_count,
      avg_views: viewsN > 0 ? viewsSum / viewsN : null,
      avg_likes: post_count > 0 ? likesSum / post_count : null,
      avg_comments: post_count > 0 ? commentsSum / post_count : null,
    };
  };

  const byFormat = {
    long_form: { organic: [], sponsored: [] },
    short_form: { organic: [], sponsored: [] },
  };
  for (const b of valid) {
    for (const f of b.formats) {
      byFormat[f.format].organic.push(f.organic);
      byFormat[f.format].sponsored.push(f.sponsored);
    }
  }

  return {
    window_days: valid[0].window_days,
    organic: mergeStats(valid.map((b) => b.organic)),
    sponsored: mergeStats(valid.map((b) => b.sponsored)),
    formats: ['long_form', 'short_form'].map((format) => ({
      format,
      organic: mergeStats(byFormat[format].organic),
      sponsored: mergeStats(byFormat[format].sponsored),
    })),
  };
}

// Merges ReplyTimeHeatmapOut objects (one per linked platform) by summing
// bucket_counts index-for-index (bucket_labels are a fixed backend
// constant, so every platform shares the same column layout) and
// combining avg_reply_time_s weighted by reply_count, same weighting
// convention as mergeSponsorshipBreakdowns.
export function mergeReplyTimeHeatmaps(heatmaps) {
  const valid = heatmaps.filter(Boolean);
  if (valid.length === 0) return null;

  const bucketLabels = valid[0].bucket_labels;
  const byFormat = { long_form: [], short_form: [] };
  for (const h of valid) {
    for (const f of h.formats) {
      byFormat[f.format].push(f);
    }
  }

  const mergeFormat = (format, statsList) => {
    const bucketCounts = new Array(bucketLabels.length).fill(0);
    const bucketTimeSum = new Array(bucketLabels.length).fill(0);
    const bucketTimeN = new Array(bucketLabels.length).fill(0);
    // Weighted by bucket_counts[i], same "not every post's comment count
    // is known" approximation mergeSponsorshipBreakdowns already makes
    // for avg_likes/avg_comments -- the backend doesn't expose a separate
    // per-bucket "posts with a known comment count" denominator.
    const bucketCommentsSum = new Array(bucketLabels.length).fill(0);
    const bucketCommentsN = new Array(bucketLabels.length).fill(0);
    let reply_count = 0, timeSum = 0, timeN = 0;
    for (const s of statsList) {
      if (!s) continue;
      reply_count += s.reply_count;
      s.bucket_counts.forEach((c, i) => { bucketCounts[i] += c; });
      (s.bucket_avg_reply_time_s ?? []).forEach((avg, i) => {
        if (avg == null) return;
        bucketTimeSum[i] += avg * s.bucket_counts[i];
        bucketTimeN[i] += s.bucket_counts[i];
      });
      (s.bucket_avg_comments ?? []).forEach((avg, i) => {
        if (avg == null) return;
        bucketCommentsSum[i] += avg * s.bucket_counts[i];
        bucketCommentsN[i] += s.bucket_counts[i];
      });
      if (s.avg_reply_time_s != null) { timeSum += s.avg_reply_time_s * s.reply_count; timeN += s.reply_count; }
    }
    return {
      format,
      reply_count,
      avg_reply_time_s: timeN > 0 ? timeSum / timeN : null,
      bucket_counts: bucketCounts,
      bucket_avg_reply_time_s: bucketTimeN.map((n, i) => (n > 0 ? bucketTimeSum[i] / n : null)),
      bucket_avg_comments: bucketCommentsN.map((n, i) => (n > 0 ? bucketCommentsSum[i] / n : null)),
    };
  };

  return {
    window_days: valid[0].window_days,
    bucket_labels: bucketLabels,
    total_replies: valid.reduce((sum, h) => sum + h.total_replies, 0),
    formats: ['long_form', 'short_form'].map((format) => mergeFormat(format, byFormat[format])),
  };
}

// Merges PostingFrequencyPoint[] lists (one per linked platform) into one
// series, summing post_count for buckets that share the same date.
export function mergePostingFrequency(seriesList) {
  const valid = seriesList.filter(Boolean);
  const byDate = new Map();
  for (const series of valid) {
    for (const point of series) {
      byDate.set(point.date, (byDate.get(point.date) || 0) + point.post_count);
    }
  }
  return Array.from(byDate.entries())
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([date, post_count]) => ({ date, post_count }));
}

// Merges EngagementTrendPoint[] lists (one per linked platform) into one
// series: post_count sums per date, avg_engagement_rate becomes a
// post_count-weighted average across platforms for that date (same
// weighting convention as mergeSponsorshipBreakdowns). No forward-fill --
// unlike a cumulative counter, a bucket with no posts on one platform
// just contributes nothing rather than needing a held-flat value.
export function mergeEngagementTrend(seriesList) {
  const valid = seriesList.filter(Boolean);
  const byDate = new Map();
  for (const series of valid) {
    for (const point of series) {
      if (!byDate.has(point.date)) byDate.set(point.date, { post_count: 0, rateSum: 0, rateN: 0 });
      const acc = byDate.get(point.date);
      acc.post_count += point.post_count;
      if (point.avg_engagement_rate != null) {
        acc.rateSum += point.avg_engagement_rate * point.post_count;
        acc.rateN += point.post_count;
      }
    }
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([date, acc]) => ({
      date,
      post_count: acc.post_count,
      avg_engagement_rate: acc.rateN > 0 ? acc.rateSum / acc.rateN : null,
    }));
}

// Merges PerformanceDecayOut objects (one per linked platform) by
// averaging avg_velocity_per_hour per bucket index, weighted by
// sample_size -- bucket_labels are a fixed backend constant, so every
// platform shares the same column layout.
export function mergePerformanceDecay(decays) {
  const valid = decays.filter(Boolean);
  if (valid.length === 0) return null;

  const bucketLabels = valid[0].bucket_labels;
  const sums = new Array(bucketLabels.length).fill(0);
  const counts = new Array(bucketLabels.length).fill(0);
  for (const d of valid) {
    d.points.forEach((p, i) => {
      if (p.avg_velocity_per_hour != null) sums[i] += p.avg_velocity_per_hour * p.sample_size;
      counts[i] += p.sample_size;
    });
  }

  return {
    window_days: valid[0].window_days,
    bucket_labels: bucketLabels,
    points: bucketLabels.map((label, i) => ({
      bucket_label: label,
      avg_velocity_per_hour: counts[i] > 0 ? sums[i] / counts[i] : null,
      sample_size: counts[i],
    })),
  };
}

// Merges CommentEngagementOut objects (one per linked platform), weighting
// each rate by comment_count -- same weighting convention as
// mergeSponsorshipBreakdowns/mergeReplyTimeHeatmaps.
function mergeCommentStatsList(statsList) {
  let comment_count = 0, replySum = 0, verifiedSum = 0, childSum = 0, likeSum = 0;
  for (const s of statsList) {
    if (!s) continue;
    comment_count += s.comment_count;
    if (s.creator_reply_rate != null) replySum += s.creator_reply_rate * s.comment_count;
    if (s.verified_commenter_rate != null) verifiedSum += s.verified_commenter_rate * s.comment_count;
    if (s.avg_child_comment_count != null) childSum += s.avg_child_comment_count * s.comment_count;
    if (s.avg_likes_per_comment != null) likeSum += s.avg_likes_per_comment * s.comment_count;
  }
  return {
    comment_count,
    creator_reply_rate: comment_count > 0 ? replySum / comment_count : null,
    verified_commenter_rate: comment_count > 0 ? verifiedSum / comment_count : null,
    avg_child_comment_count: comment_count > 0 ? childSum / comment_count : null,
    avg_likes_per_comment: comment_count > 0 ? likeSum / comment_count : null,
  };
}

export function mergeCommentEngagement(breakdowns) {
  const valid = breakdowns.filter(Boolean);
  if (valid.length === 0) return null;

  const byFormat = { long_form: [], short_form: [] };
  for (const b of valid) {
    for (const f of b.formats) byFormat[f.format].push(f);
  }

  return {
    window_days: valid[0].window_days,
    posts_with_comments: valid.reduce((sum, b) => sum + b.posts_with_comments, 0),
    overall: { format: 'overall', ...mergeCommentStatsList(valid.map((b) => b.overall)) },
    formats: ['long_form', 'short_form'].map((format) => ({ format, ...mergeCommentStatsList(byFormat[format]) })),
  };
}

// Merges FollowerRatioPoint[] lists (one per linked platform), same
// forward-fill-then-sum strategy as mergeGrowthSeries (followers/following
// are cumulative account state, not per-period counts) -- ratio is
// re-derived from the combined totals rather than averaging per-platform
// ratios, which would misweight accounts with very different follower counts.
function forwardFillFollowerRatio(points, dates) {
  const byDate = new Map(points.map((p) => [p.date, [p.followers, p.following]]));
  const firstDate = points[0]?.date;
  let last = [null, null];
  const filled = new Map();
  for (const d of dates) {
    if (byDate.has(d)) last = byDate.get(d);
    filled.set(d, firstDate && d >= firstDate ? last : [null, null]);
  }
  return filled;
}

export function mergeFollowerRatioSeries(seriesList) {
  const nonEmpty = seriesList.filter((s) => s && s.length > 0);
  if (nonEmpty.length === 0) return [];

  const allDates = [...new Set(nonEmpty.flatMap((s) => s.map((p) => p.date)))].sort();
  const filledPerSeries = nonEmpty.map((s) => forwardFillFollowerRatio(s, allDates));

  return allDates.map((date) => {
    const pairs = filledPerSeries.map((f) => f.get(date));
    const known = pairs.filter(([followers]) => followers !== null);
    if (known.length === 0) return { date, followers: null, following: null, ratio: null };
    const followers = known.reduce((sum, [f]) => sum + f, 0);
    const following = known.reduce((sum, [, fo]) => sum + (fo ?? 0), 0);
    return { date, followers, following, ratio: following > 0 ? followers / following : null };
  });
}

// Merges PostingTimeDistribution objects (one per linked platform) by
// summing each index of weekday_counts/hour_counts/hourly_weekday_matrix,
// then re-deriving best_weekday/best_hour/total_posts from the combined
// totals.
export function mergePostingTimeDistributions(distributions) {
  const valid = distributions.filter(Boolean);
  const weekday_counts = new Array(7).fill(0);
  const hour_counts = new Array(24).fill(0);
  const hourly_weekday_matrix = Array.from({ length: 7 }, () => new Array(24).fill(0));
  for (const d of valid) {
    (d.weekday_counts || []).forEach((c, i) => { weekday_counts[i] += c; });
    (d.hour_counts || []).forEach((c, i) => { hour_counts[i] += c; });
    (d.hourly_weekday_matrix || []).forEach((row, wd) => {
      (row || []).forEach((c, hr) => { hourly_weekday_matrix[wd][hr] += c; });
    });
  }
  const total_posts = weekday_counts.reduce((a, b) => a + b, 0);
  return {
    weekday_counts,
    hour_counts,
    hourly_weekday_matrix,
    best_weekday: total_posts > 0 ? weekday_counts.indexOf(Math.max(...weekday_counts)) : null,
    best_hour: total_posts > 0 ? hour_counts.indexOf(Math.max(...hour_counts)) : null,
    total_posts,
  };
}
