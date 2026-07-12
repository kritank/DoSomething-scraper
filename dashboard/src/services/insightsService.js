import apiClient from './apiClient';

export async function getBenchmark(categoryId) {
  // 404 here just means "not computed yet for this category" -- a normal,
  // expected state today (the aggregation job isn't implemented), not a
  // real error worth a global toast. The page renders its own EmptyState.
  const { data } = await apiClient.get(`/benchmarks/${categoryId}`, { suppressErrorToast: true });
  return data;
}

export async function getRecommendations(influencerId) {
  const { data } = await apiClient.get(`/recommendations/${influencerId}`);
  return data;
}
