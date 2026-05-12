import { describe, expect, it } from 'vitest';
import { validateNewMatter } from '../components/NewMatterModal.svelte';
import type { NewMatterFields } from '../components/NewMatterModal.svelte';

function fields(overrides: Partial<NewMatterFields> = {}): NewMatterFields {
  return {
    name: 'Acme NDA Review',
    description: '',
    privileged: false,
    minimum_inference_tier: null,
    ...overrides
  };
}

describe('validateNewMatter', () => {
  it('passes a plain valid matter', () => {
    const result = validateNewMatter(fields());
    expect(result.valid).toBe(true);
    expect(result.nameError).toBeNull();
    expect(result.tierError).toBeNull();
  });

  it('rejects an empty name', () => {
    const result = validateNewMatter(fields({ name: '' }));
    expect(result.valid).toBe(false);
    expect(result.nameError).toBeTruthy();
  });

  it('rejects a name that is whitespace only', () => {
    const result = validateNewMatter(fields({ name: '   ' }));
    expect(result.valid).toBe(false);
    expect(result.nameError).toBeTruthy();
  });

  it('rejects a name longer than 200 characters', () => {
    const result = validateNewMatter(fields({ name: 'A'.repeat(201) }));
    expect(result.valid).toBe(false);
    expect(result.nameError).toMatch(/200/);
  });

  it('requires tier floor when privileged=true and no tier is set', () => {
    const result = validateNewMatter(fields({ privileged: true, minimum_inference_tier: null }));
    expect(result.valid).toBe(false);
    expect(result.tierError).toBeTruthy();
    expect(result.tierError).toMatch(/privileged/i);
  });

  it('passes when privileged=true and a tier floor is provided', () => {
    const result = validateNewMatter(fields({ privileged: true, minimum_inference_tier: 3 }));
    expect(result.valid).toBe(true);
    expect(result.tierError).toBeNull();
  });

  it('does not require tier floor when privileged=false', () => {
    const result = validateNewMatter(fields({ privileged: false, minimum_inference_tier: null }));
    expect(result.valid).toBe(true);
    expect(result.tierError).toBeNull();
  });
});
