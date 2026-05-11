import { describe, expect, it } from 'vitest';
import { toneClassFor, labelFor } from '../components/TrustPill.svelte';

describe('TrustPill helpers', () => {
  it('maps secure variant to sage tone by default', () => {
    expect(toneClassFor('secure', undefined)).toBe('lq-pill-tone-sage');
  });

  it('maps tier variant to slate tone by default', () => {
    expect(toneClassFor('tier', undefined)).toBe('lq-pill-tone-slate');
  });

  it('honors explicit override tone', () => {
    expect(toneClassFor('tier', 'amber')).toBe('lq-pill-tone-amber');
    expect(toneClassFor('secure', 'red')).toBe('lq-pill-tone-red');
  });

  it('falls back to neutral for unknown variants', () => {
    // @ts-expect-error testing runtime fallback
    expect(toneClassFor('mystery', undefined)).toBe('lq-pill-tone-neutral');
  });

  it('labelFor returns "●" alone in dot mode', () => {
    expect(labelFor('● self-hosted', 'dot')).toBe('●');
    expect(labelFor('● self-hosted', 'label')).toBe('● self-hosted');
  });
});
