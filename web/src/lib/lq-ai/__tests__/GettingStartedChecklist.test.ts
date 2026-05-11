/**
 * Unit tests for the getting-started signal helpers.
 *
 * Covers the 5 detection-signal functions: isPasswordRotated (synchronous,
 * reads user object), hasRunSkill / hasTriedEnhance / hasAttachedKnowledge
 * (synchronous, read localStorage), and hasSavedSkill (async, calls
 * userSkillsApi.listUserSkills).
 *
 * localStorage is mocked via vi.stubGlobal per the pattern in preferences.test.ts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  isPasswordRotated,
  hasRunSkill,
  hasTriedEnhance,
  hasAttachedKnowledge,
  hasSavedSkill
} from '../getting-started-signals';
import type { User } from '../types';

// ---- localStorage mock ----

let mockStorage: Record<string, string> = {};

const localStorageMock = {
  getItem: (key: string) => mockStorage[key] ?? null,
  setItem: (key: string, val: string) => { mockStorage[key] = val; },
  removeItem: (key: string) => { delete mockStorage[key]; },
  clear: () => { mockStorage = {}; }
};

beforeEach(() => {
  mockStorage = {};
  vi.stubGlobal('localStorage', localStorageMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---- minimal User fixture ----

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 'u1',
    email: 'test@example.com',
    is_admin: false,
    mfa_enabled: false,
    must_change_password: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides
  };
}

// ---- isPasswordRotated ----

describe('isPasswordRotated', () => {
  it('returns true when must_change_password is false', () => {
    expect(isPasswordRotated(makeUser({ must_change_password: false }))).toBe(true);
  });

  it('returns false when must_change_password is true', () => {
    expect(isPasswordRotated(makeUser({ must_change_password: true }))).toBe(false);
  });

  it('returns false when user is null', () => {
    expect(isPasswordRotated(null)).toBe(false);
  });
});

// ---- hasRunSkill ----

describe('hasRunSkill', () => {
  it('returns false when flag is absent', () => {
    expect(hasRunSkill()).toBe(false);
  });

  it('returns true when lq-ai:onboarded:skill-applied is "true"', () => {
    localStorageMock.setItem('lq-ai:onboarded:skill-applied', 'true');
    expect(hasRunSkill()).toBe(true);
  });

  it('returns false when flag is "false"', () => {
    localStorageMock.setItem('lq-ai:onboarded:skill-applied', 'false');
    expect(hasRunSkill()).toBe(false);
  });
});

// ---- hasTriedEnhance ----

describe('hasTriedEnhance', () => {
  it('returns false when flag is absent', () => {
    expect(hasTriedEnhance()).toBe(false);
  });

  it('returns true when lq-ai:onboarded:enhance is "true"', () => {
    localStorageMock.setItem('lq-ai:onboarded:enhance', 'true');
    expect(hasTriedEnhance()).toBe(true);
  });
});

// ---- hasAttachedKnowledge ----

describe('hasAttachedKnowledge', () => {
  it('returns false when flag is absent', () => {
    expect(hasAttachedKnowledge()).toBe(false);
  });

  it('returns true when lq-ai:onboarded:knowledge is "true"', () => {
    localStorageMock.setItem('lq-ai:onboarded:knowledge', 'true');
    expect(hasAttachedKnowledge()).toBe(true);
  });
});

// ---- hasSavedSkill ----
// hasSavedSkill wraps userSkillsApi.listUserSkills; tested via the exported
// function directly with a mock injected through the api module spy.

import * as api from '../api';

describe('hasSavedSkill', () => {
  it('returns true when listUserSkills returns at least one skill', async () => {
    vi.spyOn(api.userSkillsApi, 'listUserSkills').mockResolvedValueOnce(
      [{ id: 's1', slug: 'my-skill', scope: 'user', owner_user_id: 'u1', owner_team_id: null,
         display_name: 'My Skill', description: '', version: '1.0.0', tags: [],
         frontmatter_extra: {}, body: '', archived_at: null,
         created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }]
    );
    expect(await hasSavedSkill()).toBe(true);
    vi.restoreAllMocks();
  });

  it('returns false when listUserSkills returns empty array', async () => {
    vi.spyOn(api.userSkillsApi, 'listUserSkills').mockResolvedValueOnce([]);
    expect(await hasSavedSkill()).toBe(false);
    vi.restoreAllMocks();
  });

  it('returns false when listUserSkills throws', async () => {
    vi.spyOn(api.userSkillsApi, 'listUserSkills').mockRejectedValueOnce(new Error('network'));
    expect(await hasSavedSkill()).toBe(false);
    vi.restoreAllMocks();
  });
});
