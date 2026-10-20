import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Node 26+ has an experimental undefined globalThis.localStorage unless --localstorage-file is set.
// Ensure a standard in-memory Storage object is available for happy-dom tests.
if (!window.localStorage || typeof window.localStorage.clear !== 'function') {
  const store = new Map<string, string>();
  const mockStorage: Storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => { store.set(key, String(value)); },
    removeItem: (key: string) => { store.delete(key); },
    clear: () => { store.clear(); },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() { return store.size; }
  };
  Object.defineProperty(window, 'localStorage', { value: mockStorage, configurable: true, writable: true });
  Object.defineProperty(globalThis, 'localStorage', { value: mockStorage, configurable: true, writable: true });
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.history.replaceState(null, '', '/');
});
