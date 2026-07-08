/**
 * /api/v1/user-skills — per-user DB-backed skill CRUD (D8 / ADR 0012).
 *
 * Distinct from the read-side merge surface at ``/api/v1/skills`` (which
 * lives in ``skills.ts``). The two complement each other:
 *
 * - ``skills.ts`` powers the chat-time skill picker — it returns
 *   summaries from the merged built-in + user-shadow view.
 * - ``userSkills.ts`` powers the "manage my skills" surface — it returns
 *   the rich row (body + frontmatter_extra) so the editor can render.
 *
 * Every state-changing call writes an audit row server-side
 * (user_skill.created / .updated / .deleted). Cross-user reads/writes
 * 404; failure paths use the standard ``LQAIApiError`` envelope.
 */
import { apiRequest } from './client';
import type {
	OrgSkillVersionState,
	UserSkill,
	UserSkillCreate,
	UserSkillUpdate,
	UserSkillVersionsResponse
} from '../types';

/**
 * GET /api/v1/user-skills — non-archived rows the caller can edit.
 *
 * Scope filter (D8.1c — default ``'user'`` for back-compat):
 *
 * * ``'user'`` — caller's user-scope rows only.
 * * ``'team'`` — team-scope rows from teams where the caller is admin.
 * * ``'all'`` — both layers merged + sorted by ``updated_at DESC``.
 */
export async function listUserSkills(
	scope: 'user' | 'team' | 'all' = 'user'
): Promise<UserSkill[]> {
	const path = scope === 'user' ? '/user-skills' : `/user-skills?scope=${scope}`;
	return apiRequest<UserSkill[]>(path);
}

/** GET /api/v1/user-skills/{id} — owner-only fetch (404 for non-owner). */
export async function getUserSkill(id: string): Promise<UserSkill> {
	return apiRequest<UserSkill>(`/user-skills/${encodeURIComponent(id)}`);
}

/**
 * POST /api/v1/user-skills — create a new user-scope skill.
 *
 * 409 on slug collision with the caller's existing non-archived rows;
 * collision with a built-in is allowed (the deliberate shadow case
 * per ADR 0012 §2). The Skill Creator UI surfaces shadow collisions
 * as an informational yellow note rather than blocking submit.
 */
export async function createUserSkill(body: UserSkillCreate): Promise<UserSkill> {
	return apiRequest<UserSkill>('/user-skills', { method: 'POST', body });
}

/** PATCH /api/v1/user-skills/{id} — partial update; supplied keys move only. */
export async function updateUserSkill(id: string, body: UserSkillUpdate): Promise<UserSkill> {
	return apiRequest<UserSkill>(`/user-skills/${encodeURIComponent(id)}`, {
		method: 'PATCH',
		body
	});
}

/**
 * DELETE /api/v1/user-skills/{id} — soft-delete via ``archived_at``.
 *
 * Returns 204 on success; 410 on already-archived. The archived row
 * frees the slug so a fresh creation at the same slug succeeds.
 */
export async function deleteUserSkill(id: string): Promise<void> {
	await apiRequest<void>(`/user-skills/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/**
 * GET /api/v1/user-skills/{id}/versions?limit= — Wave D.2 Task 2.6.
 *
 * Audit-log view of edits for this user-skill, ordered most-recent-first.
 * Access posture mirrors the mutable surface: user-scope rows visible
 * only to the owner; team-scope rows only to team-admins. 404 for
 * non-owners. ``limit`` defaults to 50 (backend caps at 200).
 */
export async function listUserSkillVersions(
	skillId: string,
	limit: number = 50
): Promise<UserSkillVersionsResponse> {
	return apiRequest<UserSkillVersionsResponse>(
		`/user-skills/${encodeURIComponent(skillId)}/versions?limit=${limit}`
	);
}

// ---------------------------------------------------------------------------
// ADR-F067 D2/D3 — propose a user-scope skill for org-wide adoption.
//
// Author-side of the org-skills harness (B-2a backend, B-2b UI). A proposal
// is an immutable ``org_skill_versions`` snapshot; the admin review side
// (content view — raw_yaml/body, approve/reject/revoke) lives in
// ``adminApi`` (``admin.ts``), NOT here. This is the status view only.
// ---------------------------------------------------------------------------

/**
 * One ``org_skill_versions`` row from the AUTHOR's point of view.
 * ``state`` is the shared ``OrgSkillVersionState`` union from
 * ``$lib/lq-ai/types`` (also used by the admin review view in ``admin.ts``).
 *
 * Mirrors ``OrgSkillProposalResponse`` (``api/app/api/user_skills.py:858-880``).
 * Deliberately excludes ``raw_yaml``/``body``/``frontmatter`` — the author
 * already has those in the source ``UserSkill`` row; the admin review queue
 * is the content view.
 */
export interface OrgSkillProposalResponse {
	id: string;
	slug: string;
	version_no: number;
	state: OrgSkillVersionState;
	content_hash: string;
	size_bytes: number;
	proposed_at: string;
	reviewed_at?: string | null;
	review_note?: string | null;
	revoked_at?: string | null;
}

/**
 * POST /api/v1/user-skills/{id}/propose — submit this user-scope skill for
 * org-wide adoption (ADR-F067 D2/D3).
 *
 * Owner-only (team-scope, non-owned, and archived rows all 404 — no
 * existence leak). 409 when the slug collides with a shipped skill, or an
 * open proposal for the slug already exists (this is the caller's guard —
 * the UI does NOT precompute open-proposal state to avoid an N+1 list
 * fetch). 422 when the synthesized frontmatter fails the org allowlist, or
 * the content exceeds the size cap. Both error messages are meant to
 * surface verbatim (``describeMutationError`` on the calling page).
 */
export async function proposeUserSkill(id: string): Promise<OrgSkillProposalResponse> {
	return apiRequest<OrgSkillProposalResponse>(
		`/user-skills/${encodeURIComponent(id)}/propose`,
		{ method: 'POST' }
	);
}

/**
 * GET /api/v1/user-skills/{id}/proposals — this skill's org-proposal version
 * history, newest version first (ADR-F067 D2/D3).
 *
 * Strictly author-scoped (same owner-only gate as ``proposeUserSkill``) —
 * NOT the team-admin-visible CRUD gate.
 */
export async function listUserSkillProposals(id: string): Promise<OrgSkillProposalResponse[]> {
	return apiRequest<OrgSkillProposalResponse[]>(
		`/user-skills/${encodeURIComponent(id)}/proposals`
	);
}
