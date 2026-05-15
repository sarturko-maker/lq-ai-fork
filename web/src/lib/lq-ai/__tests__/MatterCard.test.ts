import { describe, expect, it } from 'vitest';
import { matterBadges } from '../components/MatterCard.svelte';
import type { Project } from '../types';

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    id: 'proj-1',
    name: 'Acme NDA Review',
    slug: 'acme-nda-review',
    description: 'Review the Acme NDA for unusual clauses.',
    owner_id: 'user-1',
    privileged: false,
    minimum_inference_tier: null,
    attached_file_ids: [],
    attached_skill_names: [],
    archived_at: null,
    created_at: '2026-05-12T00:00:00Z',
    updated_at: '2026-05-12T00:00:00Z',
    ...overrides
  };
}

describe('matterBadges', () => {
  it('returns no badges for a plain matter', () => {
    const badges = matterBadges(makeProject());
    expect(badges.showPrivileged).toBe(false);
    expect(badges.showTier).toBe(false);
    expect(badges.tierLabel).toBeNull();
    expect(badges.isArchived).toBe(false);
  });

  it('shows Privileged badge when matter.privileged is true', () => {
    const badges = matterBadges(makeProject({ privileged: true }));
    expect(badges.showPrivileged).toBe(true);
  });

  it('shows tier badge and formats label when minimum_inference_tier is set', () => {
    // Under PRD §1.5.2 (lower = stricter), floor=3 means "Tier 3 or stronger."
    const badges = matterBadges(makeProject({ minimum_inference_tier: 3 }));
    expect(badges.showTier).toBe(true);
    expect(badges.tierLabel).toBe('Tier 3 or stronger');
  });

  it('shows "Tier 1 only" label for the strictest floor', () => {
    const badges = matterBadges(makeProject({ minimum_inference_tier: 1 }));
    expect(badges.tierLabel).toBe('Tier 1 only');
  });

  it('marks matter as archived when archived_at is set', () => {
    const badges = matterBadges(makeProject({ archived_at: '2026-05-12T12:00:00Z' }));
    expect(badges.isArchived).toBe(true);
  });

  it('counts files and skills from attached arrays', () => {
    const badges = matterBadges(
      makeProject({
        attached_file_ids: ['f1', 'f2', 'f3'],
        attached_skill_names: ['nda-review', 'msa-review']
      })
    );
    expect(badges.fileCount).toBe(3);
    expect(badges.skillCount).toBe(2);
  });

  it('defaults to 0 counts when arrays are absent', () => {
    const badges = matterBadges(
      makeProject({ attached_file_ids: undefined, attached_skill_names: undefined })
    );
    expect(badges.fileCount).toBe(0);
    expect(badges.skillCount).toBe(0);
  });
});
