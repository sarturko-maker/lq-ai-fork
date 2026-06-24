/**
 * /api/v1/matters/{id}/files — the matter-files read surface (C7a, ADR-F046).
 *
 * Feeds the cockpit Documents tab and the inline redline-download button. Read is
 * owner-scoped; the backend returns 404 (never 403) on a missing/cross-user/archived
 * matter — surfaced here as a plain `LQAIApiError` for the caller to render. The
 * actual bytes are downloaded via `filesApi.downloadFile` (GET /files/{id}/content).
 */
import { apiRequest } from './client';
import type { MatterFilesRead } from '../types';

/** GET /api/v1/matters/{id}/files — the matter's files, newest-first (metadata only). */
export async function listMatterFiles(projectId: string): Promise<MatterFilesRead> {
	return apiRequest<MatterFilesRead>(`/matters/${encodeURIComponent(projectId)}/files`);
}
