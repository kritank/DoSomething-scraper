import apiClient from './apiClient';

export async function getSchema() {
  const { data } = await apiClient.get('/admin/schema');
  return data;
}
