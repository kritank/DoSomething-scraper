import apiClient from './apiClient';

export async function getCreators() {
  const { data } = await apiClient.get('/admin/creators');
  return data;
}

export async function renameCreator(creatorId, name) {
  const { data } = await apiClient.patch(`/admin/creators/${creatorId}`, { name });
  return data;
}

export async function deleteCreator(creatorId) {
  await apiClient.delete(`/admin/creators/${creatorId}`);
}
