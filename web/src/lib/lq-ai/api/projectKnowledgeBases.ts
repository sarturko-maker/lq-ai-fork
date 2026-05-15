/**
 * /api/v1/projects/{id}/knowledge-bases — attach / detach helpers.
 *
 * Wraps the T3 backend endpoints. Mirrors the `attachFile` / `detachFile`
 * pattern in `projects.ts` and the same `apiRequest` helper for auth header
 * attachment, refresh-on-401, and structured error translation.
 */
import { apiRequest } from './client';
import type { Project } from '../types';

/**
 * POST /api/v1/projects/{id}/knowledge-bases — attach a knowledge base
 * (by id) to this project. Caller must own both the project and the KB
 * (cross-user → 404 on either side). Idempotent — re-attaching an already-
 * attached KB returns 200 with the current project state.
 *
 * Returns the updated Project with `attached_knowledge_base_ids` reflecting
 * the attachment.
 */
export async function attachKnowledgeBase(
	projectId: string,
	knowledgeBaseId: string
): Promise<Project> {
	return apiRequest<Project>(
		`/projects/${encodeURIComponent(projectId)}/knowledge-bases`,
		{
			method: 'POST',
			body: { knowledge_base_id: knowledgeBaseId }
		}
	);
}

/**
 * DELETE /api/v1/projects/{id}/knowledge-bases/{kb_id} — detach a KB
 * from this project. Idempotent — detaching a non-attached KB returns 204.
 * Resolves to `undefined` (no body) on success.
 */
export async function detachKnowledgeBase(
	projectId: string,
	knowledgeBaseId: string
): Promise<void> {
	await apiRequest<void>(
		`/projects/${encodeURIComponent(projectId)}/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`,
		{ method: 'DELETE' }
	);
}
