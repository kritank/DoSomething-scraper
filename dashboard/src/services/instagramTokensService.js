import apiClient from './apiClient';

export async function getInstagramTokens() {
  const { data } = await apiClient.get('/admin/instagram-tokens');
  return data;
}

export async function registerInstagramTokenFacebookLogin({ label, appId, appSecret, shortToken }) {
  const { data } = await apiClient.post('/admin/instagram-tokens/facebook-login', {
    label,
    app_id: appId,
    app_secret: appSecret,
    short_token: shortToken,
  });
  return data;
}

export async function registerInstagramTokenInstagramLogin({ label, appId, appSecret, token, igUserId }) {
  const { data } = await apiClient.post('/admin/instagram-tokens/instagram-login', {
    label,
    app_id: appId,
    app_secret: appSecret,
    token,
    ig_user_id: igUserId,
  });
  return data;
}

export async function updateInstagramTokenStatus(tokenId, status) {
  const { data } = await apiClient.patch(`/admin/instagram-tokens/${tokenId}`, { status });
  return data;
}

export async function deleteInstagramToken(tokenId) {
  await apiClient.delete(`/admin/instagram-tokens/${tokenId}`);
}
