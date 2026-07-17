import apiClient from './apiClient';

// Full DB dump can take a while and outgrow the default 15s timeout as data
// grows -- generous ceiling rather than tuning it precisely.
const EXPORT_TIMEOUT_MS = 5 * 60 * 1000;

function filenameFromDisposition(disposition, fallback) {
  const match = /filename="?([^"]+)"?/.exec(disposition ?? '');
  return match?.[1] ?? fallback;
}

export async function downloadDump() {
  const response = await apiClient.get('/admin/export/dump', {
    responseType: 'blob',
    timeout: EXPORT_TIMEOUT_MS,
  });

  const filename = filenameFromDisposition(
    response.headers['content-disposition'],
    `viralytics_${Date.now()}.dump`,
  );

  const url = URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);

  return filename;
}
