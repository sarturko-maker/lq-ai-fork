/**
 * /api/v1/projects — list / create / patch / archive.
 */
import { apiRequest } from './client';
import type { Project, ProjectCreate } from '../types';

/** GET /api/v1/projects?archived=… */
export async function listProjects(opts: { archived?: boolean } = {}): Promise<Project[]> {
	const qs = opts.archived ? '?archived=true' : '';
	return apiRequest<Project[]>(`/projects${qs}`);
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
