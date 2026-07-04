/**
 * Pure helpers for the unauthenticated token pages (SETUP-3b, ADR-F061):
 * /lq-ai/accept-invite and /lq-ai/reset-password.
 *
 * Extracted so vitest can exercise the logic without a SvelteKit runtime —
 * the page templates are glue. The token is read from the URL exactly once on
 * mount and held in component state only: never logged, never stored.
 */

/** Client-side floor mirroring `password_min_length` (ChangePasswordCard precedent). */
export const PASSWORD_MIN_LENGTH = 12;

/**
 * Extract the lifecycle token from the page's query string. Missing/blank →
 * null, which the pages render as an immediate invalid-link state (accept) or
 * the request form (reset) — no request is ever fired with an empty token.
 */
export function readToken(search: URLSearchParams): string | null {
	const token = (search.get('token') ?? '').trim();
	return token.length > 0 ? token : null;
}

/** Min-length + confirmation check, mirroring ChangePasswordCard's rules. */
export function validateNewPassword(password: string, confirm: string): string | null {
	if (password.length < PASSWORD_MIN_LENGTH) {
		return `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`;
	}
	if (password !== confirm) {
		return 'Password and confirmation do not match.';
	}
	return null;
}

/**
 * The page's URL with the `token` query param removed (relative form, ready
 * for SvelteKit's `replaceState`), or null when the URL carries no token.
 * Defense-in-depth (SETUP-3b review fix F7): after `readToken()` the
 * single-use token lives in component state only — scrubbing the address bar
 * keeps it out of shared-machine history and autocomplete.
 */
export function stripTokenParam(href: string): string | null {
	const url = new URL(href);
	if (!url.searchParams.has('token')) return null;
	url.searchParams.delete('token');
	return url.pathname + url.search + url.hash;
}
