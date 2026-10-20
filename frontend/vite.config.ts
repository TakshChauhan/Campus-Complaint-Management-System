/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: false,
  },
  build: {
    // Campus photos are fingerprinted assets; never inline them into JS.
    assetsInlineLimit: 4096,
  },
  test: {
    environment: 'happy-dom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    css: false,
    // Google sign-in tests need the feature flag on, whatever the local .env says.
    env: { VITE_GOOGLE_AUTH_ENABLED: 'true' },
  },
});
