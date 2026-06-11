/**
 * Server-clock skew tracking — F0-S7 (closes the F0-S3 carry-over).
 *
 * The staleness cutoff (`isStaleRunning`, 330 s) compares the client's
 * clock against the server's `started_at`; a fast client clock marks
 * fresh runs stale. The API client notes the `Date` response header on
 * every request (exposed cross-origin via the api's CORS config), and
 * the agents surface asks this module for "now" instead of trusting
 * `Date.now()` blind.
 *
 * The header has 1 s granularity and rides response latency, so small
 * offsets are noise — skew below the threshold is ignored entirely.
 */

/** |skew| below this is jitter, not drift — keep the local clock. */
const SKEW_IGNORE_MS = 5_000;

let skewMs = 0;

/** Record a response's `Date` header (no-op for absent/unparseable). */
export function noteServerDate(header: string | null | undefined): void {
	if (!header) return;
	const serverMs = Date.parse(header);
	if (Number.isNaN(serverMs)) return;
	const measured = serverMs - Date.now();
	skewMs = Math.abs(measured) < SKEW_IGNORE_MS ? 0 : measured;
}

/** Best estimate of the SERVER's current epoch millis. */
export function serverNowMs(): number {
	return Date.now() + skewMs;
}

/** Test seam. */
export function resetServerClock(): void {
	skewMs = 0;
}
