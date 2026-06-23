/**
 * /api/v1/matters/{id}/memory — the matter-memory read surface + wiki revert
 * (C3c, ADR-F042 / F044). Read is open to the matter owner; the revert is a
 * human-authenticated, owner-scoped action (the agent has no revert tool).
 * Backend authz returns 404 (never 403) on a missing/cross-user/archived
 * matter — surfaced here as a plain `LQAIApiError` for the caller to render.
 */
import { apiRequest } from './client';
import type { MatterMemoryRead, WikiRevertResponse } from '../types';

/** GET /api/v1/matters/{id}/memory — the full read-only memory projection. */
export async function readMatterMemory(projectId: string): Promise<MatterMemoryRead> {
	return apiRequest<MatterMemoryRead>(`/matters/${encodeURIComponent(projectId)}/memory`);
}

/**
 * POST /api/v1/matters/{id}/memory/wiki/revert — restore a chosen
 * `wiki_snapshot` version into the live wiki. Snapshots the current wiki first
 * (so the revert is itself reversible); append-only, nothing is deleted.
 */
export async function revertWiki(
	projectId: string,
	snapshotId: string
): Promise<WikiRevertResponse> {
	return apiRequest<WikiRevertResponse>(
		`/matters/${encodeURIComponent(projectId)}/memory/wiki/revert`,
		{ method: 'POST', body: { snapshot_id: snapshotId } }
	);
}
