import apiClient from './apiClient';

export async function getInfluencerJobs(influencerId) {
  const { data } = await apiClient.get(`/admin/influencers/${influencerId}/jobs`);
  return data;
}

export async function cancelJob(jobId) {
  const { data } = await apiClient.post(`/admin/jobs/${jobId}/cancel`);
  return data;
}
