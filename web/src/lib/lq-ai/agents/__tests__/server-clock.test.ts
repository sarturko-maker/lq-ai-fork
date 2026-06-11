import { afterEach, describe, expect, it } from 'vitest';
import { noteServerDate, resetServerClock, serverNowMs } from '../server-clock';

afterEach(() => {
	resetServerClock();
});

describe('server clock skew (F0-S7 — the 330s staleness cutoff carry-over)', () => {
	it('tracks a fast client clock back toward server time', () => {
		// Server is 10 minutes BEHIND the client (client clock fast).
		const serverDate = new Date(Date.now() - 600_000).toUTCString();
		noteServerDate(serverDate);
		const drift = serverNowMs() - Date.now();
		expect(drift).toBeLessThan(-590_000);
		expect(drift).toBeGreaterThan(-610_000);
	});

	it('ignores sub-threshold jitter — local clock wins', () => {
		noteServerDate(new Date(Date.now() - 1_500).toUTCString());
		expect(Math.abs(serverNowMs() - Date.now())).toBeLessThanOrEqual(1);
	});

	it('no-ops on absent or unparseable headers', () => {
		noteServerDate(null);
		noteServerDate('not a date');
		expect(Math.abs(serverNowMs() - Date.now())).toBeLessThanOrEqual(1);
	});
});
