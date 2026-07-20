import apiClient from './apiClient';

export async function getInstagramGraphTokens() {
  const { data } = await apiClient.get('/admin/instagram-graph-tokens');
  return data;
}

export async function registerInstagramGraphToken({ label, accessToken }) {
  const { data } = await apiClient.post('/admin/instagram-graph-tokens', {
    label,
    access_token: accessToken,
  });
  return data;
}

export async function updateInstagramGraphTokenStatus(tokenId, status) {
  const { data } = await apiClient.patch(`/admin/instagram-graph-tokens/${tokenId}`, { status });
  return data;
}

export async function deleteInstagramGraphToken(tokenId) {
  await apiClient.delete(`/admin/instagram-graph-tokens/${tokenId}`);
}
