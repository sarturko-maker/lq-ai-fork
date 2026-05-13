/**
 * /api/v1/projects — list / create / patch / archive.
 */
import { apiRequest } from './client';
import type { Project, ProjectCreate } from '../types';

/**
 * GET /api/v1/projects — list the caller's projects.
 *
 * Query parameters:
 *
 *   * ``archived`` — when true, surface soft-deleted rows alongside
 *     active ones.
 *   * ``includeSandbox`` — Wave D.2 Task 2.3: include the per-user
 *     ``__sandbox__`` matter (excluded by default).
 *   * ``onlySandbox`` — Wave D.2 Task 2.3: return only sandbox rows.
 *     Wins over ``includeSandbox`` on the server when both are set.
 */
export async function listProjects(
	opts: {
		archived?: boolean;
		includeSandbox?: boolean;
		onlySandbox?: boolean;
	} = {}
): Promise<Project[]> {
	const params = new URLSearchParams();
	if (opts.archived) params.set('archived', 'true');
	if (opts.includeSandbox) params.set('include_sandbox', 'true');
	if (opts.onlySandbox) params.set('only_sandbox', 'true');
	const qs = params.toString();
	return apiRequest<Project[]>(`/projects${qs ? `?${qs}` : ''}`);
}

/**
 * POST /api/v1/projects/sandbox/ensure — Wave D.2 Task 2.2.
 *
 * Idempotent find-or-create of the caller's per-user try-it sandbox
 * matter (slug ``__sandbox__``). First call returns 201 with a fresh
 * row; subsequent calls return 200 with the same row. The endpoint
 * accepts no body; auth is the only requirement.
 */
export async function ensureSandbox(): Promise<Project> {
	return apiRequest<Project>('/projects/sandbox/ensure', { method: 'POST' });
}

/** POST /api/v1/projects */
export async function createProject(body: ProjectCreate): Promise<Project> {
	return apiRequest<Project>('/projects', { method: 'POST', body });
}

/** GET /api/v1/projects/{id} */
export async function getProject(id: string): Promise<Project> {
	return apiRequest<Project>(`/projects/${encodeURIComponent(id)}`);
}

/** PATCH /api/v1/projects/{id} */
export async function patchProject(id: string, body: Partial<Project>): Promise<Project> {
	return apiRequest<Project>(`/projects/${encodeURIComponent(id)}`, {
		method: 'PATCH',
		body
	});
}

/** DELETE /api/v1/projects/{id} (soft-delete / archive). */
export async function archiveProject(id: string): Promise<void> {
	await apiRequest<void>(`/projects/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// File attachment / detachment
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/projects/{id}/files — link an existing file row to this
 * project. Returns the updated Project with `attached_file_ids` reflecting
 * the new attachment.
 */
export async function attachFile(projectId: string, fileId: string): Promise<Project> {
	return apiRequest<Project>(`/projects/${encodeURIComponent(projectId)}/files`, {
		method: 'POST',
		body: { file_id: fileId }
	});
}

/**
 * DELETE /api/v1/projects/{id}/files/{file_id} — remove the link between
 * the file and the project (file row remains; only the link is removed).
 * Returns the updated Project with `attached_file_ids` updated.
 */
export async function detachFile(projectId: string, fileId: string): Promise<Project> {
	return apiRequest<Project>(
		`/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}`,
		{ method: 'DELETE' }
	);
}

// ---------------------------------------------------------------------------
// Skill attachment / detachment
// ---------------------------------------------------------------------------

/**
 * POST /api/v1/projects/{id}/skills — attach a skill (by name) to this
 * project. Returns the updated Project with `attached_skill_names` updated.
 */
export async function attachSkill(projectId: string, skillName: string): Promise<Project> {
	return apiRequest<Project>(`/projects/${encodeURIComponent(projectId)}/skills`, {
		method: 'POST',
		body: { skill_name: skillName }
	});
}

/**
 * DELETE /api/v1/projects/{id}/skills/{skill_name} — detach a skill from
 * this project. Returns the updated Project with `attached_skill_names`
 * updated.
 */
export async function detachSkill(projectId: string, skillName: string): Promise<Project> {
	return apiRequest<Project>(
		`/projects/${encodeURIComponent(projectId)}/skills/${encodeURIComponent(skillName)}`,
		{ method: 'DELETE' }
	);
}
