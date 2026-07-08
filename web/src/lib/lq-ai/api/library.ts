/**
 * Org Library — member-readable read model (STORE-2 D-B, ADR-F065).
 *
 * `GET /api/v1/library` is ActiveUser-gated (any active user, not just an
 * admin) — a transparency surface mirroring the tier-config dual-exposure
 * precedent (`inferenceApi.getTierConfig`): the admin write surface
 * (adopt/remove) stays fenced at `adminApi` in this module's sibling.
 */
import { apiRequest } from './client';

/**
 * One entry the org has adopted into its Library, with display metadata.
 *
 * `label`/`description`/`source`/`author`/`version` are all `null` when the
 * underlying catalog entry is dangling (adopted, then removed from the
 * catalog) — render the bare key with an honest "no longer in the shipped
 * catalog" note rather than guessing a label. There is deliberately no
 * `adopted_by` field on this member-visible surface.
 *
 * `approver` (B-2b, D3.5 wire gap): for a `source === "org"` skill entry, the
 * approving admin's email; `null` otherwise. `author` deliberately stays
 * `null` for org skills here (unchanged from B-2a) — this member-visible read
 * still exposes no AUTHOR identity, only that an admin reviewed and approved
 * the content.
 */
export interface LibraryEntry {
	kind: 'skill' | 'tool' | 'playbook' | 'knowledge';
	key: string;
	label: string | null;
	description: string | null;
	source: string | null;
	author: string | null;
	version: string | null;
	approver: string | null;
	adopted_at: string;
}

export interface LibraryResponse {
	entries: LibraryEntry[];
}

/** GET /api/v1/library — every capability the org has adopted (member-readable). */
export async function getLibrary(): Promise<LibraryResponse> {
	return apiRequest<LibraryResponse>('/library');
}
