/**
 * /api/v1/matters/{id}/memory — the matter-memory read surface + wiki revert
 * (C3c, ADR-F042 / F044). Read is open to the matter owner; the revert is a
 * human-authenticated, owner-scoped action (the agent has no revert tool).
 * Backend authz returns 404 (never 403) on a missing/cross-user/archived
 * matter — surfaced here as a plain `LQAIApiError` for the caller to render.
 */
import { apiRequest } from './client';
import type {
	MatterCorrectionCreated,
	MatterEntryRetired,
	MatterMemoryRead,
	MatterParticipantInput,
	MatterParticipantRead,
	WikiRevertResponse
} from '../types';

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

/**
 * POST /api/v1/matters/{id}/memory/corrections — pin a human correction (C3-UM).
 * Always written `trust='human-pinned'` with the author from the session; the agent
 * cannot mint a pin. The next agent run reads it as ground truth.
 */
export async function pinCorrection(
	projectId: string,
	bodyMd: string
): Promise<MatterCorrectionCreated> {
	return apiRequest<MatterCorrectionCreated>(
		`/matters/${encodeURIComponent(projectId)}/memory/corrections`,
		{ method: 'POST', body: { body_md: bodyMd } }
	);
}

/**
 * POST /api/v1/matters/{id}/memory/corrections/{entryId}/retire — soft-retire a pinned
 * correction (C3-UM). Sets `superseded_at`; the row stays in the log marked superseded.
 * Idempotent; human-authenticated (the agent has no retire tool).
 */
export async function retireCorrection(
	projectId: string,
	entryId: string
): Promise<MatterEntryRetired> {
	return apiRequest<MatterEntryRetired>(
		`/matters/${encodeURIComponent(projectId)}/memory/corrections/${encodeURIComponent(entryId)}/retire`,
		{ method: 'POST' }
	);
}

/**
 * POST /api/v1/matters/{id}/memory/facts/{entryId}/retire — close a fact's validity
 * window (C3-UM). Sets `invalid_at`; idempotent. A fact whose validity has not begun
 * yet is rejected (409) — surfaced here as an `LQAIApiError`.
 */
export async function retireFact(projectId: string, entryId: string): Promise<MatterEntryRetired> {
	return apiRequest<MatterEntryRetired>(
		`/matters/${encodeURIComponent(projectId)}/memory/facts/${encodeURIComponent(entryId)}/retire`,
		{ method: 'POST' }
	);
}

/**
 * POST /api/v1/matters/{id}/roster — add a who-is-who participant (ADR-F048). Always
 * written `trust='confirmed'` with the author from the session (the lawyer owns it).
 */
export async function createParticipant(
	projectId: string,
	body: MatterParticipantInput
): Promise<MatterParticipantRead> {
	return apiRequest<MatterParticipantRead>(`/matters/${encodeURIComponent(projectId)}/roster`, {
		method: 'POST',
		body
	});
}

/**
 * PATCH /api/v1/matters/{id}/roster/{entryId} — edit a participant (ADR-F048). A partial
 * edit; any edit (re)confirms the entry so the agent no longer overrides its side/role.
 */
export async function updateParticipant(
	projectId: string,
	entryId: string,
	body: MatterParticipantInput
): Promise<MatterParticipantRead> {
	return apiRequest<MatterParticipantRead>(
		`/matters/${encodeURIComponent(projectId)}/roster/${encodeURIComponent(entryId)}`,
		{ method: 'PATCH', body }
	);
}

/**
 * POST /api/v1/matters/{id}/roster/{entryId}/retire — remove a participant from the
 * active roster (ADR-F048). Soft (the row is kept, dropped off the active roster).
 */
export async function retireParticipant(
	projectId: string,
	entryId: string
): Promise<MatterEntryRetired> {
	return apiRequest<MatterEntryRetired>(
		`/matters/${encodeURIComponent(projectId)}/roster/${encodeURIComponent(entryId)}/retire`,
		{ method: 'POST' }
	);
}
