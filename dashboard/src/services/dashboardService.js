import apiClient from './apiClient';

export async function getDashboardStatus(reliabilityWindowDays) {
  const { data } = await apiClient.get('/admin/dashboard/status', {
    params: reliabilityWindowDays ? { reliability_window_days: reliabilityWindowDays } : undefined,
  });
  return data;
}

export async function getDashboardMetrics(startDate, endDate) {
  const { data } = await apiClient.get('/admin/dashboard/metrics', {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}

export async function getCredentialHealth(startDate, endDate) {
  const { data } = await apiClient.get('/admin/dashboard/credential-health', {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}

export async function getQueueHistory(startDate, endDate) {
  const { data } = await apiClient.get('/admin/dashboard/queue-history', {
    params: { start_date: startDate, end_date: endDate },
  });
  return data;
}

export async function getAlerts() {
  const { data } = await apiClient.get('/admin/alerts');
  return data;
}

export async function getQueueStatus() {
  const { data } = await apiClient.get('/admin/queue/status');
  return data;
}

export async function getDlqContents() {
  const { data } = await apiClient.get('/admin/queue/dlq');
  return data;
}

export async function getRecentVerifyJobs(limit = 30) {
  const { data } = await apiClient.get('/admin/dashboard/verify-jobs', { params: { limit } });
  return data;
}

export async function getVerifyJobsSummary() {
  const { data } = await apiClient.get('/admin/dashboard/verify-jobs/summary');
  return data;
}
