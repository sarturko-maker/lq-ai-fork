/**
 * /api/v1/knowledge-bases — list / create / attach-file helpers.
 *
 * Wraps the C7 backend endpoints. Mirrors `projects.ts` / `files.ts`: uses
 * `apiRequest` for auth-header attachment, refresh-on-401, and structured
 * error translation. Owned-only (cross-user → 404 on either side).
 */
import { apiRequest } from './client';
import type { KnowledgeBase, KnowledgeBaseCreate } from '../types';

/**
 * GET /api/v1/knowledge-bases — list the caller's knowledge bases.
 *
 * `archived` defaults to false (active only); pass `archived: true` to fetch
 * only archived KBs. `project_id` filters to KBs associated with a project.
 */
export async function listKnowledgeBases(
	opts: { archived?: boolean; project_id?: string } = {}
): Promise<KnowledgeBase[]> {
	const params = new URLSearchParams();
	if (opts.archived) params.set('archived', 'true');
	if (opts.project_id) params.set('project_id', opts.project_id);
	const qs = params.toString();
	const path = qs ? `/knowledge-bases?${qs}` : '/knowledge-bases';
	return apiRequest<KnowledgeBase[]>(path);
}

/** GET /api/v1/knowledge-bases/{id} — fetch a single KB with file count + chunk count. */
export async function getKnowledgeBase(id: string): Promise<KnowledgeBase> {
	return apiRequest<KnowledgeBase>(`/knowledge-bases/${encodeURIComponent(id)}`);
}

/** POST /api/v1/knowledge-bases — create a new knowledge base. */
export async function createKnowledgeBase(
	body: KnowledgeBaseCreate
): Promise<KnowledgeBase> {
	return apiRequest<KnowledgeBase>('/knowledge-bases', {
		method: 'POST',
		body: body as unknown as Record<string, unknown>
	});
}

/**
 * POST /api/v1/knowledge-bases/{kb_id}/files — attach an already-uploaded
 * file to a KB. The file must be owned by the caller and have completed
 * the C5 ingest pipeline (`ingestion_status='ready'`); attaching a still-
 * processing file → 422.
 */
export async function attachFileToKB(
	kbId: string,
	fileId: string
): Promise<void> {
	await apiRequest<void>(
		`/knowledge-bases/${encodeURIComponent(kbId)}/files`,
		{
			method: 'POST',
			body: { file_id: fileId }
		}
	);
}

/** DELETE /api/v1/knowledge-bases/{kb_id}/files/{file_id} — detach a file from a KB. */
export async function detachFileFromKB(
	kbId: string,
	fileId: string
): Promise<void> {
	await apiRequest<void>(
		`/knowledge-bases/${encodeURIComponent(kbId)}/files/${encodeURIComponent(fileId)}`,
		{ method: 'DELETE' }
	);
}
