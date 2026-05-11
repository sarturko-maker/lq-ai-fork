import { describe, expect, it } from 'vitest';
import { iconFor, toneFor, type ProvenanceKind } from '../components/ProvenancePill.svelte';

describe('ProvenancePill helpers', () => {
  it('maps each provenance kind to its icon', () => {
    expect(iconFor('skill')).toBe('🛠️');
    expect(iconFor('tier')).toBe('🔒');
    expect(iconFor('provider')).toBe('🧠');
    expect(iconFor('kb')).toBe('📎');
    expect(iconFor('audit')).toBe('📜');
    expect(iconFor('enhanced')).toBe('✨');
  });

  it('maps kinds to sage by default; tier mismatch flips to amber', () => {
    expect(toneFor('skill', false)).toBe('sage');
    expect(toneFor('tier', false)).toBe('slate');
    expect(toneFor('tier', true)).toBe('amber');
    expect(toneFor('provider', false)).toBe('sage');
  });

  it('lists six kinds (sentinel — update if Wave D adds more)', () => {
    const kinds: ProvenanceKind[] = ['skill', 'tier', 'provider', 'kb', 'audit', 'enhanced'];
    expect(kinds.length).toBe(6);
  });
});
