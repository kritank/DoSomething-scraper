import apiClient from './apiClient';

export async function getCreatorStats(influencerId) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/stats`, {
    // A 404 here just means "no snapshots yet" -- the page renders its own
    // EmptyState for that instead of a global error toast.
    suppressErrorToast: true,
  });
  return data;
}

export async function getCreatorGrowth(influencerId, days, metric) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/growth`, {
    params: { days, metric },
  });
  return data;
}

export async function getCreatorPostPerformance(influencerId, limit = 20, format = undefined, sort = 'latest') {
  const { data } = await apiClient.get(`/influencers/${influencerId}/posts/performance`, {
    params: { limit, format, sort },
  });
  return data;
}

export async function getCreatorFormatBreakdown(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/formats`, {
    params: { days },
  });
  return data;
}

export async function getCreatorKeyEvents(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/events`, {
    params: { days },
  });
  return data;
}

export async function getCreatorPostingFrequency(influencerId, days, bucket = 'week') {
  const { data } = await apiClient.get(`/influencers/${influencerId}/posting-frequency`, {
    params: { days, bucket },
  });
  return data;
}

export async function getCreatorPostingTimes(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/posting-times`, {
    params: { days },
  });
  return data;
}

export async function getCreatorSponsorshipBreakdown(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/sponsorship`, {
    params: { days },
  });
  return data;
}

export async function getCreatorReplyTimeHeatmap(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/reply-time-heatmap`, {
    params: { days },
  });
  return data;
}

export async function getCreatorEngagementTrend(influencerId, days, bucket = 'week') {
  const { data } = await apiClient.get(`/influencers/${influencerId}/engagement-trend`, {
    params: { days, bucket },
  });
  return data;
}

export async function getCreatorPerformanceDecay(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/performance-decay`, {
    params: { days },
  });
  return data;
}

export async function getCreatorCommentEngagement(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/comment-engagement`, {
    params: { days },
  });
  return data;
}

export async function getCreatorFollowerRatio(influencerId, days) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/follower-ratio`, {
    params: { days },
  });
  return data;
}
