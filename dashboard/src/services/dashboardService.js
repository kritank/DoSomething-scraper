import apiClient from './apiClient';

export async function getDashboardStatus() {
  const { data } = await apiClient.get('/admin/dashboard/status');
  return data;
}

export async function getDashboardMetrics(startDate, endDate) {
  const { data } = await apiClient.get('/admin/dashboard/metrics', {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}
