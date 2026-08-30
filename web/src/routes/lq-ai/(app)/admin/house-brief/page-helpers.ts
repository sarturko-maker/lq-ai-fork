/**
 * Pure helpers for the /lq-ai/admin/house-brief page — B-1 (ADR-F049).
 *
 * Extracted out of `+page.svelte` so vitest can exercise them without a
 * SvelteKit runtime (branding-page precedent — no @testing-library/svelte).
 */

/** Server cap on `content_md` (`OrganizationProfileUpdateRequest.content_md`,
 *  `api/app/api/organization_profile.py` — `HOUSE_BRIEF_MAX_CHARS`) — mirrored
 *  client-side so a save is refused before the round trip, not just after a 422.
 *  The brief is injected verbatim into every prompt, so it stays a tight
 *  one-pager (VM2-G, task #532). Keep in sync with the backend constant. */
export const HOUSE_BRIEF_MAX_CHARS = 32_000;

/** `null` when the draft is within the server's cap, else a clear message
 *  naming both the limit and the current length. */
export function validateContentLength(content: string): string | null {
	if (content.length > HOUSE_BRIEF_MAX_CHARS) {
		return `The House Brief must be at most ${HOUSE_BRIEF_MAX_CHARS} characters (currently ${content.length}). Trim it and try again.`;
	}
	return null;
}

/** INTAKE-4a (ADR-F088): the org code's shape, mirroring the server's
 *  `CODE_PATTERN` (`app/matters/reference.py`) and its DB CHECK. Two to six
 *  characters, uppercase letters and digits. */
export const ORG_CODE_RE = /^[A-Z0-9]{2,6}$/;

/** Up-case as the admin types so the strict server pattern is an affordance,
 *  not a trap. Non-alphanumerics are dropped as they are typed and the value is
 *  capped at six characters — the SERVER still rejects anything malformed
 *  (reject, don't sanitize); this only keeps the field from producing one. */
export function normalizeOrgCodeInput(raw: string): string {
	return raw
		.toUpperCase()
		.replace(/[^A-Z0-9]/g, '')
		.slice(0, 6);
}

/** `null` when the code is acceptable (empty = "not set yet"), else a message. */
export function validateOrgCode(code: string): string | null {
	if (code === '') return null;
	if (!ORG_CODE_RE.test(code)) {
		return 'The org code must be 2 to 6 characters, letters and digits only (e.g. NWT).';
	}
	return null;
}

/** The example matter reference an org code produces, for the field's help text. */
export function exampleReference(code: string): string {
	return `${code || 'ORG'}-COM-0042`;
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
export function formatLastUpdated(
	updatedAt: string | null,
	updatedBy: string | null
): string | null {
	if (!updatedAt) return null;
	const when = formatDateTime(updatedAt);
	return updatedBy ? `Last updated ${when} by ${updatedBy}.` : `Last updated ${when}.`;
}
