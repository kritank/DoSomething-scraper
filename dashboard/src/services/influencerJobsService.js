import apiClient from './apiClient';

export async function getInfluencerJobs(influencerId) {
  const { data } = await apiClient.get(`/admin/influencers/${influencerId}/jobs`);
  return data;
}
