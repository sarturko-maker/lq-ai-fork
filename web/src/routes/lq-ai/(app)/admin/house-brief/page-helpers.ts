/**
 * Pure helpers for the /lq-ai/admin/house-brief page — B-1 (ADR-F049).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (branding-page precedent — no @testing-library/svelte).
 */

/** Server cap on `content_md` (`OrganizationProfileUpdateRequest.content_md`,
 *  `api/app/api/organization_profile.py`) — mirrored client-side so a save
 *  is refused before the round trip, not just after a 422. */
export const HOUSE_BRIEF_MAX_CHARS = 200_000;

/** `null` when the draft is within the server's cap, else a clear message
 *  naming both the limit and the current length. */
export function validateContentLength(content: string): string | null {
	if (content.length > HOUSE_BRIEF_MAX_CHARS) {
		return `The House Brief must be at most ${HOUSE_BRIEF_MAX_CHARS} characters (currently ${content.length}). Trim it and try again.`;
	}
	return null;
}

/** Whether the draft is empty (whitespace-only counts as empty) — drives the
 *  teaching empty-state vs. the markdown preview. */
export function isContentEmpty(content: string): boolean {
	return content.trim().length === 0;
}

/** Locale datetime for "Last updated …" — the shared admin helper,
 *  re-exported so this module stays the page's single import surface. */
import { formatDateTime } from '$lib/lq-ai/admin/page-helpers';
export { formatDateTime };

/**
 * "Last updated {date} by {user}" — `null` when the House Brief has never
 * been saved (fresh org, `updated_at` is null). `updated_by` is the saving
 * admin's id as returned by the API (no name-resolution endpoint is wired
 * to this response yet); falls back to omitting the "by" clause if absent.
 */
export function formatLastUpdated(updatedAt: string | null, updatedBy: string | null): string | null {
	if (!updatedAt) return null;
	const when = formatDateTime(updatedAt);
	return updatedBy ? `Last updated ${when} by ${updatedBy}.` : `Last updated ${when}.`;
}
