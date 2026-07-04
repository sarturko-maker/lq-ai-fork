/**
 * Unit tests for the admin patchUserRole API helper (T5 — Wave B v2;
 * response shape corrected in SETUP-3b review fix F6).
 *
 * Tests: success 200 (UserRoleResponse — user_id, not a full AdminUserRow),
 * and the 403 forbidden last-admin-demote error path (the REAL backend
 * contract: `Forbidden` → 403 code 'forbidden'; no 'last_admin' code exists).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { patchUserRole } from '../api/admin';
import type { UserRoleResponse } from '../types';
import { clearSession, setSession } from '../auth/store';
import { LQAIApiError } from '../api/client';

const realFetch = global.fetch;

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

const UPDATED: UserRoleResponse = {
	user_id: 'u2',
	email: 'bob@example.com',
	role: 'viewer',
	is_admin: false
};

describe('admin patchUserRole API', () => {
	beforeEach(() => {
		clearSession();
		setSession({ access_token: 'tok', expires_in: 900 });
		vi.restoreAllMocks();
	});

	afterEach(() => {
		global.fetch = realFetch;
	});

	it('returns the UserRoleResponse on success', async () => {
		const fetchSpy = vi.fn(async () => jsonResponse(200, UPDATED));
		global.fetch = fetchSpy as unknown as typeof fetch;
		const out = await patchUserRole('u2', 'viewer');
		expect(out.role).toBe('viewer');
		expect(out.user_id).toBe('u2');
		expect(out.is_admin).toBe(false);
		const init = (fetchSpy.mock.calls[0] as unknown as [string, RequestInit])[1];
		expect(init.method).toBe('PATCH');
		const body = JSON.parse(init.body as string);
		expect(body.role).toBe('viewer');
	});

	it('surfaces the last-admin demotion guard as 403 forbidden (real contract)', async () => {
		global.fetch = vi.fn(async () =>
			jsonResponse(403, {
				detail: {
					code: 'forbidden',
					message:
						'Cannot demote the last admin. Promote another user to admin first, then retry the demotion.'
				}
			})
		) as unknown as typeof fetch;
		await expect(patchUserRole('u1', 'member')).rejects.toBeInstanceOf(LQAIApiError);
		await expect(patchUserRole('u1', 'member')).rejects.toMatchObject({
			status: 403,
			code: 'forbidden',
			message:
				'Cannot demote the last admin. Promote another user to admin first, then retry the demotion.'
		});
	});
});
