/**
 * Pure helpers for the /lq-ai/skills page — B-2b (ADR-F067 D2/D3).
 *
 * Extracted so vitest can exercise them without a SvelteKit runtime (house
 * pattern — no @testing-library/svelte).
 */
import { LQAIApiError } from '$lib/lq-ai/api/client';
import type { UserSkill } from '$lib/lq-ai/types';
import type { OrgSkillProposalResponse } from '$lib/lq-ai/api/userSkills';

/** Shared admin helper, re-exported so this module stays the page's single
 *  import surface (house-brief precedent). */
export { describeMutationError } from '$lib/lq-ai/admin/page-helpers';

/**
 * Whether the "Propose to Library" row action should render for this row.
 *
 * Author-only, user-scope (ADR-F067 D2 v1: propose is not a team-admin
 * action). `scope='user'` rows returned by `listUserSkills` are always the
 * caller's OWN rows — the backend's `list_user_skills` filters
 * `owner_user_id == user.id` for the user layer (`api/app/api/user_skills.py:395-396`),
 * team-scope rows never carry `scope='user'` — so the scope check alone
 * already is the ownership check; no separate id comparison is needed.
 */
export function canProposeSkill(row: Pick<UserSkill, 'scope'>): boolean {
	return row.scope === 'user';
}

/**
 * The propose endpoint's "an open proposal already exists for slug '...'"
 * 409 (`api/app/api/user_skills.py:1015-1020`) — the ONE conflict case the
 * row action should lock on (disabled + tooltip) rather than let the caller
 * retry immediately. Distinct from the shipped-slug-collision 409 (a
 * doctrine problem, not a timing one) and the concurrent-race 409 (its
 * message literally says "retry") — both of those stay clickable so the
 * caller can read the error and act on it. The UI deliberately does NOT
 * precompute open-proposal state per row (would be an N+1
 * `GET .../proposals` fetch) — this 409 IS the guard.
 */
export function isOpenProposalConflict(err: unknown): boolean {
	return (
		err instanceof LQAIApiError &&
		err.status === 409 &&
		err.message.includes('open proposal already exists')
	);
}

/** Transient success copy naming the slug + version — shown in place of a
 *  toast primitive (none exists in this codebase; see SkillWizard's
 *  "Draft saved" precedent). */
export function proposeSuccessMessage(
	res: Pick<OrgSkillProposalResponse, 'slug' | 'version_no'>
): string {
	return `Proposed "${res.slug}" v${res.version_no} to the Library — an admin will review it.`;
}
