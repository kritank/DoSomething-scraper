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

export async function getCreatorPostPerformance(influencerId, limit = 20, format = undefined) {
  const { data } = await apiClient.get(`/influencers/${influencerId}/posts/performance`, {
    params: { limit, format },
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
