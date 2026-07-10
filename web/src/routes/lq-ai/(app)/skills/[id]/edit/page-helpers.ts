/**
 * Pure helpers for the /lq-ai/skills/[id]/edit page's "Proposals" status
 * section — B-2b (ADR-F067 D2/D3).
 *
 * Extracted so vitest can exercise them without a SvelteKit runtime (house
 * pattern — no @testing-library/svelte).
 */
import type { TrustTone } from '$lib/lq-ai/components/TrustPill.svelte';
import type { OrgSkillProposalResponse } from '$lib/lq-ai/api/userSkills';
import type { OrgSkillVersionState, User } from '$lib/lq-ai/types';

/** Shared admin helper, re-exported so this module stays the page's single
 *  import surface (house-brief precedent). */
export { describeMutationError, formatDateTime } from '$lib/lq-ai/admin/page-helpers';

/** The list page's transient "Proposed … to the Library" copy, re-exported so
 *  the edit page's "Propose to Library" button reuses ONE message (this module
 *  stays the page's single import surface — house-brief precedent). */
export { proposeSuccessMessage } from '../../page-helpers';

// ---------------------------------------------------------------------------
// ADR-F067 Publish fast-path (publish-admin-skill-fastpath) — role gates for
// the two MUTUALLY EXCLUSIVE org-adoption buttons on the editor page. An org
// admin publishes straight into the Library; a plain member proposes for admin
// review; the platform operator sees neither (ADR-F064 fences the operator off
// tenant-authored content, and publish/propose are exactly that write).
// ---------------------------------------------------------------------------

/**
 * "Publish to org" (admin fast-path) shows only for an org admin who is NOT the
 * platform operator. Mirrors the exact template gate
 * `$auth.user?.is_admin === true && $auth.user?.role !== 'operator'`.
 */
export function canPublish(user: Pick<User, 'is_admin' | 'role'> | null | undefined): boolean {
	return user?.is_admin === true && user?.role !== 'operator';
}

/**
 * "Propose to Library" shows only for a non-admin owner who is NOT the platform
 * operator and NOT a viewer — the propose endpoint is `MutatingUser`-gated and
 * viewer-role logins are enforced read-only (ADR-F064 D1), so rendering the
 * button for a viewer (e.g. a demoted member who still owns skills) could only
 * ever surface a spurious 403. Mutually exclusive with {@link canPublish} by
 * construction — an admin publishes, a member proposes, an operator or viewer
 * sees neither, and no user ever satisfies both.
 */
export function canPropose(user: Pick<User, 'is_admin' | 'role'> | null | undefined): boolean {
	return !!user && user.is_admin !== true && user.role !== 'operator' && user.role !== 'viewer';
}

/**
 * Gate for the whole "Org Library" section (Publish / Propose). Composes the
 * role gates with the same USER-scope rule as {@link showProposalsSection}:
 * the publish/propose endpoints are strictly author-scoped and 404 for
 * team-scope rows (ADR-F067 D2), so on a team skill the section must not
 * render at all — a button there could only ever surface a spurious
 * "not found" error.
 */
export function showOrgLibrarySection(
	scope: 'user' | 'team',
	user: Pick<User, 'is_admin' | 'role'> | null | undefined
): boolean {
	return scope === 'user' && (canPublish(user) || canPropose(user));
}

/**
 * Tone per proposal state — the TrustPill/TierBadge idiom (a tone map +
 * label over the one pill primitive) applied to the five
 * `org_skill_versions.state` values instead of inference tiers.
 */
const STATE_TONE: Record<OrgSkillVersionState, TrustTone> = {
	proposed: 'amber',
	approved: 'sage',
	rejected: 'red',
	revoked: 'red',
	superseded: 'neutral'
};

export function proposalStateTone(state: OrgSkillVersionState): TrustTone {
	return STATE_TONE[state] ?? 'neutral';
}

const STATE_LABEL: Record<OrgSkillVersionState, string> = {
	proposed: 'Proposed',
	approved: 'Approved',
	rejected: 'Rejected',
	revoked: 'Revoked',
	superseded: 'Superseded'
};

export function proposalStateLabel(state: OrgSkillVersionState): string {
	return STATE_LABEL[state] ?? state;
}

/**
 * Gate for the "Proposals" section (and its fetch): only USER-scope skills
 * can be proposed for org-wide adoption (ADR-F067 D2 — the propose/proposals
 * endpoints are strictly author-scoped and 404 for team-scope rows). For a
 * team-scope skill the section simply does not exist — fetching would only
 * surface a spurious "not found" error.
 */
export function showProposalsSection(scope: 'user' | 'team'): boolean {
	return scope === 'user';
}

/**
 * Defensive newest-first sort by `version_no`. The backend already orders
 * this way (`api/app/api/user_skills.py:1097-1101`); sorting client-side too
 * keeps the section correct even if that guarantee ever drifts, at
 * negligible cost for a per-slug proposal list.
 */
export function sortProposalsNewestFirst(
	proposals: OrgSkillProposalResponse[]
): OrgSkillProposalResponse[] {
	return [...proposals].sort((a, b) => b.version_no - a.version_no);
}
