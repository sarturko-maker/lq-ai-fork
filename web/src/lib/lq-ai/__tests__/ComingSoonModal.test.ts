import { describe, expect, it } from 'vitest';
import { copyFor } from '../components/ComingSoonModal.svelte';

describe('ComingSoonModal copy', () => {
  it('names the wave for the destination surface', () => {
    const result = copyFor('matters', 'C');
    expect(result.title).toBe('Matters');
    expect(result.body).toContain('Wave C');
    expect(result.body).toContain('design spec');
  });

  it('falls back gracefully when wave is unknown', () => {
    const result = copyFor('chats', undefined);
    expect(result.title).toBe('Chats');
    expect(result.body).toContain('planned for an upcoming wave');
  });

  it('humanizes tab id for display', () => {
    expect(copyFor('saved-prompts', 'D').title).toBe('Saved Prompts');
  });
});
