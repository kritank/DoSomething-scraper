import apiClient from './apiClient';

export async function getYoutubeKeys() {
  const { data } = await apiClient.get('/admin/youtube-keys');
  return data;
}

export async function registerYoutubeKey({ label, apiKey }) {
  const { data } = await apiClient.post('/admin/youtube-keys', { label, api_key: apiKey });
  return data;
}

export async function updateYoutubeKeyStatus(keyId, status) {
  const { data } = await apiClient.patch(`/admin/youtube-keys/${keyId}`, { status });
  return data;
}

export async function deleteYoutubeKey(keyId) {
  await apiClient.delete(`/admin/youtube-keys/${keyId}`);
}
