/**
 * /api/v1/teams — user-facing team read endpoints (D8.1a + D8.1c).
 *
 * Distinct from the operator-admin surface at /api/v1/admin/teams (which
 * lives under :mod:`admin.ts` if it ever needs a typed client). These
 * read-only endpoints back the UI's team picker and the team-membership
 * surfaces — they return only the caller's memberships and carry the
 * ``caller_role`` field so the UI knows whether to render mutate
 * affordances without a second round-trip.
 */
import { apiRequest } from './client';
import type { Team, TeamSummary } from '../types';

/**
 * GET /api/v1/teams — caller's teams (newest first). Each row carries
 * ``caller_role`` so the UI can show admin badges or hide member-only
 * affordances. The optional ``role`` filter restricts to a specific
 * membership role — the team-scope skill creation picker uses
 * ``'admin'`` so only mutate-eligible teams render.
 */
export async function listMyTeams(
	role?: 'admin' | 'member'
): Promise<TeamSummary[]> {
	const path = role ? `/teams?role=${role}` : '/teams';
	return apiRequest<TeamSummary[]>(path);
}

/**
 * GET /api/v1/teams/{id} — full team payload (with roster) for a team
 * the caller belongs to. 404 conflates "no such team" and "not a
 * member" so id-probing can't enumerate teams the caller isn't in.
 */
export async function getMyTeam(teamId: string): Promise<Team> {
	return apiRequest<Team>(`/teams/${encodeURIComponent(teamId)}`);
}
