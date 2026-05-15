/**
 * Getting-started checklist signal helpers.
 *
 * Each function returns a Promise<boolean>: true = item is done.
 * Real backend sources are used where the API shape is clean;
 * localStorage flags (V2-FALLBACK) are used where the backend
 * doesn't expose a suitable signal yet.
 */
import { userSkillsApi } from './api';
import type { User } from './types';

/** Item 1: user has logged in and does NOT need a password change. */
export function isPasswordRotated(user: User | null): boolean {
  if (!user) return false;
  return user.must_change_password === false;
}

/**
 * Item 2: user has run a skill on a document.
 * V2-FALLBACK: listMessages() requires a chat_id and doesn't support
 * cross-chat filtering by applied_skills. Use a localStorage flag that the
 * chat shell sets (via lq-ai:onboarded:skill-applied) when a skill response
 * arrives. Task T6 / Wave B chat-shell integration will set this flag.
 */
export function hasRunSkill(): boolean {
  if (typeof localStorage === 'undefined') return false;
  return localStorage.getItem('lq-ai:onboarded:skill-applied') === 'true';
}

/**
 * Item 3: user has tried Enhance Prompt.
 * V2-FALLBACK: no backend endpoint for enhance-prompt-history yet.
 * Task T6 sets this flag on first use.
 */
export function hasTriedEnhance(): boolean {
  if (typeof localStorage === 'undefined') return false;
  return localStorage.getItem('lq-ai:onboarded:enhance') === 'true';
}

/**
 * Item 4: user has attached a knowledge base.
 * V2-FALLBACK: Knowledge browser ships in Wave C.
 * The flag is set when the user visits /lq-ai/knowledge (Wave C).
 */
export function hasAttachedKnowledge(): boolean {
  if (typeof localStorage === 'undefined') return false;
  return localStorage.getItem('lq-ai:onboarded:knowledge') === 'true';
}

/**
 * Item 5: user has saved at least one prompt as a skill.
 * Real backend call: userSkillsApi.listUserSkills('user').
 */
export async function hasSavedSkill(): Promise<boolean> {
  try {
    const skills = await userSkillsApi.listUserSkills('user');
    return skills.length > 0;
  } catch {
    return false;
  }
}
