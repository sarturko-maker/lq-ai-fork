/**
 * Shared citation-display formatting helpers.
 *
 * `previewQuote` was extracted from `M2Citations.svelte` (AE3) so both the
 * sidecar chip list and the AE "Sources" card (`citations/sources.ts`) truncate
 * quotes identically — one source of truth instead of two copies.
 */

/** Truncate a quote for chip / card display so a long sentence doesn't blow the layout. */
export function previewQuote(quote: string, maxChars = 60): string {
	const trimmed = quote.trim();
	if (trimmed.length <= maxChars) return trimmed;
	return `${trimmed.slice(0, maxChars - 1).trimEnd()}…`;
}
