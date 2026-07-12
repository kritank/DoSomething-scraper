import apiClient from './apiClient';

export async function listPosts(params) {
  const { data } = await apiClient.get('/admin/posts', { params });
  return data;
}
