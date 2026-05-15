/**
 * Unit tests for the session-activity tracker.
 *
 * Uses vi.useFakeTimers() for time-based assertions. Mocks authApi.refresh
 * and getRefreshToken to keep tests hermetic.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('../api', () => ({
	authApi: { refresh: vi.fn().mockResolvedValue(undefined) }
}));

vi.mock('../auth/store', () => ({
	getRefreshToken: vi.fn().mockReturnValue('rtoken')
}));

import {
	sessionActivity,
	noteActivity,
	startTracker,
	stopTracker,
	_resetTracker,
	IDLE_LOGOUT_AT_MS,
	IDLE_WARN_AT_MS,
	REFRESH_DEBOUNCE_MS,
	CHECK_INTERVAL_MS
} from '../stores/sessionActivity';
import { getRefreshToken } from '../auth/store';
import { authApi } from '../api';

describe('sessionActivity', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.mocked(authApi.refresh).mockClear();
		vi.mocked(getRefreshToken).mockReturnValue('rtoken');
		_resetTracker();
	});

	afterEach(() => {
		stopTracker();
		vi.useRealTimers();
	});

	it('noteActivity updates lastActivityMs and clears showWarning', () => {
		sessionActivity.set({ lastActivityMs: 0, showWarning: true });
		const before = Date.now();
		noteActivity();
		const s = get(sessionActivity);
		expect(s.lastActivityMs).toBeGreaterThanOrEqual(before);
		expect(s.showWarning).toBe(false);
	});

	it('noteActivity calls authApi.refresh with the token when REFRESH_DEBOUNCE_MS has elapsed', () => {
		// Advance time past the debounce window so the first call fires a refresh.
		vi.advanceTimersByTime(REFRESH_DEBOUNCE_MS + 1);
		noteActivity();
		expect(authApi.refresh).toHaveBeenCalledOnce();
		expect(authApi.refresh).toHaveBeenCalledWith('rtoken');
	});

	it('noteActivity does NOT call authApi.refresh when called again within REFRESH_DEBOUNCE_MS', () => {
		// First call (after debounce elapsed) — fires refresh.
		vi.advanceTimersByTime(REFRESH_DEBOUNCE_MS + 1);
		noteActivity();
		expect(authApi.refresh).toHaveBeenCalledOnce();

		// Second call shortly after — still within debounce window.
		vi.advanceTimersByTime(1000);
		noteActivity();
		expect(authApi.refresh).toHaveBeenCalledOnce(); // still only one call
	});

	it('noteActivity skips refresh entirely when getRefreshToken() returns null', () => {
		vi.mocked(getRefreshToken).mockReturnValue(null);
		vi.advanceTimersByTime(REFRESH_DEBOUNCE_MS + 1);
		noteActivity();
		expect(authApi.refresh).not.toHaveBeenCalled();
	});

	it('startTracker fires onLogout after IDLE_LOGOUT_AT_MS elapses', () => {
		const onLogout = vi.fn();
		// Set lastActivityMs to the current frozen time so idle starts at 0.
		const frozenNow = Date.now();
		sessionActivity.set({ lastActivityMs: frozenNow, showWarning: false });
		startTracker(onLogout);

		// Advance to just before the logout threshold (one tick before the last
		// check-interval that would cross IDLE_LOGOUT_AT_MS). No logout yet.
		vi.advanceTimersByTime(IDLE_LOGOUT_AT_MS - CHECK_INTERVAL_MS - 1);
		expect(onLogout).not.toHaveBeenCalled();

		// Advance two more ticks so the interval fires past the boundary.
		vi.advanceTimersByTime(CHECK_INTERVAL_MS + CHECK_INTERVAL_MS);
		expect(onLogout).toHaveBeenCalledOnce();
	});
});
