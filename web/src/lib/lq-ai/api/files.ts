/**
 * /api/v1/files — multipart upload + metadata + soft-delete.
 *
 * Project-scoped attach uses /api/v1/projects/{id}/files (per backend
 * OpenAPI sketch C7); chat-scoped attach is wired client-side in M1 — the
 * backend endpoint shape for chat-attached files is TBD post-M1.
 */
import { apiBlobRequest, apiRequest } from './client';
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
export async function attachFileToProject(projectId: string, fileId: string): Promise<FileMeta> {
	return apiRequest<FileMeta>(`/projects/${encodeURIComponent(projectId)}/files`, {
		method: 'POST',
		body: { file_id: fileId }
	});
}

/**
 * DELETE /api/v1/projects/{project_id}/files/{file_id} — detach a file from a
 * project (file row remains; only the link is removed).
 */
export async function detachFileFromProject(projectId: string, fileId: string): Promise<void> {
	await apiRequest<void>(
		`/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}`,
		{ method: 'DELETE' }
	);
}

/**
 * Choose the filename for a saved download. Prefer the caller-supplied name (the
 * cockpit already has it from the file listing), then the server's
 * `Content-Disposition` (handling both `filename="..."` and RFC 5987
 * `filename*=UTF-8''...`), then the bare id. Pure — unit-tested apart from the DOM.
 */
export function pickDownloadFilename(
	explicit: string | undefined,
	disposition: string | null,
	fallbackId: string
): string {
	if (explicit && explicit.trim()) return explicit;
	const star = disposition?.match(/filename\*=UTF-8''([^;]+)/i);
	if (star) {
		try {
			return decodeURIComponent(star[1]);
		} catch {
			/* fall through to the plain form */
		}
	}
	const plain = disposition?.match(/filename="([^"]+)"/i);
	if (plain) return plain[1];
	return fallbackId;
}

/**
 * GET /api/v1/files/{id}/content — fetch the bytes with auth (refresh-on-401) and
 * trigger a browser download. Used to download a matter document / redline output
 * work product (C7a, ADR-F046). Browser-only — the DOM bits no-op under SSR/tests.
 */
export async function downloadFile(fileId: string, filename?: string): Promise<void> {
	const res = await apiBlobRequest(`/files/${encodeURIComponent(fileId)}/content`);
	const blob = await res.blob();
	const name = pickDownloadFilename(filename, res.headers.get('content-disposition'), fileId);

	if (typeof document === 'undefined') {
		return;
	}
	const url = URL.createObjectURL(blob);
	try {
		const a = document.createElement('a');
		a.href = url;
		a.download = name;
		document.body.appendChild(a);
		a.click();
		a.remove();
	} finally {
		URL.revokeObjectURL(url);
	}
}

/**
 * GET /api/v1/files/{id}/content — fetch the bytes with auth (refresh-on-401)
 * and open them in a new browser tab (viewable types render inline; others
 * download). Used by the tabular cell drawer's "Open source document" action
 * (F2 Tabular T6, ADR-F055 T6 M5). Browser-only; no-ops under SSR/tests.
 * Falls back to a download when a popup is blocked so the click is never lost.
 */
export async function openFileInNewTab(fileId: string): Promise<void> {
	const res = await apiBlobRequest(`/files/${encodeURIComponent(fileId)}/content`);
	const blob = await res.blob();
	if (typeof window === 'undefined' || typeof document === 'undefined') {
		return;
	}
	const url = URL.createObjectURL(blob);
	const win = window.open(url, '_blank', 'noopener,noreferrer');
	if (!win) {
		const a = document.createElement('a');
		a.href = url;
		a.download = '';
		document.body.appendChild(a);
		a.click();
		a.remove();
	}
	// Defer revoke so the opened tab has time to load the blob.
	setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
