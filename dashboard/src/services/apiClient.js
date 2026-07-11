import axios from 'axios';
import { toast } from 'sonner';
import { useAppStore } from '../store/useAppStore';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15_000,
});

apiClient.interceptors.request.use((config) => {
  const apiKey = useAppStore.getState().apiKey;
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;

    if (status === 401) {
      // Key was rejected (or never set) -- clear it so ApiKeyGate re-prompts.
      useAppStore.getState().clearApiKey();
      return Promise.reject(new Error('Invalid or missing API key.'));
    }

    // FastAPI's own validation errors put an array under `detail`; this
    // app's custom exceptions (ViralyticBaseError subclasses) put a plain
    // string there instead -- handle both.
    const detail = error.response?.data?.detail;
    let message;
    if (Array.isArray(detail)) {
      message = detail.map((d) => `${d.loc?.slice(-1)[0] ?? 'field'}: ${d.msg}`).join('; ');
    } else if (typeof detail === 'string') {
      message = detail;
    } else {
      message = error.message || 'Request failed.';
    }

    if (status !== undefined) {
      toast.error(message);
    }
    return Promise.reject(new Error(message));
  },
);

export default apiClient;
