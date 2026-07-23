import apiClient from './apiClient';

export async function getCategories() {
  const { data } = await apiClient.get('/admin/categories');
  return data;
}

export async function createCategory(name) {
  const { data } = await apiClient.post('/admin/categories', { name });
  return data;
}

export async function createInfluencer(handle, categoryId, scrapePostsSince, platform = 'instagram', creatorName = '', accountType = 'individual') {
  const { data } = await apiClient.post('/admin/influencers', {
    handle,
    category_id: categoryId,
    scrape_posts_since: scrapePostsSince || null,
    platform,
    creator_name: creatorName || undefined,
    account_type: accountType,
  });
  return data;
}

export async function triggerScrape(influencerId) {
  const { data } = await apiClient.post('/admin/scrape', null, {
    params: { influencer_id: influencerId },
  });
  return data;
}

export async function refreshVerified(influencerId) {
  const { data } = await apiClient.post(`/admin/influencers/${influencerId}/verify`);
  return data;
}

export async function refreshVerifiedAll(platform) {
  const { data } = await apiClient.post('/admin/influencers/verify-all', null, {
    params: { platform },
  });
  return data;
}

export async function triggerEnrich(influencerId) {
  const { data } = await apiClient.post(`/admin/influencers/${influencerId}/enrich`);
  return data;
}

export async function updateCategory(categoryId, payload) {
  const { data } = await apiClient.patch(`/admin/categories/${categoryId}`, payload);
  return data;
}

export async function deleteCategory(categoryId) {
  await apiClient.delete(`/admin/categories/${categoryId}`);
}

export async function updateInfluencerActive(influencerId, isActive) {
  const { data } = await apiClient.patch(`/admin/influencers/${influencerId}/active`, {
    is_active: isActive,
  });
  return data;
}

export async function updateInfluencerDetails(influencerId, { handle, categoryId, creatorName, accountType }) {
  const payload = { handle, category_id: categoryId };
  // Tri-state on the backend: omit the key entirely to leave the creator
  // link untouched (undefined here, not sent) -- only include it when the
  // caller explicitly passed a value (including "" to unlink).
  if (creatorName !== undefined) {
    payload.creator_name = creatorName;
  }
  if (accountType !== undefined) {
    payload.account_type = accountType;
  }
  const { data } = await apiClient.patch(`/admin/influencers/${influencerId}/details`, payload);
  return data;
}

export async function updateInfluencerScrapeSettings(influencerId, { scrapePostsSince, maxCommentsPerPost } = {}) {
  // The backend applies only whichever key is actually present in the
  // request body (partial update) -- omitting a key here leaves that
  // setting untouched server-side, rather than resetting it to null.
  const payload = {};
  if (scrapePostsSince !== undefined) payload.scrape_posts_since = scrapePostsSince || null;
  if (maxCommentsPerPost !== undefined) {
    payload.max_comments_per_post = maxCommentsPerPost === '' ? null : Number(maxCommentsPerPost);
  }
  const { data } = await apiClient.patch(`/admin/influencers/${influencerId}/scrape-settings`, payload);
  return data;
}

export async function deleteInfluencer(influencerId) {
  await apiClient.delete(`/admin/influencers/${influencerId}`);
}

export async function bulkImportInfluencers(file) {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await apiClient.post('/admin/influencers/bulk', formData, {
    // Override the instance's default 'Content-Type: application/json' so
    // the browser can set its own 'multipart/form-data; boundary=...'
    // header for this one request -- axios/the browser only does that
    // automatically when no Content-Type is already forced.
    headers: { 'Content-Type': undefined },
  });
  return data;
}

export async function downloadBulkImportTemplate() {
  const response = await apiClient.get('/admin/influencers/bulk/template', { responseType: 'blob' });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'influencer_bulk_import_template.xlsx';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
