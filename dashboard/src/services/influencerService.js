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
