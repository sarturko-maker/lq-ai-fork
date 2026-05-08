/**
 * /api/v1/files — multipart upload + metadata + soft-delete.
 *
 * Project-scoped attach uses /api/v1/projects/{id}/files (per backend
 * OpenAPI sketch C7); chat-scoped attach is wired client-side in M1 — the
 * backend endpoint shape for chat-attached files is TBD post-M1.
 */
import { apiRequest } from './client';
import type { FileMeta } from '../types';

/** POST /api/v1/files — streaming multipart upload. */
export async function uploadFile(
	file: File,
	opts: { project_id?: string } = {}
): Promise<FileMeta> {
	const fd = new FormData();
	fd.append('file', file, file.name);
	if (opts.project_id) fd.append('project_id', opts.project_id);
	return apiRequest<FileMeta>('/files', { method: 'POST', formData: fd });
}

/** GET /api/v1/files/{id} — metadata. */
export async function getFile(id: string): Promise<FileMeta> {
	return apiRequest<FileMeta>(`/files/${encodeURIComponent(id)}`);
}

/** DELETE /api/v1/files/{id} — soft-delete. */
export async function deleteFile(id: string): Promise<void> {
	await apiRequest<void>(`/files/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/**
 * POST /api/v1/projects/{project_id}/files — attach an existing file to a
 * project. Multipart upload to `/api/v1/files` is the canonical create path;
 * this endpoint links an already-created file row to a project.
 */
export async function attachFileToProject(
	projectId: string,
	fileId: string
): Promise<FileMeta> {
	return apiRequest<FileMeta>(`/projects/${encodeURIComponent(projectId)}/files`, {
		method: 'POST',
		body: { file_id: fileId }
	});
}

/**
 * DELETE /api/v1/projects/{project_id}/files/{file_id} — detach a file from a
 * project (file row remains; only the link is removed).
 */
export async function detachFileFromProject(
	projectId: string,
	fileId: string
): Promise<void> {
	await apiRequest<void>(
		`/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}`,
		{ method: 'DELETE' }
	);
}
