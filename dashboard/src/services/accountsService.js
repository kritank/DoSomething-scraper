import apiClient from './apiClient';

export async function getAccounts() {
  const { data } = await apiClient.get('/admin/accounts');
  return data;
}

export async function registerAccountViaCookies(payload) {
  const { data } = await apiClient.post('/admin/accounts/cookies', payload);
  return data;
}

export async function registerAccountViaLogin(payload) {
  const { data } = await apiClient.post('/admin/accounts/login', payload);
  return data;
}
