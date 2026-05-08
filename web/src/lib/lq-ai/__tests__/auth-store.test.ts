/**
 * Auth-store unit tests (browser-flagged paths assume `browser: true` set
 * via Vitest's jsdom environment; the store gracefully no-ops `localStorage`
 * when missing).
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { get } from 'svelte/store';

import {
	auth,
	clearSession,
	getAccessToken,
	setSession,
	tokenIsStale
} from '../auth/store';

describe('auth store', () => {
	beforeEach(() => {
		clearSession();
	});

	it('starts empty', () => {
		expect(getAccessToken()).toBeNull();
		expect(tokenIsStale()).toBe(true);
	});

	it('records the access token + expiry on setSession', () => {
		setSession({
			access_token: 'tok',
			refresh_token: 'rtok',
			expires_in: 900,
			user: {
				id: 'u',
				email: 'admin@lq.ai',
				is_admin: true,
				mfa_enabled: false,
				must_change_password: false,
				created_at: '2025-01-01T00:00:00Z'
			}
		});

		expect(getAccessToken()).toBe('tok');
		const state = get(auth);
		expect(state.user?.email).toBe('admin@lq.ai');
		expect(state.expires_at).toBeGreaterThan(Date.now());
		expect(tokenIsStale()).toBe(false);
	});

	it('treats a soon-to-expire token as stale (60s margin)', () => {
		setSession({ access_token: 't', expires_in: 30 });
		expect(tokenIsStale()).toBe(true);
		expect(tokenIsStale(0)).toBe(false);
	});

	it('clearSession wipes everything', () => {
		setSession({ access_token: 't', expires_in: 900 });
		clearSession();
		expect(getAccessToken()).toBeNull();
		expect(get(auth).user).toBeNull();
	});
});
