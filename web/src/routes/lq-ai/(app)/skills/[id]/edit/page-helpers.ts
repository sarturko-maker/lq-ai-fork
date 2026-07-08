/**
 * Pure helpers for the /lq-ai/skills/[id]/edit page's "Proposals" status
 * section — B-2b (ADR-F067 D2/D3).
 *
 * Extracted so vitest can exercise them without a SvelteKit runtime (house
 * pattern — no @testing-library/svelte).
 */
import type { TrustTone } from '$lib/lq-ai/components/TrustPill.svelte';
import type { OrgSkillProposalResponse } from '$lib/lq-ai/api/userSkills';
import type { OrgSkillVersionState } from '$lib/lq-ai/types';

/** Shared admin helper, re-exported so this module stays the page's single
 *  import surface (house-brief precedent). */
export { describeMutationError, formatDateTime } from '$lib/lq-ai/admin/page-helpers';

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
