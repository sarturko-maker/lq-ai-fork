import { describe, it, expect } from 'vitest';
import {
  storageKeyForChat,
  readPersistedOpen,
  writePersistedOpen,
  POLL_INTERVAL_MS,
} from '../components/ReceiptsDrawer.svelte';

class MockStorage implements Storage {
  private map = new Map<string, string>();
  get length() { return this.map.size; }
  key(i: number): string | null { return Array.from(this.map.keys())[i] ?? null; }
  getItem(k: string): string | null { return this.map.get(k) ?? null; }
  setItem(k: string, v: string): void { this.map.set(k, v); }
  removeItem(k: string): void { this.map.delete(k); }
  clear(): void { this.map.clear(); }
}

describe('ReceiptsDrawer helpers', () => {
  it('storageKeyForChat namespaces by chat ID', () => {
    expect(storageKeyForChat('c1')).toBe('lq_ai_receipts_drawer_open_c1');
    expect(storageKeyForChat('uuid-here')).toBe('lq_ai_receipts_drawer_open_uuid-here');
  });

  it('readPersistedOpen returns false for unset', () => {
    const s = new MockStorage();
    expect(readPersistedOpen('c1', s)).toBe(false);
  });

  it('readPersistedOpen returns true when persisted true', () => {
    const s = new MockStorage();
    s.setItem(storageKeyForChat('c1'), 'true');
    expect(readPersistedOpen('c1', s)).toBe(true);
  });

  it('writePersistedOpen writes "true" or "false" strings', () => {
    const s = new MockStorage();
    writePersistedOpen('c1', true, s);
    expect(s.getItem(storageKeyForChat('c1'))).toBe('true');
    writePersistedOpen('c1', false, s);
    expect(s.getItem(storageKeyForChat('c1'))).toBe('false');
  });

  it('write→read round-trip is correct', () => {
    const s = new MockStorage();
    writePersistedOpen('c1', true, s);
    expect(readPersistedOpen('c1', s)).toBe(true);
    writePersistedOpen('c1', false, s);
    expect(readPersistedOpen('c1', s)).toBe(false);
  });

  it('POLL_INTERVAL_MS is exposed for testing', () => {
    expect(POLL_INTERVAL_MS).toBe(5000);
  });
});
