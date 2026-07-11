import apiClient from './apiClient';

export async function runQuery(sql) {
  const { data } = await apiClient.post('/admin/query', { sql });
  return data;
}
