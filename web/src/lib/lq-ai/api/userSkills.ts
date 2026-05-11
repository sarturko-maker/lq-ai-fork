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
import type { UserSkill, UserSkillCreate, UserSkillUpdate } from '../types';

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
