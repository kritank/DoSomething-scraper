import apiClient from './apiClient';

export async function getDashboardStatus() {
  const { data } = await apiClient.get('/admin/dashboard/status');
  return data;
}

export async function getDashboardMetrics(days = 30) {
  const { data } = await apiClient.get('/admin/dashboard/metrics', { params: { days } });
  return data;
}
