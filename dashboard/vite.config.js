import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// No dev proxy here (unlike the consumer-facing DoSomething-fe app) --
// this dashboard talks directly over the network to the deployed EC2 API,
// so CORS on that API (not a proxy) is what makes local dev work.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
  },
});
