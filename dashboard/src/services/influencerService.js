import apiClient from './apiClient';

export async function getCategories() {
  const { data } = await apiClient.get('/admin/categories');
  return data;
}

export async function createCategory(name) {
  const { data } = await apiClient.post('/admin/categories', { name });
  return data;
}

export async function createInfluencer(handle, categoryId, scrapePostsSince) {
  const { data } = await apiClient.post('/admin/influencers', {
    handle,
    category_id: categoryId,
    scrape_posts_since: scrapePostsSince || null,
  });
  return data;
}

export async function triggerScrape(influencerId) {
  const { data } = await apiClient.post('/admin/scrape', null, {
    params: { influencer_id: influencerId },
  });
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

export async function updateInfluencerDetails(influencerId, { handle, categoryId }) {
  const { data } = await apiClient.patch(`/admin/influencers/${influencerId}/details`, {
    handle,
    category_id: categoryId,
  });
  return data;
}

export async function updateInfluencerScrapeSettings(influencerId, scrapePostsSince) {
  const { data } = await apiClient.patch(`/admin/influencers/${influencerId}/scrape-settings`, {
    scrape_posts_since: scrapePostsSince || null,
  });
  return data;
}

export async function deleteInfluencer(influencerId) {
  await apiClient.delete(`/admin/influencers/${influencerId}`);
}
