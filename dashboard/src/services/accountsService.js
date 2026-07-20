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

export async function updateAccountStatus(accountId, status) {
  const { data } = await apiClient.patch(`/admin/accounts/${accountId}`, { status });
  return data;
}

export async function setAccountProxy(accountId, proxy) {
  const { data } = await apiClient.patch(`/admin/accounts/${accountId}/proxy`, { proxy: proxy || null });
  return data;
}

export async function deleteAccount(accountId) {
  await apiClient.delete(`/admin/accounts/${accountId}`);
}

export async function getInstagramBackend() {
  const { data } = await apiClient.get('/admin/settings/instagram-backend');
  return data;
}

export async function setInstagramBackend(backend) {
  const { data } = await apiClient.put('/admin/settings/instagram-backend', { backend });
  return data;
}
