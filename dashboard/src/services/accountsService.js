import apiClient from './apiClient';

export async function getAccounts() {
  const { data } = await apiClient.get('/admin/accounts');
  return data;
}
